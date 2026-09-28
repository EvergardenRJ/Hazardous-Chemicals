import os
import json
import time
import queue
import threading

import pandas as pd
import fitz

from PIL import Image
import numpy as np

from paddleocr import PaddleOCR



# =====================================================
# 路径
# =====================================================

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
    "data/parse_report_v2.csv"
)


os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)



# =====================================================
# OCR GPU初始化
# =====================================================

print("="*60)
print("初始化GPU OCR")
print("="*60)


ocr = PaddleOCR(
    use_angle_cls=True,
    lang="ch",
    use_gpu=True,
    gpu_mem=12000,
    rec_batch_num=16
)


print("OCR READY")



# =====================================================
# 工具函数
# =====================================================


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


    lines=[]


    for line in text.splitlines():

        line=line.strip()

        if line:

            lines.append(line)



    return "\n".join(lines)



def get_doc_type(row):


    if "doc_type" in row:

        return row["doc_type"]


    if "document_type" in row:

        return row["document_type"]


    return "unknown"



# =====================================================
# PDF页面转图片
# =====================================================


def page_to_image(page,dpi=250):


    pix=page.get_pixmap(
        dpi=dpi
    )


    img=Image.frombytes(
        "RGB",
        [
            pix.width,
            pix.height
        ],
        pix.samples
    )


    return np.array(img)



# =====================================================
# GPU OCR
# =====================================================


def run_ocr(img):


    result=ocr.ocr(
        img,
        cls=True
    )


    texts=[]


    if result:

        for block in result:

            if block:

                for item in block:

                    txt=item[1][0]

                    score=item[1][1]


                    if score>=0.5:

                        texts.append(txt)


    return "\n".join(texts)



# =====================================================
# 单PDF解析
# =====================================================


def parse_pdf(row):


    doc_id=row["doc_id"]

    pdf_path=row["pdf_path"]


    output=os.path.join(

        OUTPUT_DIR,

        safe_name(doc_id)+".json"

    )


    if os.path.exists(output):

        return {

            "doc_id":doc_id,

            "status":"SKIP"

        }



    start=time.time()


    try:


        pdf=fitz.open(pdf_path)


        pages=[]

        methods=[]

        total_chars=0



        for index,page in enumerate(pdf):


            text=page.get_text()



            if len(text.strip())>=100:


                method="text"



            else:


                method="ocr"


                img=page_to_image(
                    page
                )


                text=run_ocr(
                    img
                )



            text=clean_text(
                text
            )


            total_chars+=len(text)


            methods.append(method)



            pages.append(

                {

                    "page":
                        index+1,


                    "method":
                        method,


                    "text":
                        text

                }

            )



        result={


            "doc_id":
                doc_id,


            "title":
                row["title"],


            "document_type":
                get_doc_type(row),


            "pdf_path":
                pdf_path,


            "page_count":
                len(pdf),


            "methods":
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


            "doc_id":
                doc_id,


            "status":
                "SUCCESS",


            "pages":
                len(pdf),


            "chars":
                total_chars,


            "time":
                round(
                    time.time()-start,
                    2
                )

        }



    except Exception as e:


        return {


            "doc_id":
                doc_id,


            "status":
                "ERROR",


            "error":
                str(e)

        }



# =====================================================
# 主程序
# =====================================================


def main():


    df=pd.read_csv(
        MAPPING_FILE
    )


    print(
        "PDF数量:",
        len(df)
    )


    results=[]


    start=time.time()



    for i,row in df.iterrows():


        print(
            "\n"
            + "="*50
        )


        print(
            f"{i+1}/{len(df)}",
            row["doc_id"]
        )


        result=parse_pdf(row)


        results.append(result)



        print(result)



        # 每20个保存一次

        if (i+1)%20==0:


            pd.DataFrame(
                results
            ).to_csv(

                REPORT_FILE,

                index=False,

                encoding="utf-8-sig"

            )


            print(
                "中间报告已保存"
            )



    report=pd.DataFrame(
        results
    )


    report.to_csv(

        REPORT_FILE,

        index=False,

        encoding="utf-8-sig"

    )


    print("\n")

    print("="*60)

    print("全部完成")


    print(
        report["status"]
        .value_counts()
    )


    print(
        "耗时:",
        round(
            time.time()-start,
            2
        ),
        "秒"
    )


    print(
        REPORT_FILE
    )



if __name__=="__main__":

    main()