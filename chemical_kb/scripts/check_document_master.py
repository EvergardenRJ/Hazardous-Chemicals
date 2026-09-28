import fitz
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
import json
import os
import time


# ===============================
# PDF路径
# ===============================

PDF_PATH = (
    "/root/autodl-tmp/chemical_kb/"
    "data/pdf/标准/AQ 3011-2007.pdf"
)


OUTPUT = (
    "/root/autodl-tmp/chemical_kb/"
    "data/parsed_documents/"
    "AQ_3011_2007_ocr.json"
)


# ===============================
# 初始化OCR GPU
# ===============================

print("初始化PaddleOCR...")

ocr = PaddleOCR(
    use_angle_cls=True,
    lang="ch",
    use_gpu=True
)


print("OCR加载完成")


# ===============================
# PDF页面转图片
# ===============================

def page_to_image(page, dpi=300):

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
# OCR单页
# ===============================

def ocr_image(img):

    result = ocr.ocr(
        img,
        cls=True
    )


    texts=[]


    if result:

        for line in result:

            if line:

                for item in line:

                    text = item[1][0]

                    score = item[1][1]


                    if score > 0.5:

                        texts.append(text)



    return "\n".join(texts)



# ===============================
# 清洗文本
# ===============================

def clean_text(text):

    remove_list=[

        "www.bzfxw.com",

        "bzfxw.com"

    ]


    for x in remove_list:

        text=text.replace(
            x,
            ""
        )


    return text.strip()



# ===============================
# PDF解析
# ===============================

def parse_pdf(pdf_path):


    doc = fitz.open(pdf_path)


    pages=[]


    start=time.time()


    for idx,page in enumerate(doc):


        print(
            f"\n处理第 {idx+1}/{len(doc)} 页"
        )


        # 先尝试文字层

        text = page.get_text()



        if len(text.strip()) >= 50:

            method="text"


            print(
                "文本模式"
            )


        else:


            method="ocr"


            print(
                "OCR模式"
            )


            img = page_to_image(
                page
            )


            text = ocr_image(
                img
            )



        text = clean_text(
            text
        )


        pages.append(

            {

            "page":idx+1,

            "method":method,

            "text":text

            }

        )


        print(
            text[:300]
        )


    result={

        "file":
            os.path.basename(pdf_path),

        "page_count":
            len(doc),

        "parse_time":
            round(
                time.time()-start,
                2
            ),

        "pages":
            pages

    }


    return result



# ===============================
# main
# ===============================

if __name__=="__main__":


    result=parse_pdf(
        PDF_PATH
    )


    os.makedirs(
        os.path.dirname(OUTPUT),
        exist_ok=True
    )


    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:


        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )


    print("\n")
    print("="*60)

    print(
        "解析完成"
    )

    print(
        "页数:",
        result["page_count"]
    )


    print(
        "耗时:",
        result["parse_time"],
        "秒"
    )


    print(
        "输出:",
        OUTPUT
    )