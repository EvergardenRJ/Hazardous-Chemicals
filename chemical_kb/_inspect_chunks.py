#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inspect chunk JSONL files: search by keyword, print metadata + optional full text."""
import json
import sys


def main():
    if len(sys.argv) < 3:
        print("usage: inspect_chunks.py <file> <keyword> [--full] [--limit N]")
        return
    path = sys.argv[1]
    kw = sys.argv[2]
    full = "--full" in sys.argv
    limit = 100
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        elif a.startswith("--limit="):
            limit = int(a.split("=")[1])
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or kw not in line:
                continue
            obj = json.loads(line)
            cid = obj.get("chunk_id", "")
            title = obj.get("title", "")
            section = obj.get("section", "")
            ps = obj.get("page_start", obj.get("page", ""))
            pe = obj.get("page_end", "")
            text = obj.get("text", "")
            dt = obj.get("document_type", obj.get("doc_type", ""))
            code = obj.get("code", "")
            print("=" * 72)
            print("chunk_id:", cid)
            print("doc_id:", obj.get("doc_id", ""))
            print("document_type:", dt)
            print("code:", code)
            print("title:", title)
            print("section:", section)
            print("page:", ps, "-", pe)
            print("text_len:", len(text))
            if full:
                print("----TEXT----")
                print(text)
                print("----END----")
            else:
                print("snippet:", text[:160].replace("\n", " "))
            n += 1
            if n >= limit:
                break
    print("=" * 72)
    print("total matched:", n)


if __name__ == "__main__":
    main()
