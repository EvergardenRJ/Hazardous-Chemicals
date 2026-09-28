import json
import faiss
import torch

from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification



# =====================================================
# 路径
# =====================================================

BASE = "/root/autodl-tmp/chemical_kb"


FAISS_PATH = (
    BASE +
    "/data/vector_store/faiss.index"
)


META_PATH = (
    BASE +
    "/data/vector_store/index_metadata.json"
)


EMBED_MODEL = (
    "/root/autodl-tmp/models/bge-m3"
)


RERANK_MODEL = (
    "/root/autodl-tmp/models/bge-reranker-v2-m3"
)



# =====================================================
# 参数
# =====================================================

FAISS_TOP_K = 50

FINAL_TOP_K = 5



# =====================================================
# 加载知识库
# =====================================================


def load_kb():


    print("="*70)

    print("加载向量知识库")


    index = faiss.read_index(
        FAISS_PATH
    )


    with open(
        META_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        metadata=json.load(f)



    print(
        "向量数量:",
        index.ntotal
    )



    print("="*70)

    print("加载BGE-M3")


    embedder = SentenceTransformer(
        EMBED_MODEL,
        device="cuda"
    )


    print("="*70)

    print("加载Reranker")


    tokenizer = AutoTokenizer.from_pretrained(
        RERANK_MODEL
    )


    reranker = AutoModelForSequenceClassification.from_pretrained(
        RERANK_MODEL
    )


    reranker.cuda()

    reranker.eval()



    print(
        "GPU:",
        torch.cuda.get_device_name(0)
    )


    print("="*70)



    return (
        index,
        metadata,
        embedder,
        tokenizer,
        reranker
    )



# =====================================================
# FAISS召回
# =====================================================


def retrieve(
        question,
        index,
        metadata,
        embedder
):


    vector = embedder.encode(
        [question],
        normalize_embeddings=True
    )


    vector = vector.astype(
        "float32"
    )



    scores, ids = index.search(
        vector,
        FAISS_TOP_K
    )



    docs=[]


    for score,idx in zip(
        scores[0],
        ids[0]
    ):


        docs.append(
            {
                "faiss_score":float(score),
                "metadata":metadata[idx]
            }
        )


    return docs



# =====================================================
# Reranker
# =====================================================


def rerank(
        question,
        docs,
        tokenizer,
        reranker
):


    pairs=[]


    for doc in docs:


        data=doc["metadata"]


        content = (
            data.get("title","")
            +
            "\n"
            +
            data.get("text","")
        )


        pairs.append(
            [
                question,
                content
            ]
        )



    inputs=tokenizer(
        pairs,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )



    inputs={
        k:v.cuda()
        for k,v in inputs.items()
    }



    with torch.no_grad():

        outputs=reranker(
            **inputs
        )


        scores=outputs.logits.view(-1)



    for doc,score in zip(
        docs,
        scores
    ):

        doc["rerank_score"]=float(score)



    docs.sort(
        key=lambda x:x["rerank_score"],
        reverse=True
    )


    return docs[:FINAL_TOP_K]



# =====================================================
# 生成知识库回答格式
# =====================================================


def build_answer(
        question,
        results
):


    print("\n")
    print("="*80)

    print("问题:")
    print(question)


    print("="*80)

    print("检索到的知识依据:")



    for i,item in enumerate(
        results,
        1
    ):


        data=item["metadata"]


        print("\n")
        print(
            f"【依据{i}】"
        )


        print(
            "标准/法规:",
            data.get(
                "title",
                ""
            )
        )


        print(
            "编号:",
            data.get(
                "code",
                ""
            )
        )


        print(
            "类型:",
            data.get(
                "document_type",
                ""
            )
        )


        print(
            "相关度:",
            round(
                item["rerank_score"],
                4
            )
        )


        print(
            "\n原文:"
        )


        text=data.get(
            "text",
            ""
        )


        print(
            text[:1000]
        )


        print("-"*80)



# =====================================================
# 主程序
# =====================================================


if __name__=="__main__":


    (
        index,
        metadata,
        embedder,
        tokenizer,
        reranker

    ) = load_kb()



    while True:


        question=input(
            "\n请输入安全问题(q退出): "
        )


        if question.lower()=="q":

            break



        docs=retrieve(
            question,
            index,
            metadata,
            embedder
        )



        results=rerank(
            question,
            docs,
            tokenizer,
            reranker
        )



        build_answer(
            question,
            results
        )