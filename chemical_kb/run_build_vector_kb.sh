#!/bin/bash

ROOT=/root/autodl-tmp/chemical_kb
PYTHON=/root/miniconda3/envs/kb/bin/python


echo "===== Step1 检查数据 ====="

$PYTHON $ROOT/scripts/01_check_document_master.py


echo "===== Step2 PDF库存 ====="

$PYTHON $ROOT/scripts/02_build_pdf_inventory.py


echo "===== Step3 PDF匹配 ====="

$PYTHON $ROOT/scripts/03_match_document_pdf.py


echo "===== Step4 PDF解析 ====="

$PYTHON $ROOT/scripts/04_batch_parse_pdf_v2.py


echo "===== Step5 Chunk ====="

$PYTHON $ROOT/scripts/05_build_chunks_v2.py


echo "===== Step6 Embedding ====="

$PYTHON $ROOT/scripts/06_build_embedding.py


echo "===== Step7 FAISS ====="

$PYTHON $ROOT/scripts/07_build_faiss_index.py


echo "===== 完成 ====="

echo "向量知识库位置:"
echo "$ROOT/data/vector_store"
