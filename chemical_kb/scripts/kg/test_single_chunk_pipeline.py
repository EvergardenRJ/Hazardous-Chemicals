#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单 chunk 全链路测试（统一版）：定位一个真实 chunk -> EDC+R pipeline -> 打印 + 落盘。

用法：
  python scripts/kg/test_single_chunk_pipeline.py --chunk-id STD_DB32_T_3617_2019_p6_c6
  python scripts/kg/test_single_chunk_pipeline.py --chunk-id ACC_aa76907ac753bc37_c0020
  python scripts/kg/test_single_chunk_pipeline.py --file <path.jsonl> --chunk-id <id> [--prefix X_]

不传 --chunk-id 时默认跑标准 chunk（canonical demo）。
源文件按 chunk_id 前缀自动推断：ACC_ -> 事故，STD_/REG_ -> 标准法规。
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.pipeline import KGExtractionPipeline, save_candidate_layer
from core.kg.schema_retriever import SchemaRetriever

# 已知 chunk 源文件（可用 --file 覆盖）
DEFAULT_FILES = {
    "accident": PROJECT_ROOT / "data" / "accident" / "chunks" / "chunks_accident.jsonl",
    "standard": PROJECT_ROOT / "data" / "chunks" / "chunks_v2.jsonl",
    "regulation": PROJECT_ROOT / "data" / "chunks" / "chunks_v2.jsonl",
}

DEFAULT_CHUNK_ID = "STD_DB32_T_3617_2019_p6_c6"


def guess_doc_type(chunk_id):
    """按 chunk_id 前缀推断文档类型（用于选源文件 + 落盘前缀）。"""
    if chunk_id.startswith("ACC_"):
        return "accident"
    if chunk_id.startswith("STD_"):
        return "standard"
    if chunk_id.startswith("REG_"):
        return "regulation"
    return "unknown"


def guess_file(chunk_id):
    t = guess_doc_type(chunk_id)
    return DEFAULT_FILES.get(t)


def locate_chunk(path, chunk_id=None, doc_id=None, text_kw=None):
    """按 chunk_id 精确匹配；否则按 doc_id + 文本关键词兜底。"""
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
    print(f"[Rule] section={ra.get('section')!r} death={ra.get('death_count')} "
          f"injury={ra.get('injury_count')} missing={ra.get('missing_count')}")
    print(f"[Rule] clause_numbers={ra.get('clause_numbers')}")
    print(f"[Rule] modalities={ra.get('modalities')} quant={ra.get('quantitative_expressions')}")
    print(f"[Rule] standard_codes={ra.get('standard_codes')} cas={ra.get('cas_numbers')}")

    sc = res.get("schema_context") or {}
    print("[Schema Retriever]")
    print("  entities:", [f"{e['name']}({e['name_zh']})" for e in sc.get("entities", [])])
    print("  relations:", [f"{x['name']}({x['name_zh']})" for x in sc.get("relations", [])])

    draft = res["extraction_draft"]
    print(f"[Extractor] status={draft.get('status')} parse_method={draft.get('parse_method')} "
          f"retry={draft.get('retry_used')}")
    print("  entity_mentions:")
    for m in draft.get("entity_mentions", []):
        print(f"    {m.get('mention_id')}: {m.get('surface')}  type_hint={m.get('type_hint')}  state={m.get('physical_state')}")
    if draft.get("relation_phrases"):
        print("  relation_phrases:")
        for rp in draft["relation_phrases"]:
            print(f"    {rp.get('relation_id')}: {rp.get('subject_mention_id')} -[{rp.get('predicate_surface')}]-> {rp.get('object_mention_id')}")
    if draft.get("clause_mentions"):
        print("  clause_mentions:")
        for c in draft["clause_mentions"]:
            print(f"    {c.get('clause_id')}: [{c.get('clause_number')}] {c.get('text','')[:80]}")
    if draft.get("requirement_candidates"):
        print("  requirement_candidates:")
        for r in draft["requirement_candidates"]:
            print(f"    {r.get('requirement_id')}: {r.get('modality')} {r.get('subject')} "
                  f"{r.get('action')} {r.get('object')}  quant={r.get('quantitative_constraint')}")
    if draft.get("attribute_mentions"):
        print("  attribute_mentions:", draft["attribute_mentions"])

    if res.get("define_results"):
        print("[Definer]")
        for d in res["define_results"]:
            print(f"    {d['relation_id']}: 「{d['predicate_surface']}」 -> {d['schema_relation'] or 'UNRESOLVED'} "
                  f"(dir={d['direction']}, status={d['status']})")

    print("[Canonicalizer]")
    for c in res["canonical_results"]:
        print(f"    {c['mention_id']}: {c['surface']} -> {c['entity_type']} | {c['canonical_id']} "
              f"({c.get('canonical_status','')}/{c.get('match_level','')})")

    print("[Assertions]")
    for a in res["assertions"]:
        flag = "OK " if a["validation_status"] == "passed" else "FAIL"
        objt = a["object_type"] if a["object_kind"] == "entity" else "literal"
        print(f"    [{flag}] {a['assertion_id']}: {a['subject_id']} ({a['subject_type']}) "
              f"-[{a['predicate']}]-> {a['object_id']} ({objt})")
        if a.get("validation_errors"):
            for e in a["validation_errors"]:
                print(f"           err: {e}")

    v = res.get("validation")
    if v:
        print(f"[Validation] total={v.get('total')} passed={v.get('passed')} failed={v.get('failed')}")
    print("[Unresolved relations]", len(res["unresolved_relations"]))
    for u in res["unresolved_relations"]:
        print(f"    {u.get('predicate_surface')}: {u.get('subject_surface')} -> {u.get('object_surface')}")


def main():
    ap = argparse.ArgumentParser(description="单 chunk 全链路测试（EDC+R）")
    ap.add_argument("--chunk-id", default=None, help="目标 chunk_id，默认标准 demo")
    ap.add_argument("--file", default=None, help="源 JSONL 路径（默认按 chunk_id 前缀推断）")
    ap.add_argument("--prefix", default=None, help="落盘文件名前缀（默认 doc_type_）")
    args = ap.parse_args()

    chunk_id = args.chunk_id or DEFAULT_CHUNK_ID
    path = Path(args.file) if args.file else guess_file(chunk_id)
    if path is None or not path.exists():
        print(f"!! 无法定位源文件：{path}")
        print("   请用 --file 指定 chunk JSONL 路径。")
        sys.exit(1)

    print(f"== 源文件: {path}")
    print(f"== 目标 chunk_id: {chunk_id}")
    chunk = locate_chunk(path, chunk_id=chunk_id)
    if chunk is None:
        print("!! 未找到目标 chunk，退出")
        sys.exit(1)

    print("== 加载 SchemaRetriever + Pipeline ==")
    retriever = SchemaRetriever()
    pipeline = KGExtractionPipeline(retriever=retriever, verbose=True)

    print("== 运行全链路 ==")
    res = pipeline.process_chunk(chunk)

    print_result(res)

    prefix = args.prefix or (res["doc_type"] + "_")
    print(f"\n== 落盘候选层 (prefix={prefix}) ==")
    files = save_candidate_layer(res, prefix=prefix)
    for name, p in files.items():
        print(f"  {name}: {p}")

    print("\n== parse_stats ==", pipeline.parse_stats)


if __name__ == "__main__":
    main()
