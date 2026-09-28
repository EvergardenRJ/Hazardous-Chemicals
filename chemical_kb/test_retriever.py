import sys
import os


# 保证可以导入core
sys.path.append(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)


from core.embedding import EmbeddingModel
from core.vector_store import VectorStore
from core.reranker import Reranker
from core.retriever import Retriever



print("=" * 60)
print("初始化 Retriever 测试")
print("=" * 60)



# ==========================
# 1. 加载Embedding
# ==========================

print("\n加载 Embedding")

embedding = EmbeddingModel()



# ==========================
# 2. 加载FAISS
# ==========================

print("\n加载 Vector Store")

vector_store = VectorStore()



# ==========================
# 3. 加载Reranker
# ==========================

print("\n加载 Reranker")

reranker = Reranker()



# ==========================
# 4. 初始化Retriever
# ==========================


retriever = Retriever(
    embedding=embedding,
    vector_store=vector_store,
    reranker=reranker
)


print("\nRetriever 初始化完成")



# ==========================
# 测试问题
# ==========================


question = """
液氯发生泄漏后应该采取哪些应急处置措施？
"""


print("\n")
print("=" * 60)
print("测试问题")
print("=" * 60)

print(question)



# ==========================
# query测试
# ==========================

print("\n")
print("=" * 60)
print("开始检索")
print("=" * 60)



results = retriever.query(
    question,
    search_top_k=50,
    final_top_k=15
)



print("\n")
print("=" * 60)
print("检索完成")
print("=" * 60)



print(
    "返回数量:",
    len(results)
)



# ==========================
# 输出结果
# ==========================


for idx, item in enumerate(
    results,
    start=1
):

    metadata = item["metadata"]


    print("\n")
    print("-" * 60)

    print(
        f"Rank {idx}"
    )

    print(
        "标题:",
        metadata.get(
            "title",
            ""
        )
    )

    print(
        "编号:",
        metadata.get(
            "code",
            ""
        )
    )


    print(
        "FAISS score:",
        item.get(
            "score"
        )
    )


    print(
        "Rerank score:",
        item.get(
            "rerank_score"
        )
    )


    text = metadata.get(
        "text",
        ""
    )


    print(
        "文本预览:"
    )

    print(
        text[:300]
    )



print("\n")
print("=" * 60)
print("Retriever测试完成")
print("=" * 60)