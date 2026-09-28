from core.rag import RAGSystem


rag = RAGSystem(
    retrieve_top_k=5
)


question = (
    "液氯发生泄漏后应该采取哪些应急处置措施？"
)


result = rag.answer(
    question
)


print("\n")
print("=" * 70)
print("问题")
print("=" * 70)

print(
    result["question"]
)


print("\n")
print("=" * 70)
print("RAG回答")
print("=" * 70)

print(
    result["answer"]
)


print("\n")
print("=" * 70)
print("检索证据")
print("=" * 70)


for i, item in enumerate(
    result["evidence"],
    start=1
):

    metadata = item["metadata"]


    print(
        f"\n------ 证据 {i} ------"
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
        "页码:",
        metadata.get(
            "page_start",
            ""
        ),
        "-",
        metadata.get(
            "page_end",
            ""
        )
    )


    print(
        "FAISS score:",
        item.get(
            "score",
            ""
        )
    )


    print(
        "Rerank score:",
        item.get(
            "rerank_score",
            ""
        )
    )


    print(
        "原文:"
    )


    print(
        metadata.get(
            "text",
            ""
        )[:800]
    )