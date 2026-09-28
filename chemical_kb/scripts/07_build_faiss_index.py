import os
import json
import numpy as np
import faiss



BASE="/root/autodl-tmp/chemical_kb"


# 输入

EMBEDDING_FILE = (
    BASE
    + "/data/embeddings/chunks_embeddings.npy"
)


METADATA_FILE = (
    BASE
    + "/data/embeddings/chunks_metadata.json"
)



# 输出

VECTOR_DIR = (
    BASE
    + "/data/vector_store"
)


INDEX_FILE = (
    VECTOR_DIR
    + "/faiss.index"
)


META_OUTPUT = (
    VECTOR_DIR
    + "/index_metadata.json"
)



os.makedirs(
    VECTOR_DIR,
    exist_ok=True
)



def main():


    print("="*60)

    print("加载embedding")



    embeddings=np.load(
        EMBEDDING_FILE
    )



    print(
        "向量shape:",
        embeddings.shape
    )



    # FAISS要求float32

    embeddings = embeddings.astype(
        "float32"
    )



    dimension = embeddings.shape[1]


    print(
        "维度:",
        dimension
    )



    print("="*60)

    print("创建FAISS Index")



    # cosine similarity

    index = faiss.IndexFlatIP(
        dimension
    )



    index.add(
        embeddings
    )


    print(
        "索引数量:",
        index.ntotal
    )



    print("="*60)

    print("保存FAISS")



    faiss.write_index(
        index,
        INDEX_FILE
    )


    print(
        INDEX_FILE
    )



    print("="*60)

    print("保存metadata")



    with open(
        METADATA_FILE,
        encoding="utf-8"
    ) as f:

        metadata=json.load(f)



    with open(
        META_OUTPUT,
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
        META_OUTPUT
    )



    print("="*60)

    print("FAISS建立完成")



if __name__=="__main__":

    main()