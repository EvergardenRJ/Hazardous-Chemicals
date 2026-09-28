import streamlit as st
import os
import sys
import pandas as pd



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
    "📚 化工安全知识库管理",
    "管理标准文件、法规文件、PDF 文档、向量索引与 Wiki 知识"
)


st.markdown(
"""
管理当前化工安全知识库中的：

- 标准文件
- 法规文件
- PDF文档
- 向量索引
- Wiki知识

"""
)



st.divider()



# ==============================
# 数据路径
# ==============================


inventory_path = os.path.join(
    ROOT_PATH,
    "data",
    "pdf_inventory.csv"
)



document_master_path = os.path.join(
    ROOT_PATH,
    "data",
    "document_master.csv"
)



# ==============================
# 加载PDF inventory
# ==============================


@st.cache_data
def load_inventory():

    if os.path.exists(
        inventory_path
    ):

        return pd.read_csv(
            inventory_path
        )

    else:

        return pd.DataFrame()



inventory = load_inventory()



# ==============================
# 总览
# ==============================


st.subheader(
    "📊 知识库统计"
)



col1,col2,col3,col4 = st.columns(4)



with col1:

    st.metric(
        "PDF数量",
        len(inventory)
        if len(inventory)>0
        else 970
    )


with col2:

    st.metric(
        "标准",
        730
    )


with col3:

    st.metric(
        "法规",
        240
    )


with col4:

    st.metric(
        "向量Chunk",
        16491
    )



st.divider()



# ==============================
# PDF状态
# ==============================


st.subheader(
    "📄 PDF文档状态"
)



if len(inventory)>0:


    st.dataframe(
        inventory.head(100),
        use_container_width=True
    )


else:


    st.info(
        "未检测到pdf_inventory.csv"
    )



st.divider()



# ==============================
# 类型统计
# ==============================


st.subheader(
    "📈 文档类型统计"
)



if len(inventory)>0:


    if "document_type" in inventory.columns:


        type_count = (
            inventory[
                "document_type"
            ]
            .value_counts()
        )


        st.bar_chart(
            type_count
        )


    else:


        st.warning(
            "缺少document_type字段"
        )



# ==============================
# 文档搜索
# ==============================


st.divider()


st.subheader(
    "🔎 文档查询"
)



keyword = st.text_input(
    "输入关键词",
    placeholder="例如：液氯、氯气、安全技术规范"
)



if keyword and len(inventory)>0:


    result = inventory[
        inventory.astype(str)
        .apply(
            lambda x:
            x.str.contains(
                keyword,
                case=False
            )
        )
        .any(axis=1)
    ]


    st.write(
        f"找到 {len(result)} 条结果"
    )


    st.dataframe(
        result,
        use_container_width=True
    )



# ==============================
# 系统信息
# ==============================


st.divider()


st.subheader(
    "🗂 数据目录"
)


st.code(
f"""
PDF目录:

{os.path.join(ROOT_PATH,'data','pdf')}


向量库:

{os.path.join(ROOT_PATH,'data','vector_store')}


Wiki:

{os.path.join(ROOT_PATH,'data','wiki')}
"""
)