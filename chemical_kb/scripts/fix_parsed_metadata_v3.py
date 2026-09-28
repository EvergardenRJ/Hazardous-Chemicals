import os
import json
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"


MASTER_FILE=BASE+"/data/parsed/document_master.csv"

PARSED_DIR=BASE+"/data/parsed_documents"



master=pd.read_csv(
    MASTER_FILE
)


# 防止nan

master=master.fillna("")



master_dict={}


for _,row in master.iterrows():

    master_dict[
        row["doc_id"]
    ]=row



count=0



for file in os.listdir(PARSED_DIR):


    if not file.endswith(".json"):
        continue


    path=os.path.join(
        PARSED_DIR,
        file
    )


    with open(
        path,
        encoding="utf-8"
    ) as f:

        data=json.load(f)



    doc_id=data["doc_id"]


    if doc_id not in master_dict:
        continue



    row=master_dict[doc_id]



    dtype=row["doc_type"]


    if dtype=="standard":

        dtype="标准"

    elif dtype=="regulation":

        dtype="法规"



    data["document_type"]=dtype


    code=row.get(
        "code",
        ""
    )


    # 空编号处理

    if not code:

        code=row.get(
            "standard_code",
            ""
        )


    if not code:

        code=row.get(
            "file_no",
            ""
        )


    data["code"]=code


    data["status"]=row.get(
        "status",
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



print(
    "修复:",
    count
)