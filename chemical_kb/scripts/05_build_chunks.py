import os
import json
import re
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"

INPUT_DIR=os.path.join(
    BASE,
    "data/parsed_documents"
)

OUTPUT_DIR=os.path.join(
    BASE,
    "data/chunks"
)

OUTPUT_FILE=os.path.join(
    OUTPUT_DIR,
    "chunks.jsonl"
)


os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)



# =========================
# 文本标准化
# =========================

def normalize_text(text):


    # 数字和标题之间补空格

    text=re.sub(
        r'(\d)([^\d\s])',
        r'\1 \2',
        text
    )


    # 小数章节不要破坏
    text=re.sub(
        r'(\d+\.\d+)([^\s])',
        r'\1 \2',
        text
    )


    text=text.replace(
        "—",
        "-"
    )


    return text



# =========================
# 质量等级
# =========================

def quality_level(chars):


    if chars>=1000:

        return "normal"

    elif chars>=500:

        return "short"

    else:

        return "very_short"





# =========================
# 标准章节切分
# =========================


def split_standard(text):


    pattern=r'(?=\n?\d+(\.\d+)*\s)'


    sections=re.split(
        pattern,
        text
    )


    return [
        s.strip()
        for s in sections
        if len(s.strip())>50
    ]



# =========================
# 法规章节切分
# =========================


def split_regulation(text):


    pattern=r'(?=\n?(第[一二三四五六七八九十百]+条))'


    sections=re.split(
        pattern,
        text
    )


    return [
        s.strip()
        for s in sections
        if len(s.strip())>30
    ]



# =========================
# fallback切分
# =========================


def split_long(text,max_len=1200):


    result=[]


    while len(text)>max_len:

        pos=text.rfind(
            "。",
            0,
            max_len
        )


        if pos==-1:

            pos=max_len


        result.append(
            text[:pos+1]
        )


        text=text[pos+1:]


    if text.strip():

        result.append(text)


    return result





# =========================
# 主程序
# =========================


chunks=[]


files=[
    f for f in os.listdir(INPUT_DIR)
    if f.endswith(".json")
]


print(
    "文档数量:",
    len(files)
)



for file in files:


    path=os.path.join(
        INPUT_DIR,
        file
    )


    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        doc=json.load(f)



    full_text="\n".join(

        [
            p["text"]
            for p in doc["pages"]
        ]

    )


    full_text=normalize_text(
        full_text
    )


    chars=len(full_text)



    dtype=doc.get(
        "document_type",
        "unknown"
    )



    if dtype=="标准":

        parts=split_standard(
            full_text
        )

    else:

        parts=split_regulation(
            full_text
        )



    if len(parts)==0:

        parts=split_long(
            full_text
        )



    for idx,part in enumerate(parts):


        if len(part)>1500:

            subparts=split_long(part)

        else:

            subparts=[part]



        for j,chunk in enumerate(subparts):


            if len(chunk)<50:

                continue



            chunks.append(

                {

                "chunk_id":
                f"{doc['doc_id']}_{idx}_{j}",


                "doc_id":
                doc["doc_id"],


                "title":
                doc.get(
                    "title",
                    ""
                ),


                "document_type":
                dtype,


                "quality":
                quality_level(chars),


                "text":
                chunk

                }

            )



print(
    "生成chunk数量:",
    len(chunks)
)



with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:


    for c in chunks:

        f.write(
            json.dumps(
                c,
                ensure_ascii=False
            )
            +"\n"
        )



print(
    "保存:",
    OUTPUT_FILE
)



df=pd.DataFrame(chunks)

print(df["document_type"].value_counts())

print(df["quality"].value_counts())