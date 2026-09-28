import streamlit as st
import os
import sys
import json

# ============================
# 项目路径
# ============================
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)

from app._theme import apply_theme, page_header, metric_row, badge, evidence_card
from app._graph import load_graph, render_graph

from core.kg.wiki_review_manager import WikiReviewManager
from core.kg.wiki_case_builder import WikiCaseBuilder
from core.kg.case_repository import CaseRepository
from core.kg.review_models import ERROR_TAXONOMY

apply_theme()

WIKI_ROOT = os.path.join(ROOT_PATH, "data", "wiki")


# ============================
# 后端对象（st.cache_resource，懒加载模型）
# ============================
@st.cache_resource
def get_wiki_review_manager():
    return WikiReviewManager()


@st.cache_resource
def get_wiki_case_builder():
    return WikiCaseBuilder()


@st.cache_resource
def get_case_repository():
    return CaseRepository()  # embedding 惰性，只在「更新 Case 索引」时加载 BGE-M3


def get_existing_wiki():
    if not os.path.exists(WIKI_ROOT):
        return []
    return [n for n in os.listdir(WIKI_ROOT) if os.path.isdir(os.path.join(WIKI_ROOT, n))]


def load_wiki(entity):
    md_path = os.path.join(WIKI_ROOT, entity, "wiki.md")
    if not os.path.exists(md_path):
        return None
    with open(md_path, encoding="utf-8") as f:
        return f.read()


def load_evidence(entity):
    p = os.path.join(WIKI_ROOT, entity, "evidence.json")
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# ============================
# 页面
# ============================
page_header("📖 知识 Wiki", "危险化学品安全知识百科 —— 生成、审核、证据溯源")

wrm = get_wiki_review_manager()
wcb = get_wiki_case_builder()
repo = get_case_repository()

existing = get_existing_wiki()

# ---- 搜索 / 生成 ----
col_search, col_gen = st.columns([4, 1])
with col_search:
    entity = st.text_input("输入化学品名称", placeholder="例如：液氯、氯、氨", key="wiki_entity")
with col_gen:
    st.write("")
    st.write("")

if not entity:
    page_stats = wrm.get_statistics()
    metric_row([
        (len(existing), "已有 Wiki"),
        (page_stats["pending"], "Wiki Pending"),
        (page_stats["approved"], "Wiki Approved"),
        (page_stats["rejected"] + page_stats["modified"], "Wiki 需修正"),
    ])
    st.divider()
    st.subheader("已有 Wiki")
    if not existing:
        st.info("暂无 Wiki，输入化学品名称开始生成。")
    else:
        for name in existing:
            st.markdown(f"- {name}")
    st.stop()

# ---- 该 Wiki 是否已存在 ----
wiki_md = load_wiki(entity)

if wiki_md is None:
    st.warning(f"暂未找到「{entity}」的 Wiki。")
    if st.button("🚀 生成 Wiki", type="primary"):
        with st.spinner("正在检索知识库并生成 Wiki（首次会加载 RAG / Qwen / BGE）..."):
            from core.rag import RAGSystem
            from core.wiki_generator import WikiGenerator
            rag = RAGSystem()
            generator = WikiGenerator(rag)
            result = generator.generate(entity)
            st.success("Wiki 生成完成")
            st.rerun()
    st.stop()

# ---- 已有 Wiki，进入 tabs ----
evidence = load_evidence(entity)

# 顶部统计
reviews = wrm.get_reviews(entity)
n_pending = sum(1 for r in reviews.values() if r.get("review_status") == "pending")
n_approved = sum(1 for r in reviews.values() if r.get("review_status") == "approved")
n_issue = sum(1 for r in reviews.values() if r.get("review_status") in ("rejected", "modified"))
metric_row([
    (len(wrm.get_sections(entity, wiki_md)), "Sections"),
    (n_pending, "Pending"),
    (n_approved, "Approved"),
    (n_issue, "需修正"),
    (len(evidence), "Evidence"),
])

st.divider()

tab_body, tab_review, tab_evidence, tab_kg, tab_case = st.tabs(
    ["📖 Wiki正文", "🔍 审核", "📚 证据来源", "🕸️ 知识图谱", "🧪 Wiki案例"]
)

# ============================
# Tab 1: Wiki 正文
# ============================
with tab_body:
    st.markdown(wiki_md)

# ============================
# Tab 2: 审核（section 级）
# ============================
with tab_review:
    sections = wrm.get_sections(entity, wiki_md)
    wrm.init_review(entity, wiki_md)  # 幂等初始化
    reviews = wrm.get_reviews(entity)

    if not sections:
        st.info("未解析到 section")
    else:
        left, right = st.columns([1, 3])
        with left:
            sec_names = [s["section"] for s in sections]
            if "wiki_sel_section" not in st.session_state or st.session_state.wiki_sel_section not in sec_names:
                st.session_state.wiki_sel_section = sec_names[0]
            sel = st.radio("Wiki Section", sec_names, key="wiki_sel_section")
            rec = reviews.get(sel, {})
            st.markdown("**审核状态**")
            st.markdown(badge(rec.get("review_status", "pending")), unsafe_allow_html=True)

        with right:
            sec = next(s for s in sections if s["section"] == sel)
            rec = reviews.get(sel, {})
            ks = sec.get("knowledge_source", "model_prior")
            ks_text = "文档证据支持" if ks == "grounded" else "模型补充知识"
            st.markdown(
                f"### {sel}  " + badge(ks, ks_text),
                unsafe_allow_html=True,
            )
            st.caption(f"evidence_ids: {', '.join('[' + e + ']' for e in sec['evidence_ids']) or '无（模型补充）'}")

            # 可编辑内容
            edited = st.text_area("内容（可直接编辑）", value=sec["content"].strip(), height=280, key=f"wiki_edit_{sel}")

            # 按钮
            c1, c2, c3 = st.columns(3)
            if c1.button("✅ 通过", type="primary", use_container_width=True, key=f"appr_{sel}"):
                record = dict(rec)
                record.update({
                    "section": sel, "content": sec["content"].strip(),
                    "knowledge_source": ks, "evidence_ids": sec["evidence_ids"],
                    "review_status": "approved", "reviewed_content": sec["content"].strip(),
                    "review_comment": "", "error_type": "",
                })
                wrm.submit_review(entity, record)
                case = wcb.build_from_review(record)
                if case:
                    repo.add_case(case)
                st.rerun()
            if c2.button("✏️ 修改并通过", use_container_width=True, key=f"mod_{sel}"):
                st.session_state.wiki_action = "modify"
                st.session_state.wiki_section = sel
                st.rerun()
            if c3.button("❌ 拒绝", use_container_width=True, key=f"rej_{sel}"):
                st.session_state.wiki_action = "reject"
                st.session_state.wiki_section = sel
                st.rerun()

            # reject / modify 表单
            if st.session_state.get("wiki_action") and st.session_state.get("wiki_section") == sel:
                st.markdown("---")
                if st.session_state.wiki_action == "reject":
                    st.subheader("❌ 拒绝此 section")
                    rej_et = st.selectbox("error_type（必填）", ERROR_TAXONOMY, key=f"wrej_et_{sel}")
                    rej_comment = st.text_area("review_comment（必填）", height=80, key=f"wrej_c_{sel}")
                    if st.button("确认拒绝", key=f"wrej_btn_{sel}"):
                        if not rej_comment.strip():
                            st.error("reject 必须填写 review_comment")
                        else:
                            record = dict(rec)
                            record.update({
                                "section": sel, "content": sec["content"].strip(),
                                "knowledge_source": ks, "evidence_ids": sec["evidence_ids"],
                                "review_status": "rejected", "reviewed_content": "",
                                "error_type": rej_et, "review_comment": rej_comment,
                            })
                            wrm.submit_review(entity, record)
                            case = wcb.build_from_review(record)
                            if case:
                                repo.add_case(case)
                            st.session_state.wiki_action = None
                            st.rerun()
                elif st.session_state.wiki_action == "modify":
                    st.subheader("✏️ 修改并通过")
                    mod_et = st.selectbox("error_type（必填）", ERROR_TAXONOMY, key=f"wmod_et_{sel}")
                    mod_comment = st.text_area("review_comment（必填）", height=80, key=f"wmod_c_{sel}")
                    if st.button("确认修改并通过", key=f"wmod_btn_{sel}"):
                        if not mod_comment.strip():
                            st.error("modify 必须填写 review_comment")
                        else:
                            record = dict(rec)
                            record.update({
                                "section": sel, "content": sec["content"].strip(),
                                "knowledge_source": ks, "evidence_ids": sec["evidence_ids"],
                                "review_status": "modified", "reviewed_content": edited.strip(),
                                "error_type": mod_et, "review_comment": mod_comment,
                            })
                            wrm.submit_review(entity, record)
                            case = wcb.build_from_review(record)
                            if case:
                                repo.add_case(case)
                            st.session_state.wiki_action = None
                            st.rerun()

# ============================
# Tab 3: 证据来源
# ============================
with tab_evidence:
    st.subheader(f"📚 证据来源（{len(evidence)}）")
    if not evidence:
        st.info("暂无证据")
    for i, item in enumerate(evidence):
        meta = item.get("metadata", {})
        html = (
            f"<b>[Wiki证据{i+1}]</b> {meta.get('title','')}<br>"
            f"<span class='src'>编号 {meta.get('code','')} | 来源 {meta.get('source','')} "
            f"| 页码 {meta.get('page_start','')} | chunk {meta.get('chunk_id','')} "
            f"| rerank {item.get('rerank_score',''):.3f}</span><br><br>"
            f"<div>{meta.get('text','')[:400]}</div>"
        )
        st.markdown(evidence_card(html), unsafe_allow_html=True)

# ============================
# Tab 4: 知识图谱
# ============================
with tab_kg:
    st.subheader("🕸️ 知识图谱")
    g = load_graph("approved")
    if not g["nodes"]:
        st.info(
            "暂无 approved KG 数据。\n\n"
            "人工审核确认的三元组会进入这里形成图谱；当前没有已确认断言，不伪造节点。"
        )
    else:
        st.caption("以「" + entity + "」相关实体为中心展示；点击节点查看来源证据，不刷新本页。")
        render_graph(g["nodes"], g["edges"], mode="approved", height=560)

# ============================
# Tab 5: Wiki 案例
# ============================
with tab_case:
    st.subheader("🧪 Wiki Success / Failure Case（task_type=wiki_generation）")
    if st.button("🔄 更新 Case 索引（调用 rebuild_index）", use_container_width=True):
        with st.spinner("正在重建索引（首次会加载 BGE-M3）..."):
            r = repo.rebuild_index()
        st.success(f"索引已更新：success={r['success']} failure={r['failure']}")

    st.divider()
    wiki_cases = [c for c in repo.list_cases() if c.get("task_type") == "wiki_generation"]
    success = [c for c in wiki_cases if c.get("case_type") == "success"]
    failure = [c for c in wiki_cases if c.get("case_type") == "failure"]

    st.subheader(f"✅ Success Cases（{len(success)}）")
    for c in success:
        with st.expander(f"{c.get('section','')} — {c.get('case_id','')}"):
            st.markdown(f"**entity**: {c.get('entity','')} | **section**: {c.get('section','')}")
            st.markdown(f"**内容**: {c.get('reviewed_content','') or c.get('source_text','')[:300]}")
            if c.get("human_verified_model_knowledge"):
                st.markdown(badge("model", "human_verified_model_knowledge"), unsafe_allow_html=True)

    st.subheader(f"❌ Failure Cases（{len(failure)}）")
    for c in failure:
        with st.expander(f"{c.get('section','')} — {c.get('error_type','')}"):
            st.markdown(f"**原内容**: {c.get('source_text','')[:300]}")
            st.markdown(f"**修改后**: {c.get('reviewed_content','')[:300] or '（拒绝，无修改）'}")
            st.markdown(f"**error_type**: {c.get('error_type','')} | **comment**: {c.get('review_comment','')}")
