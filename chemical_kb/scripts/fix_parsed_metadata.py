import os
import json
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"


mapping=pd.read_csv(
    BASE+"/data/document_pdf_mapping.csv"
)


mapping_dict={}


for _,row in mapping.iterrows():

    mapping_dict[
        row["doc_id"]
    ]=row



DIR=BASE+"/data/parsed_documents"


count=0


for file in os.listdir(DIR):

    if not file.endswith(".json"):
        continue


    path=os.path.join(
        DIR,
        file
    )


    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        data=json.load(f)



    doc_id=data["doc_id"]


    if doc_id in mapping_dict:


        row=mapping_dict[doc_id]


        data["document_type"]=row.get(
            "doc_type",
            row.get(
                "document_type",
                "unknown"
            )
        )


        data["status"]=row.get(
            "status",
            ""
        )


        data["code"]=row.get(
            "code",
            ""
        )


        count+=1



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



print(
    "修复数量:",
    count
)