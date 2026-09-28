import pandas as pd
import os
import re


INPUT = (
    "/root/autodl-tmp/chemical_kb/"
    "data/source/标准汇总.xlsx"
)

OUTPUT = (
    "/root/autodl-tmp/chemical_kb/"
    "data/parsed/document_master.csv"
)


os.makedirs(
    os.path.dirname(OUTPUT),
    exist_ok=True
)


def clean_text(x):

    if pd.isna(x):
        return ""

    return str(x).strip()



def normalize_status(x):

    x = clean_text(x)

    if "现行" in x:
        return "ACTIVE"

    if "废止" in x:
        return "ABOLISHED"

    if "失效" in x:
        return "INVALID"

    return "UNKNOWN"



def normalize_code(x):

    x = clean_text(x)

    x = x.replace(
        "—",
        "-"
    )

    x = re.sub(
        r"\s+",
        " ",
        x
    )

    return x



def make_standard_id(row):

    code = row["标准编号"]

    if pd.isna(code):
        code = row["文件编号"]

    code = normalize_code(code)

    code = (
        code
        .replace("/", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )

    return "STD_" + code



def make_reg_id(row):

    return (
        "REG_"
        +
        clean_text(
            row["记录ID"]
        )
    )



documents=[]


# ===================
# 标准
# ===================

std = pd.read_excel(
    INPUT,
    sheet_name="标准汇总"
)


for _,r in std.iterrows():

    documents.append({

        "doc_id":
            make_standard_id(r),

        "doc_type":
            "standard",

        "code":
            normalize_code(
                r["标准编号"]
            ),

        "title":
            clean_text(
                r["文件名称"]
            ),

        "status":
            normalize_status(
                r["状态"]
            ),

        "publish_date":
            r["发布日期"],

        "effective_date":
            r["实施日期"],

        "issuer":
            clean_text(
                r["发布部门"]
            ),

        "organization":
            clean_text(
                r["归口单位"]
            ),

        "topic":
            clean_text(
                r["主题分类"]
            ),

        "region":"",

        "level":"标准",

        "replacement":
            clean_text(
                r["替代情况"]
            ),

        "record_id":"",

        "attachment_id":"",

        "source":
            clean_text(
                r["数据来源"]
            ),

        "pdf_path":""

    })



# ===================
# 法规
# ===================

reg = pd.read_excel(
    INPUT,
    sheet_name="法规"
)


for _,r in reg.iterrows():

    documents.append({

        "doc_id":
            make_reg_id(r),

        "doc_type":
            "regulation",

        "code":
            normalize_code(
                r["文件编号"]
            ),

        "title":
            clean_text(
                r["标题"]
            ),

        "status":
            normalize_status(
                r["状态"]
            ),

        "publish_date":
            r["发布日期"],

        "effective_date":
            r["实施日期"],

        "issuer":
            clean_text(
                r["发布机构"]
            ),

        "organization":"",

        "topic":
            clean_text(
                r["主分类"]
            ),

        "region":
            clean_text(
                r["地区"]
            ),

        "level":
            clean_text(
                r["法规层级"]
            ),

        "replacement":
            clean_text(
                r["替代文件"]
            ),

        "record_id":
            clean_text(
                r["记录ID"]
            ),

        "attachment_id":
            clean_text(
                r["附件ID"]
            ),

        "source":
            clean_text(
                r["数据来源"]
            ),

        "pdf_path":""

    })



df=pd.DataFrame(documents)


df.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


print("="*50)
print("完成")
print("="*50)

print("总数量:",len(df))

print(
    df["doc_type"].value_counts()
)

print("\n状态:")
print(
    df["status"].value_counts()
)

print("\n输出:")
print(OUTPUT)