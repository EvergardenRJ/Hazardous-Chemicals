#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Case Repository 闭环测试（只用 test_only cases，不污染正式 data/kg/cases/）。

验证：
1. Review -> CaseBuilder（approved/rejected/modified/skip）
2. CaseRepository metadata + 幂等 + count + 统计
3. test_only（case_status=test）不进入 verified index
4. 无 verified Case 时 Retriever 返回空（正确行为）
5. 用合成 verified case（仅隔离测试目录）验证 embedding + FAISS + retriever 机制
6. prompt formatter
"""
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import BASE_DIR
from core.embedding import EmbeddingModel
from core.kg.case_builder import CaseBuilder
from core.kg.case_repository import CaseRepository
from core.kg.case_retriever import CaseRetriever, format_success_cases, format_failure_cases

TEST_DIR = BASE_DIR / "data" / "kg" / "cases_test"
VERIFIED_TEST_DIR = BASE_DIR / "data" / "kg" / "cases_verified_test"


def make_assertion(aid, predicate, object_label):
    return {
        "assertion_id": aid,
        "subject_id": "accident::TEST_ACC",
        "subject_type": "accident",
        "subject_label": "氯气泄漏事故",
        "predicate": predicate,
        "object_id": f"causal_factor::{object_label}::TEST_ACC",
        "object_type": "causal_factor",
        "object_label": object_label,
        "object_kind": "entity",
        "source_doc_id": "TEST_ACC",
        "source_chunk_id": "TEST_ACC_c0001",
        "source_text_quote": "液氯充装作业导致人员中毒",
        "source_type": "事故",
        "page_start": "1", "page_end": "1", "section": "直接原因",
        "schema_version": "1.0",
        "confidence": 0.5,
        "review_status": "pending",
        "validation_status": "passed",
        "created_at": "2026-08-26T00:00:00",
    }


def main():
    results = []  # (name, passed, detail)

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}  {detail}")

    # 清理测试目录
    for d in (TEST_DIR, VERIFIED_TEST_DIR):
        if d.exists():
            shutil.rmtree(d)

    print("== 1. Review -> CaseBuilder ==")
    a1 = make_assertion("TEST_A001", "involves_chemical", "氯")
    a2 = make_assertion("TEST_A002", "direct_cause", "中毒")
    a3 = make_assertion("TEST_A003", "direct_cause", "中毒")
    corrected3 = dict(a3)
    corrected3["predicate"] = "indirect_cause"

    recs = [
        dict(review_id="REV_T1", assertion_id="TEST_A001", decision="approved",
             original_assertion=a1, test_only=True),
        dict(review_id="REV_T2", assertion_id="TEST_A002", decision="rejected",
             original_assertion=a2, error_type="relation_type_error",
             review_comment="中毒是后果不是直接原因", test_only=True),
        dict(review_id="REV_T3", assertion_id="TEST_A003", decision="modified",
             original_assertion=a3, corrected_assertion=corrected3,
             error_type="relation_type_error", review_comment="应为间接原因", test_only=True),
    ]
    builder = CaseBuilder()
    cases = [builder.build_from_review(r) for r in recs]
    check("approved -> Success Case", cases[0]["case_type"] == "success" and cases[0]["case_status"] == "test")
    check("rejected -> Failure Case", cases[1]["case_type"] == "failure" and cases[1]["case_status"] == "test")
    check("modified -> Failure(incorrect+corrected)",
          cases[2]["incorrect_output"]["predicate"] == "direct_cause"
          and cases[2]["corrected_output"]["predicate"] == "indirect_cause")
    skip_rec = dict(review_id="REV_T4", assertion_id="TEST_A004", decision="skipped",
                    original_assertion=a1, test_only=True)
    check("skip -> 不生成 Case", builder.build_from_review(skip_rec) is None)

    print("== 2. CaseRepository metadata + 幂等 ==")
    repo = CaseRepository(cases_dir=TEST_DIR)
    for c in cases:
        assert repo.add_case(c), "add_case 应返回 case_id"
    check("add_case 返回 case_id", True)
    check("幂等：重复 add 返回 None", repo.add_case(cases[0]) is None)
    check("count == 3", repo.count() == 3, f"count={repo.count()}")
    st = repo.get_case_statistics()
    check("统计 test=3 verified=0", st["test"] == 3 and st["success_verified"] == 0 and st["failure_verified"] == 0, str(st))

    print("== 3. test_only 不进 verified index ==")
    r = repo.rebuild_index()
    check("rebuild_index 后 verified 索引为空", r == {"success": 0, "failure": 0}, str(r))

    print("== 4. 无 verified Case 时 Retriever 返回空 ==")
    ret = CaseRetriever(repository=repo)
    res = ret.retrieve("液氯充装导致人员中毒", "accident", "事故")
    check("success/failure 均返回空", res["success_cases"] == [] and res["failure_cases"] == [])

    print("== 5. 合成 verified case 验证 embedding+FAISS+retriever 机制（隔离目录）==")
    try:
        repo2 = CaseRepository(cases_dir=VERIFIED_TEST_DIR)
        vsuccess = dict(cases[0]); vsuccess["case_status"] = "verified"; vsuccess["case_id"] = "C_TEST_VS"
        vfail = dict(cases[1]); vfail["case_status"] = "verified"; vfail["case_id"] = "C_TEST_VF"
        repo2.add_case(vsuccess)
        repo2.add_case(vfail)
        emb = EmbeddingModel()
        repo2._embedding_model = emb
        r2 = repo2.rebuild_index()
        check("rebuild_index success=1 failure=1", r2 == {"success": 1, "failure": 1}, str(r2))
        ret2 = CaseRetriever(repository=repo2, embedding_model=emb)
        res2 = ret2.retrieve("液氯充装导致人员中毒", "accident", "事故")
        ok = (len(res2["success_cases"]) == 1 and len(res2["failure_cases"]) == 1
              and res2["success_cases"][0]["case_type"] == "success"
              and res2["failure_cases"][0]["case_type"] == "failure")
        check("Success/Failure 分开检索", ok,
              f"success={len(res2['success_cases'])} failure={len(res2['failure_cases'])}")
        hit = res2["success_cases"][0]
        check("记录 raw_similarity/final_score/ranking_reasons",
              all(k in hit for k in ("raw_similarity", "final_score", "ranking_reasons")))

        print("== 6. Prompt formatter ==")
        fs = format_success_cases(res2["success_cases"])
        ff = format_failure_cases(res2["failure_cases"])
        check("Success 格式", "Previous Verified Success" in fs and "human approved" in fs)
        check("Failure 明确负例", "Previous Verified Failure" in ff and "Do NOT copy" in ff)
    except Exception as e:
        check("embedding 机制（可能缺 GPU/模型）", False, repr(e))

    # 清理隔离测试目录
    for d in (TEST_DIR, VERIFIED_TEST_DIR):
        if d.exists():
            shutil.rmtree(d)

    print("\n== 汇总 ==")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [n for n, ok, _ in results if not ok]
    print(f"  {passed}/{len(results)} 通过")
    if failed:
        print("  失败项:", failed)
        sys.exit(1)
    print("  全部通过")


if __name__ == "__main__":
    main()
