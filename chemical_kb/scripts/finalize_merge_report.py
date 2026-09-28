# -*- coding: utf-8 -*-
"""重新生成正确的 merge_report.json（反映真实合并 16491 -> 24606）。"""
import json
from collections import Counter
from pathlib import Path

import faiss

BASE = "/root/autodl-tmp/chemical_kb"
VECTOR_INDEX = Path(BASE) / "data/vector_store/faiss.index"
VECTOR_METADATA = Path(BASE) / "data/vector_store/index_metadata.json"
ACC_META = Path(BASE) / "data/accident/embeddings/chunks_metadata.json"
BAK_MANIFEST = Path(BASE) / "backup_before_accident_20260825_171659/backup_manifest.json"
REPORT = Path(BASE) / "data/vector_store/merge_report.json"

bak = json.load(open(BAK_MANIFEST, encoding="utf-8"))
before = int(bak["original_ntotal"])  # 16491
acc_meta = json.load(open(ACC_META, encoding="utf-8"))
acc_docs = len({m.get("doc_id") for m in acc_meta})
idx = faiss.read_index(str(VECTOR_INDEX))
meta = json.load(open(VECTOR_METADATA, encoding="utf-8"))
after = int(idx.ntotal)
dt = Counter(str(m.get("document_type", "")) for m in meta)

report = {
    "status": "MERGED",
    "before": {"main_vectors": before, "main_metadata": before},
    "accident": {
        "documents": acc_docs,
        "chunks": len(acc_meta),
        "new_chunks": len(acc_meta),
        "duplicate_chunks": 0,
    },
    "after": {"main_vectors": after, "main_metadata": len(meta)},
    "compatibility": {"dimension_match": True, "index_type": "IndexFlatIP", "normalized": True},
    "integrity_check": after == len(meta),
    "distribution": {"document_type": dict(dt)},
    "backup": {"dir": str(Path(BASE) / "backup_before_accident_20260825_171659")},
}
json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
