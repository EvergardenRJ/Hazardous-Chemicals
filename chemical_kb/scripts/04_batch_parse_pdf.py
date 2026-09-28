import os
import json
import time
import pandas as pd
import fitz

from concurrent.futures import ThreadPoolExecutor

from PIL import Image
import numpy as np

from paddleocr import PaddleOCR



# ===============================
# 路径配置
# ===============================

BASE = "/root/autodl-tmp/chemical_kb"


MAPPING_FILE = os.path.join(
    BASE,
    "data/document_pdf_mapping.csv"
)


OUTPUT_DIR = os.path.join(
    BASE,
    "data/parsed_documents"
)


REPORT_FILE = os.path.join(
    BASE,
    "data/parse_report.csv"
)



os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)



# ===============================
# OCR初始化
# ===============================

print("初始化OCR模型...")


ocr = PaddleOCR(
    use_angle_cls=True,
    lang="ch",
    use_gpu=True
)


print("OCR加载完成")



# ===============================
# PDF转图片
# ===============================

def page_to_image(page, dpi=250):

    pix = page.get_pixmap(
        dpi=dpi
    )


    img = Image.frombytes(
        "RGB",
        [
            pix.width,
            pix.height
        ],
        pix.samples
    )


    return np.array(img)



# ===============================
# OCR
# ===============================

def ocr_page(img):


    result = ocr.ocr(
        img,
        cls=True
    )


    texts=[]


    if result:

        for block in result:

            if block:

                for item in block:

                    text=item[1][0]

                    score=item[1][1]


                    if score >=0.5:

                        texts.append(text)


    return "\n".join(texts)



# ===============================
# 文本清洗
# ===============================

def clean_text(text):


    filters=[

        "www.bzfxw.com",

        "bzfxw.com"

    ]


    for f in filters:

        text=text.replace(
            f,
            ""
        )


    # 删除多余空行

    lines=[]

    for line in text.splitlines():

        line=line.strip()

        if line:

            lines.append(line)



    return "\n".join(lines)



# ===============================
# 文件名安全处理
# ===============================

def safe_name(name):

    chars=[
        "/",
        "\\",
        ":",
        "*",
        "?",
        "\"",
        "<",
        ">",
        "|"
    ]

    for c in chars:

        name=name.replace(c,"_")


    return name



# ===============================
# 单PDF解析
# ===============================

def parse_pdf(row):


    doc_id=row["doc_id"]

    pdf_path=row["pdf_path"]


    output=os.path.join(

        OUTPUT_DIR,

        safe_name(doc_id)+".json"

    )


    # 断点续跑

    if os.path.exists(output):

        return {

            "doc_id":doc_id,

            "status":"SKIP",

            "pages":0,

            "chars":0

        }



    start=time.time()


    try:


        pdf=fitz.open(pdf_path)



        pages=[]


        total_chars=0

        methods=[]



        for i,page in enumerate(pdf):


            text=page.get_text()



            if len(text.strip()) >=100:


                method="text"


            else:


                method="ocr"


                img=page_to_image(
                    page
                )


                text=ocr_page(
                    img
                )



            text=clean_text(
                text
            )


            total_chars += len(text)


            methods.append(
                method
            )


            pages.append(

                {

                "page":i+1,

                "method":method,

                "text":text

                }

            )



        result={


            "doc_id":doc_id,


            "title":row["title"],


            "document_type":
                row["doc_type"],


            "pdf_path":
                pdf_path,


            "page_count":
                len(pdf),


            "parse_method":
                list(set(methods)),


            "char_count":
                total_chars,


            "pages":
                pages

        }



        with open(
            output,
            "w",
            encoding="utf-8"
        ) as f:


            json.dump(
                result,
                f,
                ensure_ascii=False,
                indent=2
            )



        return {

            "doc_id":doc_id,

            "status":"SUCCESS",

            "pages":len(pdf),

            "chars":total_chars,

            "time":
                round(
                    time.time()-start,
                    2
                )

        }



    except Exception as e:


        return {

            "doc_id":doc_id,

            "status":"ERROR",

            "error":str(e)

        }



# ===============================
# 主程序
# ===============================


if __name__=="__main__":


    df=pd.read_csv(
        MAPPING_FILE
    )


    print(
        "需要解析:",
        len(df)
    )



    results=[]



    # CPU线程
    # 不开太大，避免GPU竞争

    workers=8



    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:


        for i,result in enumerate(

            executor.map(
                parse_pdf,
                [
                    row
                    for _,row
                    in df.iterrows()
                ]

            )

        ):


            results.append(result)


            if (i+1)%20==0:

                print(
                    f"完成 {i+1}/{len(df)}"
                )



    report=pd.DataFrame(
        results
    )


    report.to_csv(
        REPORT_FILE,
        index=False,
        encoding="utf-8-sig"
    )


    print("="*60)

    print("解析完成")


    print(
        report["status"]
        .value_counts()
    )


    print(
        "报告:",
        REPORT_FILE
    )