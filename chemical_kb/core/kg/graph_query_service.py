# -*- coding: utf-8 -*-
"""Graph Query Service：Neo4j Cypher 查询，返回 Cytoscape 子图（nodes + edges）。

性能要求：Cypher 先过滤 → 返回子图 → Cytoscape 渲染，不在 Python 里加载全图再过滤。
"""
from core.kg.neo4j_store import Neo4jStore


def _node_dict(n):
    return {
        "canonical_id": n.get("canonical_id", ""),
        "name": n.get("name", ""),
        "entity_type": n.get("entity_type", ""),
        "label": list(n.labels)[0] if n.labels else "",
    }


def _edge_dict(r, sub_id=None, obj_id=None):
    return {
        "assertion_id": r.get("assertion_id", ""),
        "predicate": r.type,
        "review_status": r.get("review_status", ""),
        "confidence": r.get("confidence", ""),
        "assertion_type": r.get("assertion_type", ""),
        "source_doc_id": r.get("source_doc_id", ""),
        "source_chunk_id": r.get("source_chunk_id", ""),
        "page_start": r.get("page_start", ""),
        "page_end": r.get("page_end", ""),
        "source_text_quote": r.get("source_text_quote", ""),
        "valid_from": r.get("valid_from", ""),
        "valid_to": r.get("valid_to", ""),
        "recorded_at": r.get("recorded_at", ""),
        "_sub": sub_id,
        "_obj": obj_id,
    }


class GraphQueryService:
    def __init__(self, store=None):
        self.store = store or Neo4jStore()

    def _subgraph_from_paths(self, paths, include_status=None):
        """把 Neo4j path 记录转成 {nodes, edges}。"""
        nodes = {}
        edges = []
        for p in paths:
            for node in p.nodes:
                cid = node.get("canonical_id", "")
                if cid and cid not in nodes:
                    nodes[cid] = _node_dict(node)
            for rel in p.relationships:
                if include_status and rel.get("review_status", "") not in include_status:
                    continue
                sub = rel.start_node.get("canonical_id", "")
                obj = rel.end_node.get("canonical_id", "")
                edges.append(_edge_dict(rel, sub, obj))
        # 去重边
        seen = set()
        uniq = []
        for e in edges:
            key = (e["_sub"], e["predicate"], e["_obj"], e.get("assertion_id", ""))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(e)
        return {"nodes": list(nodes.values()), "edges": uniq}

    # ------------------------------------------------------------------ #
    # 已审核知识（approved）
    # ------------------------------------------------------------------ #
    def query_approved(self, center_id=None, hop=1, limit=100):
        cql = (
            "MATCH p = (c {canonical_id: $center})-[*1.." + str(int(hop)) + "]-(n) "
            "WHERE all(r IN relationships(p) WHERE r.review_status = 'approved') "
            "RETURN p LIMIT $limit"
        )
        with self.store.connect().session() as s:
            paths = [rec["p"] for rec in s.run(cql, center=center_id, limit=limit)]
        return self._subgraph_from_paths(paths, include_status={"approved"})

    def query_approved_all(self, limit=200):
        cql = (
            "MATCH (a)-[r]->(b) WHERE r.review_status = 'approved' "
            "RETURN a, r, b LIMIT $limit"
        )
        with self.store.connect().session() as s:
            recs = list(s.run(cql, limit=limit))
        nodes, edges = {}, []
        for a, r, b in recs:
            for n in (a, b):
                cid = n.get("canonical_id", "")
                if cid and cid not in nodes:
                    nodes[cid] = _node_dict(n)
            edges.append(_edge_dict(r, a.get("canonical_id", ""), b.get("canonical_id", "")))
        return {"nodes": list(nodes.values()), "edges": edges}

    # ------------------------------------------------------------------ #
    # 全部关系（candidate + approved）
    # ------------------------------------------------------------------ #
    def query_all(self, center_id=None, hop=1, limit=150):
        cql = (
            "MATCH p = (c {canonical_id: $center})-[*1.." + str(int(hop)) + "]-(n) "
            "RETURN p LIMIT $limit"
        )
        with self.store.connect().session() as s:
            paths = [rec["p"] for rec in s.run(cql, center=center_id, limit=limit)]
        return self._subgraph_from_paths(paths)

    def query_all_all(self, limit=200):
        """全部关系（无中心实体）：candidate + approved 所有边。"""
        cql = "MATCH (a)-[r]->(b) RETURN a, r, b LIMIT $limit"
        with self.store.connect().session() as s:
            recs = list(s.run(cql, limit=limit))
        nodes, edges = {}, []
        for a, r, b in recs:
            for n in (a, b):
                cid = n.get("canonical_id", "")
                if cid and cid not in nodes:
                    nodes[cid] = _node_dict(n)
            edges.append(_edge_dict(r, a.get("canonical_id", ""), b.get("canonical_id", "")))
        return {"nodes": list(nodes.values()), "edges": edges}

    # ------------------------------------------------------------------ #
    # 路径查询
    # ------------------------------------------------------------------ #
    def query_path(self, start_id, end_id, max_depth=5, limit=5):
        cql = (
            "MATCH p = shortestPath((a {canonical_id: $start})-[*.." + str(int(max_depth)) + "]-(b {canonical_id: $end})) "
            "RETURN p LIMIT $limit"
        )
        with self.store.connect().session() as s:
            paths = [rec["p"] for rec in s.run(cql, start=start_id, end=end_id, limit=limit)]
        if not paths:
            return {"found": False, "nodes": [], "edges": [],
                    "reason": "无路径或起点/终点实体不存在"}
        p = paths[0]
        ordered_ids = [n.get("canonical_id", "") for n in p.nodes]
        g = self._subgraph_from_paths([p])
        g["found"] = True
        g["path"] = ordered_ids
        return g

    # ------------------------------------------------------------------ #
    # 搜索 / 统计
    # ------------------------------------------------------------------ #
    def search_nodes(self, query, limit=20):
        cql = (
            "MATCH (n) WHERE n.name CONTAINS $q OR n.canonical_id CONTAINS $q "
            "RETURN n.canonical_id AS canonical_id, n.name AS name, "
            "n.entity_type AS entity_type LIMIT $limit"
        )
        with self.store.connect().session() as s:
            return [rec.data() for rec in s.run(cql, q=query, limit=limit)]

    def get_stats(self):
        """按实体类型统计节点数 + 关系数。"""
        node_cql = "MATCH (n) RETURN n.entity_type AS t, count(n) AS c"
        rel_cql = "MATCH ()-[r]->() RETURN r.review_status AS s, count(r) AS c"
        with self.store.connect().session() as s:
            node_stats = {r["t"] or "other": r["c"] for r in s.run(node_cql)}
            rel_stats = {r["s"] or "unknown": r["c"] for r in s.run(rel_cql)}
        return {
            "node_count": sum(node_stats.values()),
            "relation_count": sum(rel_stats.values()),
            "by_type": node_stats,
            "by_review_status": rel_stats,
        }
