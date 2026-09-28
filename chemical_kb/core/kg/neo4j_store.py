# -*- coding: utf-8 -*-
"""Neo4j Store：图谱数据存储 + 节点/关系 MERGE。

Neo4j = Production / Visualization Graph Store（不是 Review/Extraction 原始事实记录，
原始事实仍在 JSONL）。节点按 schema_v1.json 的实体类型建 label，关系严格用 schema 关系。

连接配置：环境变量 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD 优先，否则读 configs/kg/neo4j.yaml。
"""
import os
from pathlib import Path

from neo4j import GraphDatabase

from core.config import BASE_DIR
from core.entity_registry import EntityRegistry

CONFIG_PATH = BASE_DIR / "configs" / "kg" / "neo4j.yaml"


def _read_yaml_simple(path):
    """极简 key: value 解析（避免依赖 PyYAML），剥离内联注释。"""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        # 剥离内联注释（" # ..."）
        line = line.split(" #", 1)[0]
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get_config():
    cfg = _read_yaml_simple(CONFIG_PATH)
    return {
        "uri": os.environ.get("NEO4J_URI", cfg.get("neo4j_uri", "bolt://localhost:7687")),
        "user": os.environ.get("NEO4J_USER", cfg.get("neo4j_user", "neo4j")),
        "password": os.environ.get("NEO4J_PASSWORD", cfg.get("neo4j_password", "neo4j")),
    }


class Neo4jStore:
    def __init__(self, config=None):
        self.config = config or get_config()
        self._driver = None

    # ------------------------------------------------------------------ #
    # 连接
    # ------------------------------------------------------------------ #
    def connect(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.config["uri"],
                auth=(self.config["user"], self.config["password"]),
            )
        return self._driver

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def is_connected(self):
        try:
            self.connect()
            with self._driver.session() as s:
                s.run("RETURN 1").consume()
            return True
        except Exception:
            return False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ------------------------------------------------------------------ #
    # 写入（幂等 MERGE）
    # ------------------------------------------------------------------ #
    def merge_assertion(self, assertion):
        """把一条 CandidateAssertion 写入 Neo4j。节点按 canonical_id MERGE，关系按 assertion_id MERGE。"""
        assertion = EntityRegistry().apply(assertion)
        sid = assertion.get("subject_id", "")
        oid = assertion.get("object_id", "")
        pred = assertion.get("predicate", "")
        if not sid or not pred:
            return {"skipped": "no subject/predicate"}
        if assertion.get("object_kind") == "literal" or not oid:
            # 属性断言（literal）只存节点，不建关系
            self.merge_node(sid, assertion.get("subject_label", sid),
                            assertion.get("subject_type", ""), assertion)
            return {"node_only": sid}

        self.merge_node(sid, assertion.get("subject_label", sid),
                        assertion.get("subject_type", ""), assertion)
        self.merge_node(oid, assertion.get("object_label", oid),
                        assertion.get("object_type", ""), assertion)
        self.merge_relation(sid, pred, oid, assertion)
        return {"merged": f"{sid} -[{pred}]-> {oid}"}

    def merge_node(self, canonical_id, name, entity_type, assertion=None):
        label = (entity_type or "Entity")
        cql = (
            f"MERGE (n:{label} {{canonical_id: $cid}}) "
            "ON CREATE SET n.name = $name, n.entity_type = $etype "
            "ON MATCH SET n.name = $name, n.entity_type = $etype "
            "RETURN n.canonical_id"
        )
        with self.connect().session() as s:
            s.run(cql, cid=canonical_id, name=name, etype=entity_type).consume()

    def merge_relation(self, sid, pred, oid, assertion):
        rel_type = self._valid_relation_type(pred)
        cql = (
            f"MATCH (a {{canonical_id: $sid}}), (b {{canonical_id: $oid}}) "
            f"MERGE (a)-[r:{rel_type} {{assertion_id: $aid}}]->(b) "
            "SET r.review_status = $rs, r.confidence = $cf, r.assertion_type = $at, "
            "r.source_doc_id = $sdi, r.source_chunk_id = $sci, "
            "r.page_start = $ps, r.page_end = $pe, r.source_text_quote = $stq, "
            "r.valid_from = $vf, r.valid_to = $vt, r.recorded_at = $ra, r.superseded_at = $sa "
            "RETURN type(r)"
        )
        with self.connect().session() as s:
            s.run(cql,
                  sid=sid, oid=oid,
                  aid=assertion.get("assertion_id", ""),
                  rs=assertion.get("review_status", ""),
                  cf=assertion.get("confidence", ""),
                  at=assertion.get("assertion_type", ""),
                  sdi=assertion.get("source_doc_id", ""),
                  sci=assertion.get("source_chunk_id", ""),
                  ps=str(assertion.get("page_start", "")),
                  pe=str(assertion.get("page_end", "")),
                  stq=assertion.get("source_text_quote", ""),
                  vf=assertion.get("valid_from") or None, vt=assertion.get("valid_to") or None,
                  ra=assertion.get("recorded_at") or assertion.get("created_at") or None,
                  sa=assertion.get("superseded_at") or None).consume()

    @staticmethod
    def _valid_relation_type(pred):
        """关系类型只能用合法标识符（防 Cypher 注入）。"""
        pred = str(pred or "").strip()
        if not pred or not all(c.isalnum() or c == "_" for c in pred):
            raise ValueError(f"非法关系类型: {pred!r}")
        return pred

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def count_nodes(self):
        with self.connect().session() as s:
            return s.run("MATCH (n) RETURN count(n) AS c").single()["c"]

    def count_relations(self):
        with self.connect().session() as s:
            return s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
