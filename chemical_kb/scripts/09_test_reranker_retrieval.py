import json
import torch
import faiss

from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
from transformers import AutoModelForSequenceClassification



# ============================================================
# 路径
# ============================================================


BASE = "/root/autodl-tmp/chemical_kb"


FAISS_PATH = (
    BASE
    + "/data/vector_store/faiss.index"
)


META_PATH = (
    BASE
    + "/data/vector_store/index_metadata.json"
)


EMBED_MODEL_PATH = (
    "/root/autodl-tmp/models/bge-m3"
)


RERANK_MODEL_PATH = (
    "/root/autodl-tmp/models/bge-reranker-v2-m3"
)



# ============================================================
# 参数
# ============================================================


FAISS_TOP_K = 50

FINAL_TOP_K = 5



# ============================================================
# 加载模型
# ============================================================


def load_models():


    print("=" * 70)

    print("加载FAISS")


    index = faiss.read_index(
        FAISS_PATH
    )


    print(
        "FAISS向量数量:",
        index.ntotal
    )


    print("=" * 70)

    print("加载metadata")


    with open(
        META_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        metadata = json.load(f)


    print(
        "metadata数量:",
        len(metadata)
    )



    print("=" * 70)

    print("加载BGE-M3")


    embed_model = SentenceTransformer(
        EMBED_MODEL_PATH,
        device="cuda"
    )


    embed_model.max_seq_length = 1024



    print("=" * 70)

    print("加载Reranker")


    tokenizer = AutoTokenizer.from_pretrained(
        RERANK_MODEL_PATH
    )


    reranker = AutoModelForSequenceClassification.from_pretrained(
        RERANK_MODEL_PATH
    )


    reranker.cuda()

    reranker.eval()



    print(
        "GPU:",
        torch.cuda.get_device_name(0)
    )


    print("=" * 70)


    return (
        index,
        metadata,
        embed_model,
        tokenizer,
        reranker
    )




# ============================================================
# FAISS召回
# ============================================================


def faiss_search(
        question,
        index,
        metadata,
        embed_model
):


    query_vector = embed_model.encode(
        [question],
        normalize_embeddings=True
    )


    query_vector = query_vector.astype(
        "float32"
    )



    scores, ids = index.search(
        query_vector,
        FAISS_TOP_K
    )



    candidates=[]


    for idx,score in zip(
        ids[0],
        scores[0]
    ):


        item = metadata[idx]


        candidates.append(
            {
                "faiss_score": float(score),
                "data": item
            }
        )


    return candidates





# ============================================================
# Reranker排序
# ============================================================


def rerank(
        question,
        candidates,
        tokenizer,
        reranker
):


    pairs=[]


    for item in candidates:


        text = item["data"].get(
            "text",
            ""
        )


        pairs.append(
            [
                question,
                text
            ]
        )



    inputs = tokenizer(
        pairs,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )


    inputs = {
        k:v.cuda()
        for k,v in inputs.items()
    }



    with torch.no_grad():

        outputs = reranker(
            **inputs
        )


        scores = outputs.logits.view(-1)



    for item,score in zip(
        candidates,
        scores
    ):

        item["rerank_score"] = float(score)



    candidates.sort(
        key=lambda x:x["rerank_score"],
        reverse=True
    )


    return candidates[:FINAL_TOP_K]





# ============================================================
# 输出结果
# ============================================================


def print_results(
        question,
        results
):


    print("\n")
    print("=" * 80)

    print(
        "问题:"
    )

    print(
        question
    )


    print("=" * 80)

    print(
        "最终Rerank结果"
    )



    for i,item in enumerate(
        results,
        1
    ):


        data=item["data"]


        print("\n")
        print(
            "Rank:",
            i
        )


        print(
            "FAISS score:",
            round(
                item["faiss_score"],
                4
            )
        )


        print(
            "Rerank score:",
            round(
                item["rerank_score"],
                4
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
            "标题:",
            data.get(
                "title",
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
            "页码:",
            data.get(
                "page_start",
                ""
            )
        )


        print(
            "内容:"
        )


        text=data.get(
            "text",
            ""
        )


        print(
            text[:500]
        )



# ============================================================
# 主程序
# ============================================================


if __name__ == "__main__":


    (
        index,
        metadata,
        embed_model,
        tokenizer,
        reranker
    ) = load_models()



    while True:


        question=input(
            "\n请输入问题(q退出): "
        )


        if question.lower()=="q":

            break



        candidates = faiss_search(
            question,
            index,
            metadata,
            embed_model
        )



        results = rerank(
            question,
            candidates,
            tokenizer,
            reranker
        )



        print_results(
            question,
            results
        )