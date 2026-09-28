import fitz
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
import os


PDF_PATH = (
    "/root/autodl-tmp/chemical_kb/"
    "data/pdf/标准/AQ 3011-2007.pdf"
)



# 初始化GPU OCR

ocr = PaddleOCR(
    lang="ch"
)



def pdf_page_to_image(page, dpi=300):

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



def ocr_page(img):

    result = ocr.predict(img)

    texts=[]


    for res in result:

        if "rec_texts" in res:

            texts.extend(
                res["rec_texts"]
            )


    return "\n".join(texts)



doc = fitz.open(
    PDF_PATH
)


print(
    "PDF页数:",
    len(doc)
)


for i,page in enumerate(doc):

    print("="*50)

    print(
        "PAGE",
        i+1
    )


    # 先尝试文本

    text = page.get_text()


    if len(text.strip())>50:

        print(
            "文本模式"
        )

        print(
            text[:300]
        )


    else:

        print(
            "OCR模式"
        )


        img = pdf_page_to_image(page)


        text = ocr_page(img)


        print(
            text[:500]
        )