import os
import re
import pandas as pd


PDF_ROOT = (
    "/root/autodl-tmp/chemical_kb/data/pdf"
)


OUTPUT = (
    "/root/autodl-tmp/chemical_kb/data/pdf_inventory.csv"
)



# def extract_standard_code(filename):

#     """
#     从PDF文件名提取标准编号

#     示例:
#     AQ 3011-2007.pdf
#     DB11_T 1191.1-2018_xxx.pdf
#     GB50016-2014.pdf

#     输出:
#     AQ3011-2007
#     """

#     name = filename.replace(".pdf", "")


#     pattern = (
#         r"(GB|GB/T|AQ|AQ/T|DB\d+/?T?|"
#         r"GA|HG|HG/T|JT|JT/T|SY|SN|T)"
#         r"[\s_-]*"
#         r"[\d\.]+"
#         r"[\s_-]*"
#         r"\d{4}"
#     )


#     result = re.search(
#         pattern,
#         name,
#         re.I
#     )


#     if result:

#         code = result.group()

#         code = (
#             code
#             .replace("_","/")
#             .replace(" ","")
#             .rstrip(".")
#         )

#         return code


#     return ""


def extract_standard_code(filename):

    """
    提取标准编号
    """

    name = filename.replace(".pdf","")


    patterns = [

        # GB/T
        r"GB[_\s]?/?T[_\s]*\d+[\.\d]*[-_]\d{4}",

        # DB地方标准
        r"DB\d+[_\s]?T[_\s]*\d+[\.\d]*[-_]\d{4}",

        # AQ/T
        r"AQ[_\s]?T[_\s]*\d+[\.\d]*[-_]\d{4}",

        # AQ
        r"AQ[_\s]*\d+[\.\d]*[-_]\d{4}",

        # GA
        r"GA[_\s]*\d+[\.\d]*[-_]\d{4}",

        # HG/T
        r"HG[_\s]?T[_\s]*\d+[\.\d]*[-_]\d{4}",

        # JT/T
        r"JT[_\s]?T[_\s]*\d+[\.\d]*[-_]\d{4}",

        # SY
        r"SY[_\s]*\d+[\.\d]*[-_]\d{4}",

        # 普通T
        r"T[_\s]*\d+[\.\d]*[-_]\d{4}"

    ]


    for pattern in patterns:

        result=re.search(
            pattern,
            name,
            re.I
        )


        if result:

            code=result.group()


            code=(
                code
                .replace("_","/")
                .replace(" ","")
                .replace("//","/")
                .rstrip(".")
            )


            return code.upper()


    return ""



def extract_year(filename):

    years = re.findall(
        r"(19\d{2}|20\d{2})",
        filename
    )

    if years:
        return years[-1]

    return ""



records=[]



for root,dirs,files in os.walk(PDF_ROOT):

    for file in files:


        if not file.lower().endswith(".pdf"):
            continue



        path=os.path.join(
            root,
            file
        )


        relative=os.path.relpath(
            path,
            PDF_ROOT
        )


        # --------------------
        # 判断类型
        # --------------------

        if relative.startswith("法规"):

            document_type="法规"

            document_status="ACTIVE"

            standard_status=""


        elif "已废止地方标准" in relative:

            document_type="标准"

            document_status="ABOLISHED"

            standard_status="废止"


        else:

            document_type="标准"

            document_status="ACTIVE"

            standard_status="现行"



        records.append({

            "filename":
                file,


            "path":
                path,


            "document_type":
                document_type,


            "document_status":
                document_status,


            "standard_status":
                standard_status,


            "standard_code":
                extract_standard_code(file),


            "year":
                extract_year(file),


            "size_mb":
                round(
                    os.path.getsize(path)
                    /
                    1024
                    /
                    1024,
                    2
                ),


            "parse_status":
                "WAIT"

        })




df=pd.DataFrame(records)



df.insert(
    0,
    "pdf_id",
    [
        f"PDF_{i:05d}"
        for i in range(len(df))
    ]
)



df.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)



print("="*60)

print("PDF Inventory生成完成")

print("="*60)


print("\nPDF数量:")
print(len(df))


print("\n文档类型:")
print(
    df["document_type"]
    .value_counts()
)


print("\n文档状态:")
print(
    df["document_status"]
    .value_counts()
)


print("\n标准编号示例:")
print(
    df[
        df["document_type"]=="标准"
    ]
    [
        [
            "filename",
            "standard_code"
        ]
    ]
    .head(10)
)


print("\n保存位置:")
print(OUTPUT)