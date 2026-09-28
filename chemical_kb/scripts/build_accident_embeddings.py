# -*- coding: utf-8 -*-
"""
事故 chunk Embedding (Phase 5)

复用现有 BGE-M3 模型与向量维度（IndexFlatIP + normalize_embeddings）。
对 chunks_accident.jsonl 中的事故 chunk 做 embedding。
输入文本与现有系统一致：title + "\n" + text。
输出 embeddings.npy + metadata.json，并校验行数/维度/NaN/Inf。
"""
import os
import json
import time

import numpy as np
import torch
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

BASE = "/root/autodl-tmp/chemical_kb"
OUT_ROOT = BASE + "/data/accident"
CHUNKS_FILE = OUT_ROOT + "/chunks/chunks_accident.jsonl"
EMBEDDINGS_DIR = OUT_ROOT + "/embeddings"
EMBEDDING_FILE = EMBEDDINGS_DIR + "/chunks_embeddings.npy"
METADATA_FILE = EMBEDDINGS_DIR + "/chunks_metadata.json"

MODEL_PATH = "/root/autodl-tmp/models/bge-m3"

BATCH_SIZE = 512
DEVICE = "cuda"
USE_FP16 = True   # 4090 上 fp16 约 2x 吞吐，embedding 余弦相似度几乎无影响


def check_gpu():
    print("=" * 60)
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
        print("显存: %.2f GB" %
              (torch.cuda.get_device_properties(0).total_memory / 1024 ** 3))
    else:
        print("警告: CUDA 不可用")


def load_model():
    print("=" * 60)
    print("加载 Embedding 模型")
    print("模型路径:", MODEL_PATH)
    model = SentenceTransformer(MODEL_PATH, device=DEVICE)
    model.max_seq_length = 1024
    if USE_FP16:
        model = model.half()
        print("精度: fp16")
    else:
        print("精度: fp32")
    print("设备:", model.device)
    dim = model.get_sentence_embedding_dimension()
    print("embedding 维度:", dim)
    if torch.cuda.is_available():
        print("加载后显存占用: %.2f GB" %
              (torch.cuda.memory_allocated(0) / 1024 ** 3))
    return model


def load_chunks():
    print("=" * 60)
    print("读取 chunks")
    texts, metadata = [], []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            text = item.get("title", "") + "\n" + item.get("text", "")
            texts.append(text)
            metadata.append(item)
    print("chunk 数量:", len(texts))
    return texts, metadata


def build_embedding(model, texts):
    print("=" * 60)
    print("开始生成向量")
    start = time.time()
    vectors = []
    total = len(texts)
    for i in tqdm(range(0, total, BATCH_SIZE), desc="Embedding"):
        batch = texts[i:i + BATCH_SIZE]
        emb = model.encode(batch, batch_size=BATCH_SIZE,
                           normalize_embeddings=True,
                           show_progress_bar=False,
                           convert_to_numpy=True)
        vectors.append(emb)
    vectors = np.vstack(vectors).astype("float32")
    print("向量生成完成, 耗时 %.1f 秒" % (time.time() - start))
    print("shape:", vectors.shape)
    if torch.cuda.is_available():
        print("峰值显存: %.2f GB / 总 %.2f GB" %
              (torch.cuda.max_memory_allocated(0) / 1024 ** 3,
               torch.cuda.get_device_properties(0).total_memory / 1024 ** 3))
    return vectors


def save_result(vectors, metadata):
    os.makedirs(EMBEDDINGS_DIR, exist_ok=True)
    print("=" * 60)
    print("保存向量与 metadata")
    np.save(EMBEDDING_FILE, vectors)
    print(EMBEDDING_FILE)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(METADATA_FILE)


def verify(vectors, metadata):
    print("=" * 60)
    print("校验")
    n, d = vectors.shape
    print("embedding 数量:", n, "== chunk 数量:", len(metadata),
          "->", "一致" if n == len(metadata) else "不一致!")
    print("embedding 维度:", d)
    print("NaN:", bool(np.isnan(vectors).any()))
    print("Inf:", bool(np.isinf(vectors).any()))
    print("dtype:", vectors.dtype)


def main():
    check_gpu()
    model = load_model()
    texts, metadata = load_chunks()
    if not texts:
        print("没有 chunk，请先运行 build_accident_chunks.py")
        return
    vectors = build_embedding(model, texts)
    save_result(vectors, metadata)
    verify(vectors, metadata)
    print("=" * 60)
    print("全部完成")


if __name__ == "__main__":
    main()
