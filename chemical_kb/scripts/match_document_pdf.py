import pandas as pd
import re
from rapidfuzz import fuzz


DOCUMENT_MASTER = (
    "/root/autodl-tmp/chemical_kb/"
    "data/parsed/document_master.csv"
)


PDF_INVENTORY = (
    "/root/autodl-tmp/chemical_kb/"
    "data/pdf_inventory.csv"
)


OUTPUT = (
    "/root/autodl-tmp/chemical_kb/"
    "data/document_pdf_mapping.csv"
)



def normalize(text):

    if pd.isna(text):
        return ""

    text=str(text)

    text=text.upper()

    # 删除中文符号、空格、特殊字符

    text=re.sub(
        r"[^A-Z0-9\u4e00-\u9fa5]",
        "",
        text
    )

    return text



def match_score(a,b):

    return fuzz.ratio(
        normalize(a),
        normalize(b)
    )



documents=pd.read_csv(
    DOCUMENT_MASTER
)


pdfs=pd.read_csv(
    PDF_INVENTORY
)


results=[]


matched_pdf=set()



for _,doc in documents.iterrows():

    best=None
    best_score=0
    method=""



    # =====================
    # 1 标准编号匹配
    # =====================

    if doc["doc_type"]=="standard":

        doc_code=normalize(
            doc["code"]
        )


        for idx,pdf in pdfs.iterrows():

            pdf_code=normalize(
                pdf["standard_code"]
            )


            if (
                doc_code
                and
                doc_code==pdf_code
            ):

                best=pdf
                best_score=100
                method="standard_code"
                break



    # =====================
    # 2 标题匹配
    # =====================

    if best is None:


        for idx,pdf in pdfs.iterrows():


            score=match_score(
                doc["title"],
                pdf["filename"]
            )


            if score>best_score:

                best_score=score
                best=pdf
                method="title"



    # =====================
    # 保存
    # =====================


    if best is not None and best_score>=70:

        matched_pdf.add(
            best["pdf_id"]
        )

        results.append({

            "doc_id":
                doc["doc_id"],

            "title":
                doc["title"],

            "pdf_id":
                best["pdf_id"],

            "pdf_path":
                best["path"],

            "match_method":
                method,

            "confidence":
                round(
                    best_score/100,
                    3
                )

        })

    else:

        results.append({

            "doc_id":
                doc["doc_id"],

            "title":
                doc["title"],

            "pdf_id":"",

            "pdf_path":"",

            "match_method":
                "unmatched",

            "confidence":0

        })



result=pd.DataFrame(results)


result.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)



print("="*60)

print("匹配完成")

print("="*60)


print(
    "总文档:",
    len(result)
)


print(
    "\n匹配情况:"
)


print(
    result["match_method"]
    .value_counts()
)


print(
    "\n平均置信度:"
)

print(
    result[
        result["confidence"]>0
    ]
    ["confidence"]
    .mean()
)


print(
    "\n未匹配数量:"
)

print(
    len(
        result[
            result["confidence"]==0
        ]
    )
)


print("\n输出:")
print(OUTPUT)