import os
import json
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"


MASTER_FILE=BASE+"/data/parsed/document_master.csv"

PARSED_DIR=BASE+"/data/parsed_documents"



# ============================
# 读取主表
# ============================

master=pd.read_csv(
    MASTER_FILE
)


print("主表数量:",len(master))


master_dict={}


for _,row in master.iterrows():

    master_dict[
        row["doc_id"]
    ]=row



# ============================
# 修复JSON
# ============================


count=0
not_found=[]


for file in os.listdir(PARSED_DIR):


    if not file.endswith(".json"):
        continue


    path=os.path.join(
        PARSED_DIR,
        file
    )


    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        data=json.load(f)



    doc_id=data["doc_id"]


    if doc_id not in master_dict:

        not_found.append(doc_id)
        continue



    row=master_dict[doc_id]



    # 标准化类型

    doc_type=row["doc_type"]


    if doc_type=="standard":

        doc_type="标准"


    elif doc_type=="regulation":

        doc_type="法规"



    data["document_type"]=doc_type


    data["code"]=row.get(
        "code",
        ""
    )


    data["status"]=row.get(
        "status",
        ""
    )


    data["source"]=row.get(
        "source",
        ""
    )



    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:


        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


    count+=1



print("="*50)

print(
    "修复成功:",
    count
)


print(
    "未找到:",
    len(not_found)
)


if not_found:

    print(
        not_found[:10]
    )