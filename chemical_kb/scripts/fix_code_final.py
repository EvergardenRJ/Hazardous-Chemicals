import os
import json
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"


PDF_INV=BASE+"/data/pdf_inventory.csv"

PARSED=BASE+"/data/parsed_documents"



pdf=pd.read_csv(
    PDF_INV,
    dtype=str
).fillna("")



# path -> standard_code

pdf_dict={}


for _,r in pdf.iterrows():

    pdf_dict[
        r["path"]
    ]=r.get(
        "standard_code",
        ""
    )



count=0



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



    current=data.get(
        "code",
        ""
    )


    if current in [
        "",
        None,
        "nan"
    ]:


        pdf_path=data.get(
            "pdf_path",
            ""
        )


        code=pdf_dict.get(
            pdf_path,
            ""
        )


        data["code"]=code



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
    "补充编号:",
    count
)