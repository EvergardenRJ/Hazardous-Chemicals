import streamlit as st
import os
import sys
import json
import time
from datetime import datetime

# ==============================
# 项目路径
# ==============================
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)

from core.kg.review_manager import ReviewManager
from core.kg.review_models import ERROR_TAXONOMY
from core.kg.case_builder import CaseBuilder, assertion_to_str
from core.kg.case_repository import CaseRepository
from core.kg.schema_manager import SchemaManager
from core.kg.ai_reviewer import AIReviewer, get_ai_decision, override_ai_decision

from app._theme import apply_theme, page_header

apply_theme()

OUTPUT_DIR = os.path.join(ROOT_PATH, "data", "kg", "output")

_FORM_KEYS = ("m_slabel", "m_stype", "m_sid", "m_pred", "m_olabel", "m_otype", "m_oid",
              "m_et", "m_comment", "rej_et", "rej_comment")


# ==============================
# 缓存后端对象（st.cache_resource，避免每次 rerun 重新加载）
# ==============================
@st.cache_resource
def get_review_manager():
    return ReviewManager()


@st.cache_resource
def get_schema_manager():
    return SchemaManager()


@st.cache_resource
def get_case_builder():
    return CaseBuilder(schema_manager=get_schema_manager())


@st.cache_resource
def get_case_repository():
    # embedding 惰性加载，只在「更新 Case 索引」时加载 BGE-M3（且只加载一次）
    return CaseRepository()


@st.cache_resource
def get_ai_reviewer():
    # AI 预审器（Qwen3-4B），只在点击「AI预审核」时真正调用
    return AIReviewer()


# ==============================
# 只读数据加载（从 v0.1 落盘的 output 读 canonicalization / 标题 / unresolved）
# ==============================
@st.cache_data
def load_canonical_map():
    """canonical_id -> {surfaces, entity_type, physical_state, match_level, confidence}"""
    mapping = {}
    for prefix in ("accident", "standard"):
        p = os.path.join(OUTPUT_DIR, f"{prefix}_pipeline_result.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for c in data.get("canonical_results", []):
            cid = c.get("canonical_id", "")
            if not cid:
                continue
            entry = mapping.setdefault(cid, {
                "surfaces": [],
                "entity_type": c.get("entity_type", ""),
                "canonical_name": c.get("canonical_name", ""),
                "physical_state": c.get("physical_state"),
                "match_level": c.get("match_level", ""),
                "confidence": c.get("confidence", ""),
            })
            s = c.get("surface", "")
            if s and s not in entry["surfaces"]:
                entry["surfaces"].append(s)
    return mapping


@st.cache_data
def load_doc_titles():
    titles = {}
    for prefix in ("accident", "standard"):
        p = os.path.join(OUTPUT_DIR, f"{prefix}_pipeline_result.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        doc_id = data.get("doc_id", "")
        title = data.get("title", "") or data.get("code", "")
        if doc_id:
            titles[doc_id] = title
    return titles


@st.cache_data
def load_unresolved_relations():
    rows = []
    for prefix in ("accident", "standard"):
        p = os.path.join(OUTPUT_DIR, f"{prefix}_unresolved_relations.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    return rows


@st.cache_data
def load_chunk_text_map():
    """从向量库 metadata 恢复 chunk_id -> 完整 chunk 原文（一次性加载，缓存）。"""
    p = os.path.join(ROOT_PATH, "data", "vector_store", "index_metadata.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return {str(item.get("chunk_id", "")): item.get("text", "")
            for item in data if item.get("chunk_id")}


def _review_duration():
    t0 = st.session_state.get("review_t0")
    return round(time.time() - t0, 2) if t0 else 0.0


# ==============================
# 工具函数
# ==============================
def submit_review(assertion, decision, error_type="", comment="", corrected=None):
    """幂等提交：若 assertion 已不在 pending（被重复触发），则跳过。"""
    mgr = get_review_manager()
    builder = get_case_builder()
    repo = get_case_repository()

    pending_ids = {a.get("assertion_id") for a in mgr.get_pending()}
    if assertion.get("assertion_id") not in pending_ids:
        return None  # 已处理过，幂等跳过

    review_id = f"REV_{assertion.get('assertion_id','')}_{int(time.time() * 1000000)}"
    rec = {
        "review_id": review_id,
        "assertion_id": assertion.get("assertion_id", ""),
        "decision": decision,
        "original_assertion": assertion,
        "corrected_assertion": corrected,
        "error_type": error_type,
        "review_comment": comment,
        "reviewed_by": "human",
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "review_started_at": st.session_state.get("review_started_at", ""),
        "review_finished_at": datetime.now().isoformat(timespec="seconds"),
        "review_duration_seconds": _review_duration(),
        "source_doc_id": assertion.get("source_doc_id", ""),
        "source_chunk_id": assertion.get("source_chunk_id", ""),
        "schema_version": assertion.get("schema_version", ""),
        "review_version": "v0.3",
        "test_only": False,
    }
    mgr.submit_review(rec)
    case = builder.build_from_review(rec)
    if case is not None:
        repo.add_case(case)
    return case


def accept_ai(assertion, ai_rec):
    """把 AI 预审结论转化为人工审核动作（由人工点击，故仍是 human reviewed）。"""
    d = ai_rec.get("decision", "")
    if d == "ai_approved":
        submit_review(assertion, "approved")
    elif d == "ai_rejected":
        submit_review(assertion, "rejected", error_type="other",
                      comment=ai_rec.get("reason", "") or "AI 预审判定为拒绝")
    else:  # ai_uncertain：无法直接采纳，打开修改表单由人工修正
        st.session_state.action = "modify"
        clear_form_keys()
    st.rerun()


def render_entity(assertion, side, canon_map):
    """展示 subject / object 的实体映射：surface -> canonical_id / type / confidence / physical_state。"""
    label = assertion.get(f"{side}_label", "")
    cid = assertion.get(f"{side}_id", "")
    etype = assertion.get(f"{side}_type", "")
    entry = canon_map.get(cid)
    if entry:
        surfaces = " / ".join(entry["surfaces"]) if entry["surfaces"] else label
        st.markdown(
            f"- **surface**: {surfaces}\n"
            f"- **type**: {etype or entry['entity_type']}\n"
            f"- **canonical_id**: `{cid}`\n"
            f"- **confidence**: {entry['confidence']}\n"
            f"- **physical_state**: {entry['physical_state'] or '—'}\n"
            f"- **match_level**: {entry['match_level']}"
        )
    else:
        st.markdown(
            f"- **label**: {label}\n"
            f"- **type**: {etype}\n"
            f"- **canonical_id**: `{cid}`"
        )


def clear_form_keys():
    for k in _FORM_KEYS:
        st.session_state.pop(k, None)


# ==============================
# 初始化后端对象
# ==============================
mgr = get_review_manager()
sm = get_schema_manager()
repo = get_case_repository()
canon_map = load_canonical_map()
doc_titles = load_doc_titles()
unresolved = load_unresolved_relations()
chunk_text_map = load_chunk_text_map()

ENTITY_TYPES = sm.get_entity_types()
RELATION_TYPES = sm.get_relation_types()

page_header("🔬 KG Review Center", "Human Review + Case Repository —— 人工审核中心（不自动审核，只提供工具）")

# ==============================
# 顶部统计
# ==============================
review_stats = mgr.get_review_statistics()["counts"]
all_cases = repo.list_cases()
n_success = len([c for c in all_cases if c.get("case_type") == "success"])
n_failure = len([c for c in all_cases if c.get("case_type") == "failure"])

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Pending", review_stats["pending"])
c2.metric("Approved", review_stats["approved"])
c3.metric("Rejected", review_stats["rejected"])
c4.metric("Modified", review_stats["modified"])
c5.metric("Success Cases", n_success)
c6.metric("Failure Cases", n_failure)

st.divider()

tab_review, tab_cases, tab_unresolved = st.tabs(["🔍 审核", "📚 案例库", "⚠️ Unresolved / Schema 提案"])

# ==============================
# Tab 1: 审核
# ==============================
with tab_review:
    pending = mgr.get_pending()
    if not pending:
        st.info("✅ 没有待审核的 assertion。")
    else:
        # AI 预审（批量，可选；不改变 pending 状态，只写 ai_preview.jsonl 供人工参考）
        if st.button("🤖 [AI预审核] 批量预审 pending 队列", use_container_width=True, key="ai_batch"):
            with st.spinner("正在调用 Qwen3-4B 对 pending 断言做 AI 预审（不改变 pending 状态）..."):
                results = get_ai_reviewer().review_pending(save=True)
            n = len(results)
            if n:
                st.success(f"✅ AI 预审完成：新增 {n} 条（decision ∈ ai_approved / ai_rejected / ai_uncertain，仅供人工参考）")
            else:
                st.info("没有新增预审（所有 pending 均已预审过）")
            st.rerun()

        ids = [a.get("assertion_id", "") for a in pending]

        # 应用 pending 的「跳转」请求（在 selectbox 实例化之前，避免改 widget key 报错）
        if st.session_state.get("advance") is not None:
            st.session_state.sel_assertion = st.session_state.advance
            st.session_state.advance = None

        # 确保选择有效（提交后旧 id 不在 ids，自动回退到第一条 = 自动进入下一条）
        if st.session_state.get("sel_assertion") not in ids:
            st.session_state.sel_assertion = ids[0]

        sel_id = st.selectbox("选择待审核断言", ids, key="sel_assertion")

        # 切换断言时重置操作状态 + 清空表单残留 + 记录审核开始时间
        if st.session_state.get("prev_sel") != sel_id:
            st.session_state.prev_sel = sel_id
            st.session_state.review_started_at = datetime.now().isoformat(timespec="seconds")
            st.session_state.review_t0 = time.time()
            if st.session_state.get("action"):
                st.session_state.action = None
                clear_form_keys()

        current = next(a for a in pending if a.get("assertion_id") == sel_id)

        # 来源信息
        st.subheader("📄 来源信息")
        doc_id = current.get("source_doc_id", "")
        ca, cb, cc, cd, ce, cf = st.columns(6)
        ca.markdown(f"**文档标题**: {doc_titles.get(doc_id, doc_id) or '—'}")
        cb.markdown(f"**source_type**: {current.get('source_type', '')}")
        cc.markdown(f"**doc_id**: {doc_id}")
        cd.markdown(f"**chunk_id**: {current.get('source_chunk_id', '')}")
        ce.markdown(f"**章节**: {current.get('section', '') or '—'}")
        cf.markdown(f"**页码**: {current.get('page_start', '')}-{current.get('page_end', '')}")

        # 原文
        st.subheader("📜 原文")
        st.info(current.get("source_text_quote", "") or "（无）")
        full_text = chunk_text_map.get(current.get("source_chunk_id", ""), "")
        if full_text:
            with st.expander("📄 完整 chunk 原文"):
                st.text(full_text)

        # 实体映射
        st.subheader("🔗 实体映射")
        cs, co = st.columns(2)
        with cs:
            st.markdown("**Subject**")
            render_entity(current, "subject", canon_map)
        with co:
            st.markdown("**Object**")
            render_entity(current, "object", canon_map)

        # 三元组
        st.subheader("🧩 候选三元组")
        st.markdown(
            f"### `{current.get('subject_label','')}`  →  `{current.get('predicate','')}`  →  `{current.get('object_label','')}`"
        )
        st.caption(
            f"confidence={current.get('confidence','')} | validation_status={current.get('validation_status','')} "
            f"| assertion_type={current.get('assertion_type','')} | object_kind={current.get('object_kind','')}"
        )

        # ---- AI 预审建议 ----
        ai_rec = get_ai_decision(sel_id)
        if ai_rec is not None:
            st.divider()
            if ai_rec.get("decision") == "overridden":
                st.info("🤖 AI 预审建议已被你忽略，可用下方常规按钮继续人工审核。")
            else:
                d = ai_rec.get("decision", "")
                badge_html = {
                    "ai_approved": "<span style='background:#e8f1fb;color:#1668c7;padding:1px 8px;border-radius:10px;font-size:12px'>ai_approved</span>",
                    "ai_rejected": "<span style='background:#fbe9e9;color:#c0392b;padding:1px 8px;border-radius:10px;font-size:12px'>ai_rejected</span>",
                    "ai_uncertain": "<span style='background:#f1eafb;color:#7b3fd0;padding:1px 8px;border-radius:10px;font-size:12px'>ai_uncertain</span>",
                }.get(d, d)
                st.markdown(
                    f"### 🤖 AI 预审建议 {badge_html}  <small>confidence={ai_rec.get('confidence', '—')}</small>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**理由**：{ai_rec.get('reason', '') or '（无）'}")
                corr = ai_rec.get("suggested_correction", "")
                if corr:
                    st.markdown(f"**修正建议**：`{corr}`")
                ai_a, ai_m, ai_r = st.columns(3)
                if ai_a.button("✅ 接受AI建议", use_container_width=True, key="ai_accept"):
                    accept_ai(current, ai_rec)
                if ai_m.button("✏️ 修改", use_container_width=True, key="ai_modify"):
                    st.session_state.action = "modify"
                    clear_form_keys()
                    st.rerun()
                if ai_r.button("🚫 拒绝AI建议", use_container_width=True, key="ai_reject"):
                    override_ai_decision(sel_id)
                    st.rerun()
                st.caption("AI 预审仅供人工参考，不改变 pending 状态；最终通过/修改/拒绝由你决定。")

        st.divider()

        # 审核操作
        st.subheader("⚙️ 审核操作")
        col_a, col_m, col_r, col_s = st.columns(4)
        if col_a.button("✅ 通过", type="primary", use_container_width=True):
            submit_review(current, "approved")
            st.rerun()
        if col_m.button("✏️ 修改", use_container_width=True):
            st.session_state.action = "modify"
            clear_form_keys()
            st.rerun()
        if col_r.button("❌ 拒绝", use_container_width=True):
            st.session_state.action = "reject"
            clear_form_keys()
            st.rerun()
        if col_s.button("⏭ 暂不处理", use_container_width=True):
            # skip = 稍后处理：不移出 pending，只跳到下一条
            cur_idx = ids.index(sel_id)
            st.session_state.advance = ids[(cur_idx + 1) % len(ids)]
            st.rerun()

        # reject 表单
        if st.session_state.get("action") == "reject":
            st.markdown("---")
            st.subheader("❌ 拒绝")
            with st.form("reject_form"):
                rej_et = st.selectbox("error_type（必填）", ERROR_TAXONOMY, key="rej_et")
                rej_comment = st.text_area("review_comment（必填）", height=80, key="rej_comment")
                rej_submit = st.form_submit_button("确认拒绝")
            if rej_submit:
                if not rej_comment.strip():
                    st.error("reject 必须填写 review_comment")
                else:
                    submit_review(current, "rejected", error_type=rej_et, comment=rej_comment)
                    st.session_state.action = None
                    clear_form_keys()
                    st.rerun()

        # modify 表单（实时 domain/range 校验）
        if st.session_state.get("action") == "modify":
            st.markdown("---")
            st.subheader("✏️ 修改断言")
            orig = current
            c1, c2, c3 = st.columns(3)
            with c1:
                m_slabel = st.text_input("subject_label", value=orig.get("subject_label", ""), key="m_slabel")
                st_idx = ENTITY_TYPES.index(orig.get("subject_type", "")) if orig.get("subject_type", "") in ENTITY_TYPES else 0
                m_stype = st.selectbox("subject_type", ENTITY_TYPES, index=st_idx, key="m_stype")
                m_sid = st.text_input("subject_id", value=orig.get("subject_id", ""), key="m_sid")
            with c2:
                r_idx = RELATION_TYPES.index(orig.get("predicate", "")) if orig.get("predicate", "") in RELATION_TYPES else 0
                m_pred = st.selectbox("predicate", RELATION_TYPES, index=r_idx, key="m_pred")
            with c3:
                m_olabel = st.text_input("object_label", value=orig.get("object_label", ""), key="m_olabel")
                o_idx = ENTITY_TYPES.index(orig.get("object_type", "")) if orig.get("object_type", "") in ENTITY_TYPES else 0
                m_otype = st.selectbox("object_type", ENTITY_TYPES, index=o_idx, key="m_otype")
                m_oid = st.text_input("object_id", value=orig.get("object_id", ""), key="m_oid")

            # 实时 domain/range 校验（entity 断言才校验）
            if orig.get("object_kind") == "entity" or m_otype in ENTITY_TYPES:
                ok = sm.validate_relation_domain(m_stype, m_pred, m_otype)
                if ok:
                    st.success(f"✅ domain/range 合法：{m_stype} -[{m_pred}]-> {m_otype}")
                else:
                    st.error(f"❌ domain/range 不合法：{m_stype} -[{m_pred}]-> {m_otype}")
            else:
                st.info("literal 属性断言，不校验 domain/range")

            m_et = st.selectbox("error_type（必填）", ERROR_TAXONOMY, key="m_et")
            m_comment = st.text_area("review_comment（必填）", height=80, key="m_comment")
            if st.button("确认修改", type="primary"):
                if not m_comment.strip():
                    st.error("modify 必须填写 review_comment")
                else:
                    corrected = {
                        **orig,
                        "subject_label": m_slabel, "subject_type": m_stype, "subject_id": m_sid,
                        "predicate": m_pred,
                        "object_label": m_olabel, "object_type": m_otype, "object_id": m_oid,
                    }
                    submit_review(current, "modified", error_type=m_et, comment=m_comment, corrected=corrected)
                    st.session_state.action = None
                    clear_form_keys()
                    st.rerun()

        # Schema 扩展建议（对当前 assertion）
        st.markdown("---")
        with st.expander("📝 Schema 无合适关系？提交扩展建议"):
            sp_missing = st.text_input("missing_semantic（缺什么语义）", key="sp_missing")
            sp_suggested = st.text_input("suggested_entity_or_relation（建议实体/关系）", key="sp_suggested")
            sp_reason = st.text_area("reason（理由）", height=60, key="sp_reason")
            if st.button("提交 Schema 扩展建议", key="sp_btn"):
                if not sp_missing.strip() or not sp_suggested.strip():
                    st.error("请填写缺失语义和建议")
                else:
                    mgr.add_schema_extension_proposal({
                        "source_assertion_id": current.get("assertion_id", ""),
                        "source_text": current.get("source_text_quote", ""),
                        "missing_semantic": sp_missing,
                        "suggested_entity_or_relation": sp_suggested,
                        "reason": sp_reason,
                        "review_id": "",
                        "status": "pending",
                    })
                    st.success("✅ 已提交 Schema 扩展建议（写入 schema_extension_proposals.jsonl）")
                    st.rerun()

# ==============================
# Tab 2: 案例库
# ==============================
with tab_cases:
    st.subheader("📚 Case Repository")

    if st.button("🔄 更新 Case 索引（调用 rebuild_index）", use_container_width=True):
        with st.spinner("正在重建索引（首次会加载 BGE-M3）..."):
            r = repo.rebuild_index()
        st.success(f"索引已更新：success={r['success']} failure={r['failure']}")

    st.divider()
    all_cases = repo.list_cases()
    success_cases = [c for c in all_cases if c.get("case_type") == "success"]
    failure_cases = [c for c in all_cases if c.get("case_type") == "failure"]

    st.subheader(f"✅ Success Cases（{len(success_cases)}）")
    if not success_cases:
        st.info("暂无 Success Case")
    for c in success_cases:
        a = c.get("reviewed_assertion") or c.get("original_assertion") or {}
        with st.expander(f"{c.get('case_id','')} — {a.get('predicate','')}（{c.get('case_status','')}）"):
            st.markdown(f"**原文**: {c.get('source_text','')}")
            st.markdown(f"**三元组**: `{assertion_to_str(a)}`")
            st.markdown(f"**schema_version**: {c.get('schema_version','')} | **review_id**: {c.get('review_id','')}")

    st.subheader(f"❌ Failure Cases（{len(failure_cases)}）")
    if not failure_cases:
        st.info("暂无 Failure Case")
    for c in failure_cases:
        with st.expander(f"{c.get('case_id','')} — {c.get('error_type','')}（{c.get('case_status','')}）"):
            st.markdown(f"**原文**: {c.get('source_text','')}")
            st.markdown(f"**错误三元组**: `{assertion_to_str(c.get('incorrect_output'))}`")
            st.markdown(f"**修改后三元组**: `{assertion_to_str(c.get('corrected_output')) or '（无，建议 unresolved / schema extension）'}`")
            st.markdown(f"**error_type**: {c.get('error_type','')}")
            st.markdown(f"**review_comment**: {c.get('review_comment','')}")
            st.markdown(f"**rule_learned**: {c.get('rule_learned','')}")

# ==============================
# Tab 3: Unresolved / Schema 提案
# ==============================
with tab_unresolved:
    st.subheader("⚠️ Unresolved Relations（未映射到 schema 的开放谓词）")
    if not unresolved:
        st.info("暂无 unresolved relations")
    for i, u in enumerate(unresolved):
        with st.expander(
            f"r{u.get('relation_id','?')} — {u.get('predicate_surface','')} "
            f"({u.get('subject_surface','')} → {u.get('object_surface','')})"
        ):
            st.markdown(f"**subject**: {u.get('subject_surface','')}（{u.get('subject_type','')}）")
            st.markdown(f"**predicate_surface**: {u.get('predicate_surface','')}")
            st.markdown(f"**object**: {u.get('object_surface','')}（{u.get('object_type','')}）")
            st.markdown(f"**evidence**: {u.get('evidence_quote','')}")

            with st.form(f"prop_form_{i}"):
                p_missing = st.text_input("missing_semantic", value=u.get("predicate_surface", ""))
                p_suggested = st.text_input("suggested_entity_or_relation（建议关系，如 contains/handles）")
                p_reason = st.text_area("reason", height=50)
                if st.form_submit_button("提交为 Schema 扩展建议"):
                    if not p_missing.strip() or not p_suggested.strip():
                        st.error("请填写缺失语义和建议")
                    else:
                        mgr.add_schema_extension_proposal({
                            "source_assertion_id": "",
                            "source_text": u.get("evidence_quote", ""),
                            "missing_semantic": p_missing,
                            "suggested_entity_or_relation": p_suggested,
                            "reason": p_reason,
                            "review_id": "",
                            "status": "pending",
                        })
                        st.success("✅ 已提交 Schema 扩展建议")
                        st.rerun()

    st.divider()
    st.subheader("📝 已有 Schema 扩展建议")
    proposals = mgr.get_schema_extension_proposals()
    if not proposals:
        st.info("暂无提案")
    else:
        st.write(f"共 {len(proposals)} 条")
        for p in proposals:
            with st.expander(f"{p.get('proposal_id','')} — {p.get('suggested_entity_or_relation','')}（{p.get('status','')}）"):
                st.markdown(f"**missing_semantic**: {p.get('missing_semantic','')}")
                st.markdown(f"**suggested**: {p.get('suggested_entity_or_relation','')}")
                st.markdown(f"**reason**: {p.get('reason','')}")
                st.markdown(f"**source_text**: {p.get('source_text','')}")
                st.markdown(f"**source_assertion_id**: {p.get('source_assertion_id','')}")
