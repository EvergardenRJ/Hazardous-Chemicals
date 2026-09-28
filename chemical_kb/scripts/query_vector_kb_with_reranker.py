import json
import faiss
import torch

from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification


# ============================================================
# 路径
# ============================================================

BASE = "/root/autodl-tmp/chemical_kb"

FAISS_PATH = BASE + "/data/vector_store/faiss.index"
META_PATH = BASE + "/data/vector_store/index_metadata.json"

EMBED_MODEL_PATH = "/root/autodl-tmp/models/bge-m3"
RERANK_MODEL_PATH = "/root/autodl-tmp/models/bge-reranker-v2-m3"


# ============================================================
# 参数
# ============================================================

FAISS_TOP_K = 50
FINAL_TOP_K = 5


# ============================================================
# 加载资源
# ============================================================

def load_resources():
    print("=" * 70)
    print("加载FAISS索引...")

    index = faiss.read_index(FAISS_PATH)

    print("FAISS向量数量:", index.ntotal)

    print("=" * 70)
    print("加载metadata...")

    with open(META_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    print("metadata数量:", len(metadata))

    print("=" * 70)
    print("加载Embedding模型...")

    embed_model = SentenceTransformer(
        EMBED_MODEL_PATH,
        device="cuda"
    )
    embed_model.max_seq_length = 1024

    print("=" * 70)
    print("加载Reranker模型...")

    tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL_PATH)

    reranker = AutoModelForSequenceClassification.from_pretrained(
        RERANK_MODEL_PATH
    )
    reranker.cuda()
    reranker.eval()

    print("GPU:", torch.cuda.get_device_name(0))
    print("=" * 70)

    return index, metadata, embed_model, tokenizer, reranker


# ============================================================
# 第一步：FAISS召回
# ============================================================

def faiss_retrieve(question, index, metadata, embed_model):
    query_vector = embed_model.encode(
        [question],
        normalize_embeddings=True
    )
    query_vector = query_vector.astype("float32")

    scores, ids = index.search(query_vector, FAISS_TOP_K)

    candidates = []

    for idx, score in zip(ids[0], scores[0]):
        item = metadata[idx]
        candidates.append({
            "faiss_score": float(score),
            "data": item
        })

    return candidates


# ============================================================
# 第二步：Reranker重排
# ============================================================

def rerank(question, candidates, tokenizer, reranker):
    pairs = []

    for item in candidates:
        text = item["data"].get("text", "")
        title = item["data"].get("title", "")
        code = item["data"].get("code", "")

        # 把编号 + 标题 + 正文一起送入reranker，效果更稳定
        candidate_text = f"{code}\n{title}\n{text}"
        pairs.append([question, candidate_text])

    inputs = tokenizer(
        pairs,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )

    inputs = {k: v.cuda() for k, v in inputs.items()}

    with torch.no_grad():
        outputs = reranker(**inputs)
        rerank_scores = outputs.logits.view(-1)

    for item, score in zip(candidates, rerank_scores):
        item["rerank_score"] = float(score)

    candidates.sort(
        key=lambda x: x["rerank_score"],
        reverse=True
    )

    return candidates[:FINAL_TOP_K]


# ============================================================
# 查询主函数
# ============================================================

def query_kb(question, index, metadata, embed_model, tokenizer, reranker):
    candidates = faiss_retrieve(
        question,
        index,
        metadata,
        embed_model
    )

    final_results = rerank(
        question,
        candidates,
        tokenizer,
        reranker
    )

    return final_results


# ============================================================
# 输出
# ============================================================

def print_results(question, results):
    print("\n")
    print("=" * 80)
    print("问题:")
    print(question)
    print("=" * 80)
    print("检索结果（FAISS召回 + Reranker重排）")

    for i, item in enumerate(results, 1):
        data = item["data"]

        print("\n")
        print("-" * 80)
        print("Rank:", i)
        print("FAISS score:", round(item.get("faiss_score", 0.0), 4))
        print("Rerank score:", round(item.get("rerank_score", 0.0), 4))
        print("标题:", data.get("title", ""))
        print("编号:", data.get("code", ""))
        print("类型:", data.get("document_type", ""))
        print("状态:", data.get("status", ""))

        page_start = data.get("page_start", "")
        page_end = data.get("page_end", "")
        if page_start == page_end:
            print("页码:", page_start)
        else:
            print("页码:", f"{page_start}-{page_end}")

        print("内容:")
        text = data.get("text", "")
        print(text[:800])


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    index, metadata, embed_model, tokenizer, reranker = load_resources()

    while True:
        question = input("\n请输入问题(q退出): ").strip()

        if question.lower() == "q":
            print("退出。")
            break

        if not question:
            print("问题不能为空，请重新输入。")
            continue

        results = query_kb(
            question,
            index,
            metadata,
            embed_model,
            tokenizer,
            reranker
        )

        print_results(question, results)