#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Human Review CLI：逐条人工审核 Candidate Assertion。

操作：[a] approve  [r] reject  [m] modify  [s] skip  [q] quit

规则（八 / 三十三 / 三十二）：
- approve：review_comment 可选
- reject ：error_type + review_comment 必填
- modify ：corrected_assertion + error_type + review_comment 必填
- skip   ：不生成 Case
- 每次决策记录 review_started_at / review_finished_at / review_duration_seconds

提交后自动 Review -> CaseBuilder -> CaseRepository（approved=Success，rejected/modified=Failure）。
"""
import time
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.review_models import ERROR_TAXONOMY
from core.kg.review_manager import ReviewManager
from core.kg.case_builder import CaseBuilder
from core.kg.case_repository import CaseRepository


def now():
    return datetime.now().isoformat(timespec="seconds")


def make_review_id(assertion_id):
    return f"REV_{assertion_id}_{int(time.time() * 1000000)}"


def read_line(prompt=""):
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"  # 非交互 / EOF 视为 quit


def display_assertion(a, remaining):
    line = "=" * 78
    print(line)
    print(f"Assertion ID : {a.get('assertion_id','')}")
    print(f"原始文档      : {a.get('source_doc_id','')}")
    print(f"Chunk        : {a.get('source_chunk_id','')}")
    print(f"章节          : {a.get('section','') or '(无)'}")
    print(f"页码          : {a.get('page_start','')}-{a.get('page_end','')}")
    print(f"原文证据      : {a.get('source_text_quote','')}")
    print("-" * 78)
    print(f"Subject      : {a.get('subject_label','')}")
    print(f"  类型        : {a.get('subject_type','')}")
    print(f"  Canonical ID: {a.get('subject_id','')}")
    print(f"Predicate    : {a.get('predicate','')}")
    print(f"Object       : {a.get('object_label','')}")
    print(f"  类型        : {a.get('object_type','')}")
    if a.get('object_kind') == 'entity':
        print(f"  Canonical ID: {a.get('object_id','')}")
    print(f"Confidence   : {a.get('confidence','')}")
    print(f"Validation   : {a.get('validation_status','')}")
    print("-" * 78)
    print(f"（剩余 {remaining} 条待审核）")


def prompt_error_type():
    print("错误类型（输入编号或名称）:")
    for i, e in enumerate(ERROR_TAXONOMY, 1):
        print(f"  {i:2d}. {e}")
    while True:
        s = read_line("error_type > ").strip()
        if s == "q":
            return None
        if s.isdigit():
            n = int(s)
            if 1 <= n <= len(ERROR_TAXONOMY):
                return ERROR_TAXONOMY[n - 1]
        elif s in ERROR_TAXONOMY:
            return s
        print("  无效，请重试")


def prompt_comment():
    return read_line("review_comment > ").strip()


def prompt_modify(original):
    print("修改字段（留空保留原值）:")
    corrected = dict(original)
    for field in ("subject_label", "subject_type", "predicate", "object_label", "object_type"):
        cur = corrected.get(field, "")
        s = read_line(f"  {field} [{cur}] > ").strip()
        if s:
            corrected[field] = s
    for field in ("subject_id", "object_id"):
        cur = corrected.get(field, "")
        s = read_line(f"  {field} [{cur}] > ").strip()
        if s:
            corrected[field] = s
    return corrected


def main():
    mgr = ReviewManager()
    builder = CaseBuilder()
    repo = CaseRepository()  # embedding 惰性加载
    pending = mgr.get_pending()
    if not pending:
        print("没有待审核的 assertion。请先运行 scripts/kg/init_review_queue.py。")
        return

    added_verified = False
    n_done = 0
    while True:
        pending = mgr.get_pending()
        if not pending:
            break
        a = pending[0]
        display_assertion(a, len(pending))

        started = now()
        t0 = time.time()
        while True:
            cmd = read_line("[a]pprove [r]eject [m]odify [s]kip [q]uit > ").lower()
            if cmd in ("a", "r", "m", "s", "q"):
                break
            print("  请输入 a / r / m / s / q")
        if cmd == "q":
            break

        finished = now()
        duration = round(time.time() - t0, 2)
        decision = {"a": "approved", "r": "rejected", "m": "modified", "s": "skipped"}[cmd]

        corrected = None
        error_type = ""
        comment = ""
        cancelled = False
        if cmd == "r":
            error_type = prompt_error_type()
            comment = prompt_comment()
            if not error_type or not comment:
                print("  reject 需要 error_type + review_comment，本条已取消（保留在 pending）")
                cancelled = True
        elif cmd == "m":
            corrected = prompt_modify(a)
            error_type = prompt_error_type()
            comment = prompt_comment()
            if not error_type or not comment:
                print("  modify 需要 corrected_assertion + error_type + review_comment，本条已取消（保留在 pending）")
                cancelled = True

        if cancelled:
            continue

        rec = {
            "review_id": make_review_id(a.get("assertion_id", "")),
            "assertion_id": a.get("assertion_id", ""),
            "decision": decision,
            "original_assertion": a,
            "corrected_assertion": corrected,
            "error_type": error_type,
            "review_comment": comment,
            "reviewed_by": "human",
            "reviewed_at": finished,
            "review_started_at": started,
            "review_finished_at": finished,
            "review_duration_seconds": duration,
            "source_doc_id": a.get("source_doc_id", ""),
            "source_chunk_id": a.get("source_chunk_id", ""),
            "schema_version": a.get("schema_version", ""),
            "review_version": "v0.2",
            "test_only": False,
        }
        mgr.submit_review(rec)

        case = builder.build_from_review(rec)
        if case is not None:
            cid = repo.add_case(case)
            if cid and case.get("case_status") == "verified":
                added_verified = True
            print(f"  -> {decision} 完成，case_id={cid or '(重复跳过)'}")
        else:
            print(f"  -> {decision} 完成（skip，不生成 Case）")
        n_done += 1

    # 结束：若产生了 verified case，重建一次索引（一次性）
    if added_verified:
        try:
            r = repo.rebuild_index()
            print(f"索引已重建: success={r['success']} failure={r['failure']}")
        except Exception as e:
            print(f"（警告）索引重建失败: {e}")

    print("审核会话结束。")
    stats = mgr.get_review_statistics()["counts"]
    print(f"统计: pending={stats['pending']} approved={stats['approved']} "
          f"rejected={stats['rejected']} modified={stats['modified']} skipped={stats['skipped']}")
    cstats = repo.get_case_statistics()
    print(f"Case: success_verified={cstats['success_verified']} "
          f"failure_verified={cstats['failure_verified']} test={cstats['test']} "
          f"deprecated={cstats['deprecated']} total={cstats['total']}")


if __name__ == "__main__":
    main()
