import streamlit as st
import os
import sys


# ==============================
# 添加项目路径
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
    "📄 化工安全文档上传",
    "上传国家标准、行业标准、安全法规、技术文件"
)


st.markdown(
"""
上传新的：

- 国家标准
- 行业标准
- 地方标准
- 安全法规
- 技术文件

用于扩展知识库。
"""
)


st.divider()



# ==============================
# 文件上传
# ==============================


uploaded_file = st.file_uploader(
    "请选择PDF文件",
    type=["pdf"]
)



if uploaded_file:


    st.success(
        "文件上传成功"
    )


    st.write(
        "文件名:",
        uploaded_file.name
    )


    st.write(
        "大小:",
        f"{uploaded_file.size/1024/1024:.2f} MB"
    )



    st.divider()



    # 保存目录

    save_dir = os.path.join(
        ROOT_PATH,
        "data",
        "upload"
    )


    os.makedirs(
        save_dir,
        exist_ok=True
    )


    save_path = os.path.join(
        save_dir,
        uploaded_file.name
    )



    if st.button(
        "💾 保存文档"
    ):


        with open(
            save_path,
            "wb"
        ) as f:

            f.write(
                uploaded_file.getbuffer()
            )


        st.success(
            f"""
文档保存成功

路径:

{save_path}
"""
        )



        st.info(
"""
下一阶段处理流程：

PDF解析
↓
文本抽取/OCR
↓
Chunk切分
↓
Embedding
↓
FAISS更新

"""
        )



# ==============================
# 当前知识库
# ==============================


st.divider()


st.subheader(
    "📚 当前知识库"
)



col1,col2,col3 = st.columns(3)


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
        "向量数量",
        "16491"
    )