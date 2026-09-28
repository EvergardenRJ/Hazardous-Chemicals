import os
import subprocess
import time


# ==========================================================
# 路径配置
# ==========================================================

ROOT = "/root/autodl-tmp/chemical_kb"

PYTHON = "/root/miniconda3/envs/kb/bin/python"


SCRIPTS = [

    # 数据检查
    "01_check_document_master.py",

    # PDF扫描
    "02_build_pdf_inventory.py",

    # 文档-PDF匹配
    "03_match_document_pdf.py",

    # PDF解析OCR
    "04_batch_parse_pdf_v2.py",

    # chunk构建
    "05_build_chunks_v2.py",

    # embedding
    "06_build_embedding.py",

    # FAISS
    "07_build_faiss_index.py",

]


# ==========================================================
# 执行函数
# ==========================================================


def run_script(script):


    path = os.path.join(
        ROOT,
        "scripts",
        script
    )


    print("\n")
    print("="*70)

    print(
        "开始执行:",
        script
    )

    print("="*70)



    start=time.time()



    result=subprocess.run(
        [
            PYTHON,
            path
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )


    print(result.stdout)



    cost=time.time()-start


    if result.returncode != 0:

        print(
            "❌ 执行失败:",
            script
        )

        print(
            "退出码:",
            result.returncode
        )

        exit(1)


    else:

        print(
            "✅ 完成:",
            script
        )

        print(
            "耗时:",
            round(cost,2),
            "秒"
        )





# ==========================================================
# 主程序
# ==========================================================


if __name__=="__main__":


    print("="*70)

    print("危险化学品安全领域向量知识库构建")

    print("="*70)



    total=time.time()



    for script in SCRIPTS:

        run_script(script)



    print("\n")
    print("="*70)

    print("🎉 向量知识库构建完成")

    print("="*70)



    print(
        """
最终文件:

1. 文档解析:
data/parsed_documents/

2. Chunk:
data/chunks/chunks.jsonl

3. Embedding:
data/embeddings/chunks_embeddings.npy

4. FAISS:
data/vector_store/faiss.index

5. Metadata:
data/vector_store/index_metadata.json

"""
    )



    print(
        "总耗时:",
        round(time.time()-total,2),
        "秒"
    )