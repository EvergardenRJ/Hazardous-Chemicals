import os
import json
import time

import numpy as np
import torch

from tqdm import tqdm
from sentence_transformers import SentenceTransformer



# ============================================================
# 路径配置
# ============================================================

BASE = "/root/autodl-tmp/chemical_kb"


# 输入chunk

INPUT_FILE = (
    BASE
    + "/data/chunks/chunks_v2.jsonl"
)


# 输出目录

OUTPUT_DIR = (
    BASE
    + "/data/embeddings"
)


EMBEDDING_FILE = (
    OUTPUT_DIR
    + "/chunks_embeddings.npy"
)


METADATA_FILE = (
    OUTPUT_DIR
    + "/chunks_metadata.json"
)


# 本地模型

MODEL_PATH = (
    "/root/autodl-tmp/models/bge-m3"
)



# ============================================================
# 参数
# ============================================================


# 4090D 推荐

BATCH_SIZE = 128


DEVICE = "cuda"



# ============================================================
# 加载模型
# ============================================================


def load_model():


    print("="*60)

    print("加载Embedding模型")


    print(
        "模型:",
        MODEL_PATH
    )


    model = SentenceTransformer(
        MODEL_PATH,
        device=DEVICE
    )


    # chunk已经切分
    # 设置最大长度

    model.max_seq_length = 1024


    print(
        "设备:",
        model.device
    )


    return model




# ============================================================
# 读取chunk
# ============================================================


def load_chunks():


    print("="*60)

    print("读取chunks")


    texts = []

    metadata = []


    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:


        for line in f:


            item = json.loads(line)


            # embedding输入

            text = (
                item.get(
                    "title",
                    ""
                )
                +
                "\n"
                +
                item.get(
                    "text",
                    ""
                )
            )


            texts.append(text)


            metadata.append(item)



    print(
        "chunk数量:",
        len(texts)
    )


    return texts, metadata





# ============================================================
# embedding
# ============================================================


def build_embedding(
    model,
    texts
):


    print("="*60)

    print("开始生成向量")


    start=time.time()


    vectors=[]


    total=len(texts)



    for i in tqdm(
        range(
            0,
            total,
            BATCH_SIZE
        ),
        desc="Embedding"
    ):


        batch = texts[
            i:
            i+BATCH_SIZE
        ]



        emb = model.encode(

            batch,

            batch_size=BATCH_SIZE,

            normalize_embeddings=True,

            show_progress_bar=False,

            convert_to_numpy=True

        )


        vectors.append(
            emb
        )



    vectors=np.vstack(
        vectors
    )


    cost=time.time()-start


    print(
        "向量生成完成"
    )


    print(
        "耗时:",
        round(cost,2),
        "秒"
    )


    print(
        "shape:",
        vectors.shape
    )


    return vectors





# ============================================================
# 保存
# ============================================================


def save_result(
    vectors,
    metadata
):


    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    print("="*60)

    print("保存向量")



    np.save(
        EMBEDDING_FILE,
        vectors
    )


    print(
        EMBEDDING_FILE
    )



    print("保存metadata")



    with open(
        METADATA_FILE,
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
        METADATA_FILE
    )






# ============================================================
# 检查GPU
# ============================================================


def check_gpu():


    print("="*60)


    if torch.cuda.is_available():


        print(
            "GPU:",
            torch.cuda.get_device_name(0)
        )


        print(
            "显存:",
            round(
                torch.cuda.get_device_properties(0).total_memory/1024**3,
                2
            ),
            "GB"
        )


    else:


        print(
            "警告: CUDA不可用"
        )





# ============================================================
# main
# ============================================================


def main():


    check_gpu()


    model=load_model()


    texts,metadata=load_chunks()



    vectors=build_embedding(
        model,
        texts
    )



    save_result(
        vectors,
        metadata
    )


    print("="*60)

    print("全部完成")




if __name__=="__main__":

    main()