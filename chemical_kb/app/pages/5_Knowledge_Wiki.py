"""Legacy Streamlit view over the same versioned Wiki service as React."""
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.wiki.service import WikiService
from core.wiki.jobs import Jobs
from core.wiki.citations import SECTIONS
from app._theme import apply_theme,page_header
apply_theme()
page_header("📖 知识 Wiki","逐节核查原文，保留版本与审核历史")
service=WikiService();jobs=Jobs(service.repo)
entries=service.list()
entity=st.selectbox("已有条目",[""]+[e["entity"] for e in entries])
new=st.text_input("新化学品名称")
if st.button("创建生成任务",disabled=not new.strip()):
    try:
        job=jobs.create(new,{"sections":SECTIONS})
        st.success(job.get("block_reason") or "任务已保存")
    except Exception as e:st.error(str(e))
with st.expander("生成任务"):
    for job in jobs.list():
        st.write(job["entity"],job["state"],job["progress"])
        if job["block_reason"]:st.info(job["block_reason"])
        if job["error"]:st.error(job["error"])
if not entity:st.stop()
try:
    view=st.radio("内容版本",["draft","published"],format_func=lambda v:"当前草稿" if v=="draft" else "已发布版本",horizontal=True)
    detail=service.detail(entity,view)
    st.caption(("已发布" if detail["is_published"] else "未发布草稿")+"；版本："+detail["revision_id"])
    if not detail["validation"]["ok"]:
        st.warning("该草稿需要修正，尚不可发布")
        with st.expander("校验问题"):st.write(detail["validation"]["errors"])
    sections=detail["sections"]
    title=st.selectbox("章节",[s["section"] for s in sections])
    section=next(s for s in sections if s["section"]==title)
    body,proof=st.columns([3,2])
    with body:
        st.markdown(section["content"])
        st.caption("知识来源："+{"grounded":"本地文档","model_prior":"大模型知识库","external":"百科来源","mixed":"多种来源"}.get(section.get("knowledge_source"),"来源待核实")+"；审核："+section.get("review_status","pending"))
    with proof:
        for n,e in enumerate(detail["evidence"],1):
            if e["evidence_id"] not in section.get("evidence_refs",[]):continue
            m=e["metadata"]
            with st.expander(f"[Wiki证据{n}] {m.get('title','')}"):
                st.write("文档",m.get("code"),"页码",m.get("page_start"),"片段",m.get("chunk_id"))
                st.write(m.get("text",""))
    with st.expander("百科资料与事故阅读"):
        for source in detail.get("external_sources",[]):
            st.markdown("**来源："+source["source_name"]+"**")
            st.write(source.get("summary",""))
            st.link_button("阅读 "+source.get("title","词条"),source["url"])
        for rec in detail.get("accident_reading",[]):
            st.markdown("**"+rec["title"]+"**")
            st.write(rec.get("reason",""))
            url=rec.get("url")
            if not url and rec.get("evidence_id"):
                from urllib.parse import quote
                url="/api/wiki/"+quote(entity,safe="")+"/evidence/"+rec["evidence_id"]+"/pdf?revision="+detail["revision_id"]
            if url:st.markdown("[阅读报告]("+url+")")
    reviewer=st.text_input("审核人")
    if view=="draft":
        edited=st.text_area("候选正文",section["content"],height=280,key=detail["revision_id"]+section["section_id"])
        comment=st.text_input("审核意见（修改或拒绝必填）")
        c1,c2,c3=st.columns(3)
        decision="approved" if c1.button("通过",disabled=edited.strip()!=section["content"].strip()) else ("modified" if c2.button("修改并通过") else ("rejected" if c3.button("拒绝") else None))
        if decision:
            service.review(entity,{"expected_revision":detail["revision_id"],"section_id":section["section_id"],
                "reviewer":reviewer,"review_status":decision,"reviewed_content":edited,"review_comment":comment})
            st.rerun()
        if st.button("重新生成本节"):
            jobs.create(entity,{"sections":[title],"base_revision":detail["revision_id"]})
            st.success("本节更新任务已保存")
        if st.button("发布审核版本"):
            service.publish(entity,{"reviewer":reviewer,"expected_revision":detail["revision_id"]})
            st.rerun()
    with st.expander("版本历史"):st.write(service.repo.history(entity))
except Exception as exc:
    st.error(str(exc))
