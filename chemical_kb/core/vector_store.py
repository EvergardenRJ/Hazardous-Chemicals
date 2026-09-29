#封装FAISS加载

import faiss
import json

from core.config import (
    VECTOR_INDEX,
    VECTOR_METADATA
)



class VectorStore:


    def __init__(self, index_path=None, metadata_path=None):

        print("加载FAISS")

        self.index = faiss.read_index(
            str(index_path or VECTOR_INDEX)
        )


        with open(
            metadata_path or VECTOR_METADATA,
            "r",
            encoding="utf-8"
        ) as f:

            self.metadata=json.load(f)


        print(
            "向量数量:",
            self.index.ntotal
        )



    def search(
        self,
        vector,
        top_k=50
    ):


        scores, ids = self.index.search(
            vector,
            top_k
        )


        results=[]


        for score,idx in zip(
            scores[0],
            ids[0]
        ):

            if idx < 0 or idx >= len(self.metadata):
                continue
            results.append(
                {
                    "score":float(score),
                    "metadata":self.metadata[idx]
                }
            )


        return results