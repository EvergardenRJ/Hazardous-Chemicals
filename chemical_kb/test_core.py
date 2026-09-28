from core.embedding import EmbeddingModel


if __name__ == "__main__":

    model = EmbeddingModel()

    vec = model.encode(
        "液氯泄漏事故如何处理"
    )

    print("向量shape:")
    print(vec.shape)