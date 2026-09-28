# -*- coding: utf-8 -*-
"""Case Repository：cases.jsonl 统一 metadata store + success/failure 独立 FAISS 索引。

目录（data/kg/cases/）：
- cases.jsonl          全部 case（含 test / deprecated / pending / verified）
- success/  embeddings.npy  metadata.json  faiss.index
- failure/  embeddings.npy  metadata.json  faiss.index

只有 case_status == verified 进入 FAISS retrieval index（十八）。
add_case 幂等（三十四）：同一 case_id 第二次 add 不重复加入。
"""
import json
from pathlib import Path

import faiss
import numpy as np

from core.config import BASE_DIR
from core.embedding import EmbeddingModel

CASES_DIR = BASE_DIR / "data" / "kg" / "cases"


def _read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class CaseRepository:
    def __init__(self, cases_dir=None, embedding_model=None):
        self.cases_dir = Path(cases_dir) if cases_dir else CASES_DIR
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        self.cases_file = self.cases_dir / "cases.jsonl"
        self.success_dir = self.cases_dir / "success"
        self.failure_dir = self.cases_dir / "failure"
        self._embedding_model = embedding_model  # 惰性加载，避免无谓占用显存

    def _embedding(self):
        if self._embedding_model is None:
            self._embedding_model = EmbeddingModel()
        return self._embedding_model

    # ------------------------------------------------------------------ #
    # metadata store
    # ------------------------------------------------------------------ #
    def _load_cases(self):
        return _read_jsonl(self.cases_file)

    def add_case(self, case):
        """幂等：case_id 已存在则不重复加入。返回 case_id 或 None。"""
        case = dict(case)
        cid = case.get("case_id", "")
        if not cid:
            return None
        if self.get_case(cid) is not None:
            return None
        with open(self.cases_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
        return cid

    def get_case(self, case_id):
        for c in self._load_cases():
            if c.get("case_id") == case_id:
                return c
        return None

    def list_cases(self, case_type=None, case_status=None):
        out = []
        for c in self._load_cases():
            if case_type and c.get("case_type") != case_type:
                continue
            if case_status and c.get("case_status") != case_status:
                continue
            out.append(c)
        return out

    def deprecate(self, case_id):
        cases = self._load_cases()
        found = False
        for c in cases:
            if c.get("case_id") == case_id:
                c["case_status"] = "deprecated"
                found = True
        if found:
            with open(self.cases_file, "w", encoding="utf-8") as f:
                for c in cases:
                    f.write(json.dumps(c, ensure_ascii=False, default=str) + "\n")
        return found

    def count(self):
        return len(self._load_cases())

    # ------------------------------------------------------------------ #
    # 索引（只有 verified 进入）
    # ------------------------------------------------------------------ #
    def verified_cases(self):
        return [c for c in self._load_cases() if c.get("case_status") == "verified"]

    def rebuild_index(self):
        """从 verified cases 重建 success / failure 独立 FAISS 索引。返回 {success, failure} 数量。"""
        success = [c for c in self.verified_cases() if c.get("case_type") == "success"]
        failure = [c for c in self.verified_cases() if c.get("case_type") == "failure"]
        self._build_index(success, self.success_dir)
        self._build_index(failure, self.failure_dir)
        return {"success": len(success), "failure": len(failure)}

    def _build_index(self, cases, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        # 清空旧文件，避免残留索引被 retriever 读到
        for name in ("embeddings.npy", "metadata.json", "faiss.index"):
            p = out_dir / name
            if p.exists():
                p.unlink()
        if not cases:
            with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump([], f)
            return
        emb = self._embedding()
        texts = [c.get("embedding_text") or self._fallback_text(c) for c in cases]
        vecs = []
        for t in texts:
            v = np.asarray(emb.encode(t), dtype="float32").reshape(1, -1)
            vecs.append(v)
        mat = np.vstack(vecs).astype("float32")
        faiss.normalize_L2(mat)
        idx = faiss.IndexFlatIP(mat.shape[1])
        idx.add(mat)
        faiss.write_index(idx, str(out_dir / "faiss.index"))
        np.save(str(out_dir / "embeddings.npy"), mat)
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, default=str, indent=2)

    @staticmethod
    def _fallback_text(c):
        a = (c.get("reviewed_assertion") or c.get("incorrect_output")
             or c.get("original_assertion") or {})
        return (f"{c.get('task_type','')} {c.get('source_text','')} "
                f"{a.get('predicate','')} {a.get('subject_label','')} {a.get('object_label','')}")

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def get_case_statistics(self):
        cases = self._load_cases()
        stats = {"success_verified": 0, "failure_verified": 0, "pending": 0,
                 "deprecated": 0, "test": 0, "total": len(cases)}
        for c in cases:
            ct = c.get("case_type")
            cs = c.get("case_status")
            if cs == "verified":
                if ct == "success":
                    stats["success_verified"] += 1
                elif ct == "failure":
                    stats["failure_verified"] += 1
            elif cs == "pending":
                stats["pending"] += 1
            elif cs == "deprecated":
                stats["deprecated"] += 1
            elif cs == "test":
                stats["test"] += 1
        return stats
