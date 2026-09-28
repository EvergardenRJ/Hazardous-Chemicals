import streamlit as st
import os
import sys
import torch
import platform
import subprocess



# ==============================
# 项目路径
# ==============================

ROOT_PATH = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

sys.path.append(ROOT_PATH)

from app._theme import apply_theme, page_header

apply_theme()


page_header(
    "⚙️ 化工安全知识库系统状态",
    "模型、向量库、GPU、数据规模与 Wiki 知识库运行状态"
)


st.markdown(
"""
系统运行状态监控：

- 模型状态
- 向量库状态
- GPU环境
- 数据规模
- Wiki知识库
"""
)


st.divider()



# ==============================
# GPU状态
# ==============================

st.subheader(
    "🖥️ GPU环境"
)


col1,col2,col3 = st.columns(3)



with col1:


    if torch.cuda.is_available():

        gpu_name = torch.cuda.get_device_name(0)

        st.metric(
            "GPU",
            gpu_name
        )

    else:

        st.metric(
            "GPU",
            "CPU"
        )



with col2:


    if torch.cuda.is_available():

        memory = torch.cuda.memory_allocated(
            0
        ) / 1024**3


        st.metric(
            "显存使用",
            f"{memory:.2f} GB"
        )

    else:

        st.metric(
            "显存",
            "-"
        )



with col3:


    st.metric(
        "Python版本",
        platform.python_version()
    )



st.divider()



# ==============================
# 模型状态
# ==============================


st.subheader(
    "🤖 AI模型"
)



model_data = {


    "Embedding":
    "BGE-M3",


    "Reranker":
    "BGE Reranker",


    "LLM":
    "Qwen",


    "Vector Database":
    "FAISS"

}



for k,v in model_data.items():


    st.success(
        f"{k}: {v}  ✓"
    )



st.divider()



# ==============================
# 知识库状态
# ==============================


st.subheader(
    "📚 知识库规模"
)



col1,col2,col3,col4 = st.columns(4)



with col1:

    st.metric(
        "标准数量",
        "615"
    )


with col2:

    st.metric(
        "法规数量",
        "240"
    )


with col3:

    st.metric(
        "PDF数量",
        "970"
    )


with col4:

    st.metric(
        "Chunk数量",
        "16491"
    )



st.divider()



# ==============================
# Wiki状态
# ==============================


st.subheader(
    "📖 Wiki知识库"
)



wiki_path = os.path.join(
    ROOT_PATH,
    "data",
    "wiki"
)



if os.path.exists(
    wiki_path
):


    entities = os.listdir(
        wiki_path
    )


    st.metric(
        "Wiki实体数量",
        len(entities)
    )


    if len(entities)>0:

        st.write(
            "已有Wiki:"
        )


        for e in entities:

            st.write(
                "📘",
                e
            )


else:


    st.info(
        "暂无Wiki"
    )



st.divider()



# ==============================
# FAISS状态
# ==============================


st.subheader(
    "🔍 向量数据库"
)



vector_path = os.path.join(
    ROOT_PATH,
    "data",
    "vector_store"
)



if os.path.exists(
    vector_path
):


    files=os.listdir(
        vector_path
    )


    st.success(
        "FAISS索引存在 ✓"
    )


    st.write(
        files
    )


else:


    st.warning(
        "未找到FAISS索引"
    )



st.divider()



st.caption(
"""
Chemical Safety Knowledge Base
RAG + Vector Database + LLM Wiki System
"""
)