import numpy as np


def _diversity_filter(
        self,
        results,
        max_per_doc=2
):

    """
    控制同一个文档最多出现次数
    """

    final=[]

    doc_count={}


    for item in results:

        doc_id=item["metadata"].get(
            "doc_id"
        )


        if doc_count.get(doc_id,0)>=max_per_doc:
            continue


        final.append(item)

        doc_count[doc_id]=(
            doc_count.get(doc_id,0)+1
        )


    return final

class Retriever:

    def __init__(
        self,
        embedding,
        vector_store,
        reranker
    ):
        """
        初始化Retriever

        参数:
        embedding:
            BGE-M3 embedding模型

        vector_store:
            FAISS向量库

        reranker:
            BGE reranker模型
        """

        self.embedding = embedding
        self.vector_store = vector_store
        self.reranker = reranker


    def query(
        self,
        question,
        search_top_k=50,
        final_top_k=15
    ):
        """
        检索知识库

        参数:

        question:
            用户问题

        search_top_k:
            FAISS初步召回数量

        final_top_k:
            reranker最终返回数量


        返回:

        [
            {
                "score": float,
                "rerank_score": float,
                "metadata": {}
            }
        ]

        """

        # ==========================
        # Step 1
        # Query Embedding
        # ==========================

        query_vector = self.embedding.encode(
            question
        )


        # 转numpy
        if not isinstance(
            query_vector,
            np.ndarray
        ):
            query_vector = np.array(
                query_vector
            )


        # ==========================
        # Step 2
        # FAISS Search
        # ==========================

        search_results = self.vector_store.search(
            query_vector,
            top_k=search_top_k
        )


        if not search_results:
            return []


        # ==========================
        # Step 3
        # Reranker
        # ==========================

                # ===============================
        # Step 3: Rerank
        # ===============================

        reranked_results = self.reranker.rerank(
            question,
            search_results
        )


        print("="*60)
        print("DEBUG RERANK RESULT")
        print(type(reranked_results))
        print(len(reranked_results))

        if len(reranked_results) > 0:
            print(reranked_results[0])

        print("="*60)



        # ===============================
        # Step 4: 构造最终结果
        # ===============================

        final_results = []


        for item in reranked_results:

            metadata = item["metadata"]

            final_results.append(
                {
                    "score": item.get(
                        "score",
                        0
                    ),

                    "rerank_score": item.get(
                        "rerank_score",
                        0
                    ),

                    "metadata": metadata
                }
            )


       # return final_results[:top_k]
        final_results=self._diversity_filter(
            final_results,
            max_per_doc=2
        )


#return final_results[:top_k]
        return final_results[:final_top_k]


        # ==========================
        # Step 5
        # 排序
        # ==========================

        reranked_results.sort(
            key=lambda x:
                x["rerank_score"],
            reverse=True
        )


        # ==========================
        # Step 6
        # 返回TopK
        # ==========================

        return reranked_results[
            :final_top_k
        ]

    # def _diversity_filter(
    #         self,
    #         results,
    #         max_results=5
    # ):
    #     """
    #     文档多样性过滤

    #     避免TopK结果全部来自同一个文档
    #     """

    #     final_results = []

    #     used_docs = set()


    #     # 第一轮
    #     # 优先不同文档
    #     for item in results:

    #         metadata = item.get(
    #             "metadata",
    #             {}
    #         )

    #         doc_id = metadata.get(
    #             "doc_id"
    #         )


    #         if doc_id not in used_docs:

    #             final_results.append(item)

    #             used_docs.add(doc_id)


    #         if len(final_results) >= max_results:
    #             return final_results



    #     # 第二轮
    #     # 如果不足，再补充同文档结果
    #     for item in results:

    #         if item not in final_results:

    #             final_results.append(item)


    #         if len(final_results) >= max_results:
    #             break


    #     return final_results

    def _diversity_filter(
            self,
            results,
            max_results=5,
            max_per_doc=2
    ):
        """
        文档多样性过滤

        参数:
            results:
                reranker排序后的结果

            max_results:
                最终返回数量

            max_per_doc:
                单个文档最多保留chunk数量

        目的:
            防止TopK全部来自同一个PDF
        """

        final_results = []

        doc_count = {}


        for item in results:


            metadata = item.get(
                "metadata",
                {}
            )


            doc_id = metadata.get(
                "doc_id",
                "unknown"
            )


            # 当前文档已经达到限制
            if doc_count.get(doc_id,0) >= max_per_doc:
                continue



            final_results.append(item)


            doc_count[doc_id] = (
                doc_count.get(doc_id,0)+1
            )



            if len(final_results)>=max_results:
                break



        return final_results

    def retrieve(
        self,
        question,
        top_k=5
    ):
        """
        兼容旧版本接口

        原来的RAG可能调用:

        retriever.retrieve()

        保留避免影响旧代码

        """

        return self.query(
            question,
            search_top_k=50,
            final_top_k=top_k
        )