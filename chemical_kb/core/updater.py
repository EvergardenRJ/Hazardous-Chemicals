import faiss
import json
import numpy as np


from core.config import (
    VECTOR_INDEX,
    VECTOR_METADATA
)


from core.embedding import EmbeddingModel
from core.knowledge import KeywordIndex
from core.config import BASE_DIR




class KnowledgeUpdater:


    def __init__(self):

        self.embedding = EmbeddingModel()



    def update(
        self,
        chunks
    ):


        if not chunks:

            print(
                "没有新增chunk"
            )

            return



        print(
            "生成embedding..."
        )


        texts = [
            c["text"]
            for c in chunks
        ]



        vectors = self.embedding.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=64,
            show_progress_bar=True
        )


        vectors=np.array(
            vectors
        ).astype(
            "float32"
        )



        print(
            "新增向量:",
            vectors.shape
        )



        # ==========================
        # 加载FAISS
        # ==========================


        index = faiss.read_index(
            str(VECTOR_INDEX)
        )


        old_count=index.ntotal



        index.add(
            vectors
        )



        faiss.write_index(
            index,
            str(VECTOR_INDEX)
        )



        print(
            f"FAISS: {old_count} -> {index.ntotal}"
        )



        # ==========================
        # 更新metadata
        # ==========================


        with open(
            VECTOR_METADATA,
            "r",
            encoding="utf-8"
        ) as f:

            metadata=json.load(f)



        old_metadata_count=len(metadata)



        # 防止重复chunk

        exist_ids=set(
            item.get(
                "chunk_id",
                ""
            )
            for item in metadata
        )



        new_chunks=[]



        for chunk in chunks:


            if (
                chunk["chunk_id"]
                not in exist_ids
            ):

                new_chunks.append(
                    chunk
                )



        metadata.extend(
            new_chunks
        )



        with open(
            VECTOR_METADATA,
            "w",
            encoding="utf-8"
        ) as f:


            json.dump(
                metadata,
                f,
                ensure_ascii=False,
                indent=2
            )



        print(
            f"metadata: {old_metadata_count} -> {len(metadata)}"
        )


        KeywordIndex(BASE_DIR / "data/search/keyword.sqlite").build(metadata)

        print(
            "知识库更新完成"
        )