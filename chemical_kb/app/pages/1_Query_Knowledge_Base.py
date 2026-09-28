import streamlit as st
import sys
import os


# ==============================
# 项目路径
# ==============================

# ROOT_PATH = os.path.dirname(
#     os.path.dirname(
#         os.path.abspath(__file__)
#     )
# )

# sys.path.append(
#     ROOT_PATH
# )

# import sys
# import os


ROOT_PATH = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)


sys.path.append(
    ROOT_PATH
)


from core.rag import RAGSystem

from app._theme import apply_theme, page_header

apply_theme()


page_header(
    "🔍 化工安全知识库问答",
    "关键词 · 向量 · 已审核图谱融合检索 / RRF 排序 / 可追溯证据"
)


st.caption("知识检索工作台 · 默认查看当前有效知识；可选择历史生效时点。")
as_of_date = st.date_input("知识生效时点", value="today", help="按 [生效日, 失效日) 查询；未标注生效日期的旧数据仍可见。")



# ==============================
# 初始化RAG
# ==============================

@st.cache_resource
def load_rag():

    return RAGSystem()



with st.spinner(
    "正在加载知识库模型..."
):

    rag = load_rag()



st.success(
    "RAG系统加载完成"
)



# ==============================
# 输入问题
# ==============================


question = st.text_area(
    "请输入化工安全问题",
    placeholder=
    "例如：\n液氯发生泄漏后应该采取哪些应急处置措施？",
    height=120
)



# ==============================
# 查询
# ==============================


if st.button(
    "🚀 开始查询",
    type="primary"
):


    if question.strip()=="":


        st.warning(
            "请输入问题"
        )


    else:


        with st.spinner(
            "正在检索知识库并生成答案..."
        ):


            result = rag.answer(
                question,
                as_of=as_of_date.isoformat()
            )



        st.divider()



        # ======================
        # 回答
        # ======================


        st.subheader(
            "🤖 AI回答"
        )


        answer = result.get(
            "answer",
            ""
        )


        st.markdown(
            answer
        )



        st.divider()



        # ======================
        # Evidence
        # ======================


        st.subheader(
            "📚 检索证据"
        )


        evidence = result.get(
            "evidence",
            []
        )



        st.write(
            f"共检索到 {len(evidence)} 条证据"
        )



        for idx,item in enumerate(
            evidence
        ):


            metadata = item.get(
                "metadata",
                {}
            )


            with st.expander(
                f"证据 {idx+1}: {metadata.get('title','')}"
            ):


                st.markdown(
                    f"""
**编号**

{metadata.get('code')}


**来源**

{metadata.get('source')}


**页码**

{metadata.get('page_start')}


**向量 Score**

{item.get('score')}


**融合路径**

{", ".join(item.get("routes", [])) or "向量"}

**RRF Score**

{item.get("rrf_score", "—")}

**Rerank Score**

{item.get('rerank_score')}


---

**原文**

{metadata.get('text')}
"""
                )