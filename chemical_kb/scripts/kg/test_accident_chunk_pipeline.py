#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""事故 chunk 全链路测试：定位真实 chunk -> pipeline -> 打印 + 落盘。"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.pipeline import KGExtractionPipeline, save_candidate_layer
from core.kg.schema_retriever import SchemaRetriever

ACCIDENT_FILE = PROJECT_ROOT / "data" / "accident" / "chunks" / "chunks_accident.jsonl"
TARGET_CHUNK_ID = "ACC_aa76907ac753bc37_c0020"
TARGET_DOC_ID = "ACC_aa76907ac753bc37"


def locate_chunk(path, chunk_id=None, doc_id=None, section_kw=None):
    """按 chunk_id 精确匹配，否则按 doc_id+section 关键词兜底。"""
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
            if doc_id and doc_id in line and section_kw and section_kw in line:
                obj = json.loads(line)
                if obj.get("doc_id") == doc_id and section_kw in str(obj.get("section", "")):
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
    print(f"[Rule] section={ra['section']!r} death={ra['death_count']} injury={ra['injury_count']} "
          f"severe={ra['severe_injury_count']} missing={ra['missing_count']}")
    print(f"[Rule] standard_codes={ra['standard_codes']} cas={ra['cas_numbers']} dates={ra['dates']}")
    print(f"[Rule] modalities={ra['modalities']} quant={ra['quantitative_expressions']}")

    sc = res.get("schema_context") or {}
    print("[Schema Retriever]")
    print("  entities:", [f"{e['name']}({e['name_zh']})" for e in sc.get("entities", [])])
    print("  relations:", [f"{x['name']}({x['name_zh']})" for x in sc.get("relations", [])])

    draft = res["extraction_draft"]
    print(f"[Extractor] status={draft['status']} parse_method={draft['parse_method']} "
          f"retry={draft['retry_used']}")
    print("  entity_mentions:")
    for m in draft["entity_mentions"]:
        print(f"    {m.get('mention_id')}: {m.get('surface')}  type_hint={m.get('type_hint')}  state={m.get('physical_state')}")
    print("  relation_phrases:")
    for rp in draft["relation_phrases"]:
        print(f"    {rp.get('relation_id')}: {rp.get('subject_mention_id')} -[{rp.get('predicate_surface')}]-> {rp.get('object_mention_id')}")
    print("  attribute_mentions:", draft["attribute_mentions"])

    print("[Definer]")
    for d in res["define_results"]:
        print(f"    {d['relation_id']}: 「{d['predicate_surface']}」 -> {d['schema_relation'] or 'UNRESOLVED'} "
              f"(dir={d['direction']}, status={d['status']})")

    print("[Canonicalizer]")
    for c in res["canonical_results"]:
        print(f"    {c['mention_id']}: {c['surface']} -> {c['entity_type']} | {c['canonical_id']} "
              f"({c['canonical_status']}/{c['match_level']})")

    print("[Assertions]")
    for a in res["assertions"]:
        flag = "OK " if a["validation_status"] == "passed" else "FAIL"
        print(f"    [{flag}] {a['assertion_id']}: {a['subject_id']} ({a['subject_type']}) "
              f"-[{a['predicate']}]-> {a['object_id']} ({a['object_type'] if a['object_kind']=='entity' else 'literal'})")
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
    chunk = locate_chunk(ACCIDENT_FILE, chunk_id=TARGET_CHUNK_ID,
                         doc_id=TARGET_DOC_ID, section_kw="直接原因")
    if chunk is None:
        print("!! 未找到目标事故 chunk，尝试任意含「直接原因」的 chunk")
        chunk = locate_chunk(ACCIDENT_FILE, doc_id=TARGET_DOC_ID, section_kw="直接原因")
    if chunk is None:
        print("!! 仍未找到，退出")
        sys.exit(1)

    print("== 加载 SchemaRetriever + Pipeline ==")
    retriever = SchemaRetriever()
    pipeline = KGExtractionPipeline(retriever=retriever, verbose=True)

    print("== 运行全链路 ==")
    res = pipeline.process_chunk(chunk)

    print_result(res)

    print("\n== 落盘候选层 ==")
    files = save_candidate_layer(res, prefix="accident_")
    for name, p in files.items():
        print(f"  {name}: {p}")

    print("\n== parse_stats ==", pipeline.parse_stats)


if __name__ == "__main__":
    main()
