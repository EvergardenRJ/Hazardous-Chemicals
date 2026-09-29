#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch semantic review of source-grounded KG candidates in corpus.sqlite.

Writes audit decisions to SQLite. It does not publish assertions to the live graph.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
DB=ROOT/'data/kg/batch_extraction/corpus.sqlite'
META=ROOT/'data/vector_store/index_metadata.json'
SCHEMA=ROOT/'data/kg/schema_v1.json'
SCHEMA_DATA=json.loads(SCHEMA.read_text(encoding='utf-8'))
RELATIONS={r['id']:r for r in SCHEMA_DATA.get('relation_types',[])}
ATTRIBUTES={(e['id'],a['name']):a for e in SCHEMA_DATA.get('entity_types',[]) for a in e.get('attributes',[])}
SYSTEM='你是化工安全知识图谱关系审核员。只依据提供的原文判断每条断言的主客体、关系方向和数值是否被原文直接支持。只输出严格 JSON，不补充解释。'


def connect(path):
    db=sqlite3.connect(path,timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS candidate_audits (
      assertion_id TEXT PRIMARY KEY, chunk_id TEXT NOT NULL,
      decision TEXT NOT NULL, reason TEXT NOT NULL,
      reviewed_at TEXT NOT NULL, reviewer TEXT NOT NULL DEFAULT 'adamin',
      method TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS candidate_audits_chunk ON candidate_audits(chunk_id)')
    db.commit()
    return db


def save(db,aid,chunk_id,decision,reason,method):
    with db:
        db.execute('INSERT OR REPLACE INTO candidate_audits VALUES(?,?,?,?,?, ?, ?)',
                   (aid,chunk_id,decision,str(reason)[:500],
                    datetime.now(timezone.utc).isoformat(timespec='seconds'),'adamin',method))


def make_prompt(text,items):
    compact=[]
    for i,a in enumerate(items,1):
        compact.append({'i':i,'subject':a.get('subject_label'),'subject_type':a.get('subject_type'),
                        'predicate':a.get('predicate'),'object':a.get('object_label'),
                        'object_type':a.get('object_type'),'quote':a.get('source_text_quote')})
    predicates={a.get('predicate') for a in items}
    definitions=[]
    for predicate in sorted(p for p in predicates if p):
        relation=RELATIONS.get(predicate)
        if relation:
            definitions.append({'predicate':predicate,'meaning':relation.get('description') or relation.get('name'),
                                'subject_type':relation.get('domain'),'object_type':relation.get('range')})
        else:
            for subject_type in sorted({a.get('subject_type') for a in items if a.get('predicate')==predicate and a.get('subject_type')}):
                attribute=ATTRIBUTES.get((subject_type,predicate))
                if attribute:
                    definitions.append({'predicate':predicate,'meaning':attribute.get('description') or predicate,
                                        'subject_type':subject_type,'object_type':'literal'})

    return ('【关系定义，箭头从主语指向宾语】\n'+json.dumps(definitions,ensure_ascii=False)+
            '\n【原文片段】\n'+text+'\n【候选断言】\n'+json.dumps(compact,ensure_ascii=False)+
            '\n逐条检查：主语、宾语、谓词方向、限定条件和数值须由原文支持；结果 decision 只能是 valid、reject、uncertain。'
            '原文无法确定则 uncertain，不要猜测。输出格式：{"results":[{"i":1,"decision":"valid","reason":"简短理由"}]}。')


def parse_result(raw,items):
    from core.kg.extractor import parse_llm_json
    obj,_=parse_llm_json(raw)
    answers={}
    if isinstance(obj,dict):
        for row in obj.get('results',[]):
            if not isinstance(row,dict): continue
            try: index=int(row.get('i'))
            except (ValueError,TypeError): continue
            if 1<=index<=len(items) and index not in answers:
                decision=str(row.get('decision','')).lower()
                if decision not in ('valid','reject','uncertain'): decision='uncertain'
                answers[index]=(decision,str(row.get('reason') or '模型未提供理由'))
    return [answers.get(i,('uncertain','模型未返回此条判定')) for i in range(1,len(items)+1)]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,default=DB)
    p.add_argument('--metadata',type=Path,default=META)
    p.add_argument('--batch-size',type=int,default=4,help='Number of review prompts per GPU batch')
    p.add_argument('--items-per-prompt',type=int,default=10)
    p.add_argument('--limit-prompts',type=int,default=0)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--static-only',action='store_true',help='Run schema and evidence checks without using GPU')
    args=p.parse_args()
    db=connect(args.db)
    texts={r['chunk_id']:str(r.get('text') or '') for r in json.loads(args.metadata.read_text(encoding='utf-8'))}
    rows=db.execute('''SELECT a.assertion_id,a.chunk_id,a.validation_status,a.evidence_ok,a.payload
        FROM assertions a LEFT JOIN candidate_audits v ON a.assertion_id=v.assertion_id
        WHERE v.assertion_id IS NULL ORDER BY a.chunk_id,a.assertion_id''').fetchall()
    ready=defaultdict(list)
    static=[]
    for aid,cid,status,evidence,payload in rows:
        if status!='passed':
            static.append((aid,cid,'needs_review','schema 校验未通过'))
        elif not evidence:
            static.append((aid,cid,'needs_review','来源引句未能在片段中按顺序定位'))
        else:
            ready[cid].append((aid,json.loads(payload)))
    prompts=[]
    for cid,items in ready.items():
        for offset in range(0,len(items),max(1,args.items_per_prompt)):
            part=items[offset:offset+max(1,args.items_per_prompt)]
            prompts.append((cid,part,make_prompt(texts.get(cid,''),[a for _,a in part])))
    print('unaudited',len(rows),'static_flags',len(static),'semantic_prompts',len(prompts),flush=True)
    if args.dry_run: return
    for aid,cid,decision,reason in static:
        save(db,aid,cid,decision,reason,'deterministic')
    if args.static_only:
        print('static_audit_totals',db.execute('SELECT decision,COUNT(*) FROM candidate_audits GROUP BY decision').fetchall(),flush=True)
        return
    if args.limit_prompts: prompts=prompts[:args.limit_prompts]
    if not prompts: return
    from core.llm import QwenLLM
    model=QwenLLM()
    size=max(1,args.batch_size)
    for offset in range(0,len(prompts),size):
        group=prompts[offset:offset+size]
        t=time.monotonic()
        try:
            raws=model.generate_batch([x[2] for x in group],system_prompt=SYSTEM,
                                      max_new_tokens=1600,temperature=0.1)
            if len(raws)!=len(group): raise RuntimeError('batch response count mismatch')
        except Exception as exc:
            print('batch error',repr(exc),'retrying separately',flush=True)
            raws=[]
            for _,_,prompt in group:
                try: raws.append(model.generate(prompt,system_prompt=SYSTEM,max_new_tokens=1600,temperature=0.1))
                except Exception: raws.append('')
        for (cid,part,_),raw in zip(group,raws):
            for (aid,_),(decision,reason) in zip(part,parse_result(raw,[a for _,a in part])):
                save(db,aid,cid,decision,reason,'llm-semantic-v1')
        print('prompts',offset+len(group),'/',len(prompts),'seconds',round(time.monotonic()-t,1),flush=True)
    print('audit_totals',db.execute('SELECT decision,COUNT(*) FROM candidate_audits GROUP BY decision').fetchall(),flush=True)

if __name__=='__main__': main()
