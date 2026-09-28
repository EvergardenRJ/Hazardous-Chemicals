#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调试：dump 标准 chunk 的 raw LLM 输出，定位抽取失败原因。"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.document_router import DocumentRouter
from core.kg.rule_extractor import RuleExtractor
from core.kg.extractor import Extractor, parse_llm_json, EXTRACTION_SYSTEM_PROMPT

STANDARD_FILE = PROJECT_ROOT / "data" / "chunks" / "chunks_v2.jsonl"
TARGET_CHUNK_ID = "STD_DB32_T_3617_2019_p6_c6"


def main():
    chunk = None
    with open(STANDARD_FILE, encoding="utf-8") as f:
        for line in f:
            if TARGET_CHUNK_ID in line:
                chunk = json.loads(line)
                if chunk.get("chunk_id") == TARGET_CHUNK_ID:
                    break
    print("chunk_id:", chunk.get("chunk_id"))
    print("text_len:", len(chunk.get("text", "")))

    router = DocumentRouter()
    doc_type = router.route(chunk)
    print("doc_type:", doc_type)

    text = chunk.get("text", "")
    ra = RuleExtractor().extract(text, chunk, doc_type)
    print("rule clauses:", ra.clause_numbers)
    print("rule modalities:", ra.modalities)

    ext = Extractor()
    prompt = ext._build_prompt(text, doc_type, ra, None)
    print("\n===== PROMPT (last 300 chars) =====")
    print(prompt[-300:])

    raw = ext.llm.generate(prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT,
                           max_new_tokens=2048, temperature=0.2)
    print("\n===== RAW LLM OUTPUT (len=%d) =====" % len(raw))
    print(raw[:3000])
    print("\n===== parse result =====")
    obj, method = parse_llm_json(raw)
    print("method:", method)
    if obj is None:
        print("PARSE FAILED")
    else:
        print("keys:", list(obj.keys()))
        print("clause_mentions:", len(obj.get("clause_mentions", [])))
        print("requirement_candidates:", len(obj.get("requirement_candidates", [])))
        print("entity_mentions:", len(obj.get("entity_mentions", [])))


if __name__ == "__main__":
    main()
