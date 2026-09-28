import os
import json
import numpy as np
import faiss

from sentence_transformers import SentenceTransformer



# ============================================================
# 路径
# ============================================================


BASE="/root/autodl-tmp/chemical_kb"


INDEX_FILE = (
    BASE
    +
    "/data/vector_store/faiss.index"
)


META_FILE = (
    BASE
    +
    "/data/vector_store/index_metadata.json"
)


MODEL_PATH = (
    "/root/autodl-tmp/models/bge-m3"
)



# ============================================================
# 参数
# ============================================================


TOP_K = 5



# ============================================================
# 加载
# ============================================================


def load_resources():


    print("="*60)

    print("加载FAISS")


    index = faiss.read_index(
        INDEX_FILE
    )


    print(
        "向量数量:",
        index.ntotal
    )



    print("加载metadata")


    with open(
        META_FILE,
        encoding="utf-8"
    ) as f:

        metadata=json.load(f)



    print(
        "metadata数量:",
        len(metadata)
    )



    print("加载BGE-M3")


    model=SentenceTransformer(
        MODEL_PATH,
        device="cuda"
    )


    model.max_seq_length=1024



    return index,metadata,model





# ============================================================
# 检索
# ============================================================


def search(
    question,
    index,
    metadata,
    model
):


    print("\n")
    print("="*80)

    print(
        "问题:"
    )

    print(
        question
    )



    # 问题向量

    query_vector=model.encode(

        [question],

        normalize_embeddings=True

    )


    query_vector=query_vector.astype(
        "float32"
    )



    scores,ids=index.search(

        query_vector,

        TOP_K

    )



    print("="*80)

    print("检索结果")



    for rank,(idx,score) in enumerate(
        zip(ids[0],scores[0]),
        1
    ):


        item=metadata[idx]


        print("\n")

        print(
            "Rank:",
            rank
        )


        print(
            "Score:",
            round(float(score),4)
        )


        print(
            "编号:",
            item.get(
                "code",
                ""
            )
        )


        print(
            "标题:",
            item.get(
                "title",
                ""
            )
        )


        print(
            "类型:",
            item.get(
                "document_type",
                ""
            )
        )


        print(
            "页码:",
            item.get(
                "page_start",
                ""
            )
        )


        text=item.get(
            "text",
            ""
        )


        print(
            "内容:"
        )


        print(
            text[:500]
        )



# ============================================================
# main
# ============================================================


if __name__=="__main__":


    index,metadata,model=load_resources()



    while True:


        question=input(
            "\n请输入问题(q退出): "
        )


        if question.lower()=="q":

            break



        search(
            question,
            index,
            metadata,
            model
        )