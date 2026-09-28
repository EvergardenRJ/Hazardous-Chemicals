import os
import json
import pandas as pd


BASE="/root/autodl-tmp/chemical_kb"

DIR=os.path.join(
    BASE,
    "data/parsed_documents"
)


files=[
    f for f in os.listdir(DIR)
    if f.endswith(".json")
]


print("="*60)
print("解析文件数量:")
print(len(files))


results=[]


empty_docs=[]

empty_pages=[]


for f in files:

    path=os.path.join(
        DIR,
        f
    )


    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as fp:

            data=json.load(fp)



        chars=data.get(
            "char_count",
            0
        )


        pages=data.get(
            "page_count",
            0
        )


        if chars <100:

            empty_docs.append(
                f
            )


        for p in data["pages"]:

            if len(
                p["text"].strip()
            ) <10:

                empty_pages.append(
                    (
                        f,
                        p["page"]
                    )
                )


        results.append(

            {

            "file":f,

            "pages":pages,

            "chars":chars,

            }

        )


    except Exception as e:

        print(
            "ERROR",
            f,
            e
        )



df=pd.DataFrame(results)


print("\n字符统计:")
print(df["chars"].describe())


print("\n空文档:")
print(
    len(empty_docs)
)


print("\n空页面:")
print(
    len(empty_pages)
)



df.sort_values(
    "chars"
).head(20).to_csv(
    BASE+"/data/parse_low_quality.csv",
    index=False,
    encoding="utf-8-sig"
)


print("\n低质量列表:")
print(
    BASE+"/data/parse_low_quality.csv"
)