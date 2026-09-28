from core.rag import RAGSystem


rag = RAGSystem(
    retrieve_top_k=5
)


questions = [

    "液氯在储存过程中有哪些安全要求？",

    "液氯相关作业人员需要采取哪些个体防护措施？",

    "液氯发生泄漏后应该采取哪些应急处置措施？",

    "液氯需要配置哪些安全设施和自动控制措施？"

]


for question in questions:

    print("\n")
    print("#" * 80)
    print("测试问题：")
    print(question)
    print("#" * 80)


    result = rag.retrieve_evidence(
        question=question,
        top_k=5,
        verbose=True
    )


    print("\n最终Evidence:")


    for i, item in enumerate(
        result["evidence"],
        start=1
    ):

        metadata = item[
            "metadata"
        ]

        print(
            f"\n{i}."
        )

        print(
            metadata.get(
                "title",
                ""
            )
        )

        print(
            metadata.get(
                "code",
                ""
            )
        )

        print(
            metadata.get(
                "text",
                ""
            )[:800]
        )