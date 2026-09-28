#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""标准 chunk 全链路测试：定位真实 chunk -> pipeline -> 打印 + 落盘。"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.pipeline import KGExtractionPipeline, save_candidate_layer
from core.kg.schema_retriever import SchemaRetriever

STANDARD_FILE = PROJECT_ROOT / "data" / "chunks" / "chunks_v2.jsonl"
TARGET_CHUNK_ID = "STD_DB32_T_3617_2019_p6_c6"
TARGET_DOC_ID = "STD_DB32_T_3617_2019"


def locate_chunk(path, chunk_id=None, doc_id=None, text_kw=None):
    fallback = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if chunk_id and chunk_id in line:
                obj = json.loads(line)
                if obj.get("chunk_id") == chunk_id:
                    return obj
            if doc_id and doc_id in line and text_kw and text_kw in line:
                obj = json.loads(line)
                if obj.get("doc_id") == doc_id and text_kw in str(obj.get("text", "")):
                    if fallback is None:
                        fallback = obj
    return fallback


def print_result(res):
    print("=" * 78)
    print(f"chunk_id    : {res['chunk_id']}")
    print(f"doc_id      : {res['doc_id']}   doc_type(路由)={res['doc_type']}")
    print(f"title       : {res['title']}")
    print(f"code        : {res['code']}")
    print(f"section     : {res['section']}   page={res['page_start']}-{res['page_end']}")
    print(f"status      : {res['status']}")
    print("-" * 78)
    print(f"[原文] {res['text']}")
    print("-" * 78)

    ra = res["rule_annotations"]
    print(f"[Rule] clause_numbers={ra['clause_numbers']}")
    print(f"[Rule] modalities={ra['modalities']} quant={ra['quantitative_expressions']}")
    print(f"[Rule] standard_codes={ra['standard_codes']}")

    sc = res.get("schema_context") or {}
    print("[Schema Retriever]")
    print("  entities:", [f"{e['name']}({e['name_zh']})" for e in sc.get("entities", [])])
    print("  relations:", [f"{x['name']}({x['name_zh']})" for x in sc.get("relations", [])])

    draft = res["extraction_draft"]
    print(f"[Extractor] status={draft['status']} parse_method={draft['parse_method']} "
          f"retry={draft['retry_used']}")
    print("  entity_mentions:")
    for m in draft["entity_mentions"]:
        print(f"    {m.get('mention_id')}: {m.get('surface')}  type_hint={m.get('type_hint')}")
    print("  clause_mentions:")
    for c in draft["clause_mentions"]:
        print(f"    {c.get('clause_id')}: [{c.get('clause_number')}] {c.get('text','')[:80]}")
    print("  requirement_candidates:")
    for r in draft["requirement_candidates"]:
        print(f"    {r.get('requirement_id')}: {r.get('modality')} {r.get('subject')} {r.get('action')} "
              f"{r.get('object')}  quant={r.get('quantitative_constraint')}")

    print("[Canonicalizer]")
    for c in res["canonical_results"]:
        print(f"    {c['mention_id']}: {c['surface']} -> {c['entity_type']} | {c['canonical_id']} "
              f"({c['canonical_status']})")

    print("[Assertions]")
    for a in res["assertions"]:
        flag = "OK " if a["validation_status"] == "passed" else "FAIL"
        objt = a["object_type"] if a["object_kind"] == "entity" else "literal"
        print(f"    [{flag}] {a['assertion_id']}: {a['subject_id']} ({a['subject_type']}) "
              f"-[{a['predicate']}]-> {a['object_id']} ({objt})")
        if a["validation_errors"]:
            for e in a["validation_errors"]:
                print(f"           err: {e}")

    v = res.get("validation")
    if v:
        print(f"[Validation] total={v['total']} passed={v['passed']} failed={v['failed']}")
    print("[Unresolved relations]", len(res["unresolved_relations"]))
    for u in res["unresolved_relations"]:
        print(f"    {u['predicate_surface']}: {u['subject_surface']} -> {u['object_surface']}")


def main():
    chunk = locate_chunk(STANDARD_FILE, chunk_id=TARGET_CHUNK_ID,
                         doc_id=TARGET_DOC_ID, text_kw="1.20kg/L")
    if chunk is None:
        print("!! 未找到目标标准 chunk，退出")
        sys.exit(1)

    print("== 加载 SchemaRetriever + Pipeline ==")
    retriever = SchemaRetriever()
    pipeline = KGExtractionPipeline(retriever=retriever, verbose=True)

    print("== 运行全链路 ==")
    res = pipeline.process_chunk(chunk)

    print_result(res)

    print("\n== 落盘候选层 ==")
    files = save_candidate_layer(res, prefix="standard_")
    for name, p in files.items():
        print(f"  {name}: {p}")

    print("\n== parse_stats ==", pipeline.parse_stats)


if __name__ == "__main__":
    main()
