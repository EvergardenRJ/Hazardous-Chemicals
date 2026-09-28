import fitz
import tempfile
from pathlib import Path

from paddleocr import PaddleOCR


class PDFParser:


    def __init__(self):

        print("初始化OCR")

        self.ocr = PaddleOCR(
            lang="ch",
            use_gpu=True
        )



    def parse(self, pdf_path):

        pdf_path = Path(pdf_path)

        doc = fitz.open(
            pdf_path
        )


        pages=[]


        for i,page in enumerate(doc):

            pix = page.get_pixmap(
                dpi=300
            )


            img_path = tempfile.mktemp(
                suffix=".png"
            )


            pix.save(
                img_path
            )


            result=self.ocr.ocr(
                img_path
            )


            text=""


            if result and result[0]:

                for line in result[0]:

                    text += line[1][0] + "\n"


            pages.append(
                {
                    "page":i+1,
                    "text":text
                }
            )


        return pages