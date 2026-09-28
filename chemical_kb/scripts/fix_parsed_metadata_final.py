import os
import json
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"


MASTER=BASE+"/data/parsed/document_master.csv"

PARSED=BASE+"/data/parsed_documents"



df=pd.read_csv(
    MASTER,
    dtype=str
)


# 删除nan

df=df.fillna("")



master={}


for _,row in df.iterrows():

    master[row["doc_id"]]=row



success=0

fail=[]



for file in os.listdir(PARSED):


    if not file.endswith(".json"):
        continue



    path=os.path.join(
        PARSED,
        file
    )


    with open(
        path,
        encoding="utf-8"
    ) as f:

        data=json.load(f)



    doc_id=data["doc_id"]



    if doc_id not in master:

        fail.append(doc_id)

        continue



    row=master[doc_id]



    # 类型

    if row["doc_type"]=="standard":

        dtype="标准"

    elif row["doc_type"]=="regulation":

        dtype="法规"

    else:

        dtype=row["doc_type"]



    data["document_type"]=dtype


    # 关键：编号

    data["code"]=row["code"]


    data["status"]=row["status"]


    data["source"]=row["source"]


    data["topic"]=row["topic"]


    data["issuer"]=row["issuer"]



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


    success+=1



print("="*60)

print(
    "成功:",
    success
)

print(
    "失败:",
    len(fail)
)

if fail:
    print(fail[:10])