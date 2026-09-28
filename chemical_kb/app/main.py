import streamlit as st
import os
import sys

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_PATH)

from app._theme import apply_theme, page_header, metric_row, PLATFORM_NAME_EN

apply_theme()

from core.kg.review_manager import ReviewManager
from core.kg.case_repository import CaseRepository

DATA_DIR = os.path.join(ROOT_PATH, "data")


@st.cache_data
def load_home_metrics():
    parsed = os.path.join(DATA_DIR, "parsed_documents")
    docs = 0
    accidents = 0
    if os.path.exists(parsed):
        files = [f for f in os.listdir(parsed) if f.endswith(".json")]
        docs = len(files)
        accidents = len([f for f in files if f.startswith("ACC_")])

    vectors = 0
    chunks_file = os.path.join(DATA_DIR, "chunks", "chunks_v2.jsonl")
    if os.path.exists(chunks_file):
        with open(chunks_file, encoding="utf-8") as f:
            vectors = sum(1 for _ in f)

    wiki_dir = os.path.join(DATA_DIR, "wiki")
    wikis = 0
    if os.path.exists(wiki_dir):
        wikis = len([n for n in os.listdir(wiki_dir)
                     if os.path.isdir(os.path.join(wiki_dir, n))])

    return {"docs": docs, "accidents": accidents, "vectors": vectors, "wikis": wikis}


m = load_home_metrics()
rm = ReviewManager()
cr = CaseRepository()

pending = len(rm.get_pending())
cases = cr.list_cases()
success = len([c for c in cases if c.get("case_type") == "success"])
failure = len([c for c in cases if c.get("case_type") == "failure"])

page_header("化工安全知识图谱", f"{PLATFORM_NAME_EN}  /  Evidence Explorer")

st.markdown("#### 平台概览")
metric_row([
    (m["docs"], "文档数量"),
    (m["vectors"], "Vector 数量"),
    (m["accidents"], "事故报告"),
    (pending, "Pending KG 审核"),
    (success, "Success Case"),
    (failure, "Failure Case"),
    (m["wikis"], "Wiki 数量"),
])

st.markdown("""
<div style="background:radial-gradient(circle at 78% 22%,rgba(68,212,197,.18),transparent 32%),linear-gradient(125deg,#123447,#0b2130);
            border:1px solid #2c6672;border-radius:16px;padding:1.6rem 2rem;margin:1.2rem 0 1.5rem;
            box-shadow:0 18px 42px rgba(0,0,0,.18)">
  <div style="color:#6ce2d1;font:600 .78rem monospace;letter-spacing:.16em;margin-bottom:.6rem">KNOWLEDGE ATLAS  /  探索工作台</div>
  <div style="color:#f1f9f8;font-size:clamp(1.3rem,2vw,2rem);font-weight:700;line-height:1.35">从问题进入证据，再沿关系追溯来源</div>
  <div style="color:#accbd0;max-width:680px;line-height:1.75;margin-top:.7rem">
  将关键词、语义向量和人工审核图谱融合检索；按生效日期浏览关系，检查跨来源冲突，导出可溯源知识。</div>
</div>
""", unsafe_allow_html=True)

st.markdown("### 开始探索")
left, middle, right = st.columns(3)
with left:
    with st.container(border=True):
        st.markdown("#### 01 / 检索")
        st.caption("关键词 + 向量 + 图谱证据 · RRF · 原文页码")
        st.page_link("pages/1_Query_Knowledge_Base.py", label="打开知识问答", icon="🔎")
    with st.container(border=True):
        st.markdown("#### 04 / 知识管理")
        st.caption("文档、向量与索引状态")
        st.page_link("pages/3_Knowledge_Management.py", label="打开知识管理", icon="📚")
with middle:
    with st.container(border=True):
        st.markdown("#### 02 / 图谱")
        st.caption("时点关系 · 证据路径 · 冲突和实体审核 · 多格式导出")
        st.page_link("pages/7_Knowledge_Graph.py", label="打开图谱探索台", icon="🕸️")
    with st.container(border=True):
        st.markdown("#### 05 / 文档入库")
        st.caption("沿用现有标准、法规与事故报告上传流程")
        st.page_link("pages/2_Upload_Document.py", label="上传文档", icon="📄")
with right:
    with st.container(border=True):
        st.markdown("#### 03 / 审核")
        st.caption("人工审核断言 · 决定进入生产图谱的知识")
        st.page_link("pages/6_KG_Review.py", label="打开审核中心", icon="✅")
    with st.container(border=True):
        st.markdown("#### 06 / Wiki 与状态")
        st.caption("安全 Wiki 与系统运行指标")
        st.page_link("pages/5_Knowledge_Wiki.py", label="打开 Wiki", icon="📖")
        st.page_link("pages/4_System_Status.py", label="查看系统状态", icon="🖥️")
