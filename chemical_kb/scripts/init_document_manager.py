import json
import pandas as pd
from pathlib import Path
from collections import defaultdict


BASE_DIR = Path(
    "/root/autodl-tmp/chemical_kb"
)


MASTER_FILE = (
    BASE_DIR /
    "data/parsed/document_master.csv"
)



CHUNK_DIR = (
    BASE_DIR /
    "data/chunks"
)


chunk_files = list(
    CHUNK_DIR.glob(
        "*.jsonl"
    )
)


if len(chunk_files)==0:

    raise FileNotFoundError(
        "没有找到chunk文件"
    )


CHUNK_FILE = chunk_files[0]


print(
    "使用chunk文件:",
    CHUNK_FILE
)


OUTPUT_FILE = (
    BASE_DIR /
    "data/knowledge/documents.json"
)



print("="*50)

print("初始化文档管理数据库")



# ==========================
# 读取文档主表
# ==========================

df = pd.read_csv(
    MASTER_FILE
)


print(
    "文档主表:",
    len(df)
)



# ==========================
# 统计chunk数量
# ==========================

chunk_count = defaultdict(int)



with open(
    CHUNK_FILE,
    "r",
    encoding="utf-8"
) as f:


    for line in f:

        item=json.loads(line)


        chunk_count[
            item["doc_id"]
        ] += 1



print(
    "Chunk统计完成"
)



# ==========================
# 创建documents.json
# ==========================


documents=[]



for _,row in df.iterrows():


    doc_id=row["doc_id"]



    document={

        "doc_id":
            doc_id,


        "title":
            row.get(
                "title",
                ""
            ),


        "document_type":
            row.get(
                "level",
                row.get(
                    "doc_type",
                    ""
                )
            ),


        "code":
            row.get(
                "code",
                ""
            ),


        "source":
            row.get(
                "source",
                ""
            ),


        "pdf_path":
            str(
                row.get(
                    "pdf_path",
                    ""
                )
            ),


        "chunks":
            chunk_count.get(
                doc_id,
                0
            ),


        "status":
            "active"

    }


    documents.append(
        document
    )



# ==========================
# 保存
# ==========================


OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)



with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:


    json.dump(
        documents,
        f,
        ensure_ascii=False,
        indent=2
    )



print("="*50)

print(
    "完成"
)


print(
    "生成文档数量:",
    len(documents)
)


print(
    "保存:",
    OUTPUT_FILE
)