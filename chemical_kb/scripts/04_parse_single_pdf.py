import fitz
import json
import os



PDF_PATH = (
    "/root/autodl-tmp/chemical_kb/"
    "data/pdf/标准/AQ 3011-2007.pdf"
)



OUTPUT = (
    "/root/autodl-tmp/chemical_kb/"
    "data/parsed_documents/test.json"
)



def extract_pdf(pdf_path):

    doc = fitz.open(pdf_path)


    pages=[]


    for page_num,page in enumerate(doc):

        text = page.get_text()


        pages.append({

            "page":

                page_num + 1,


            "text":

                text.strip()

        })


    return {

        "file":

            os.path.basename(pdf_path),


        "page_count":

            len(doc),


        "pages":

            pages

    }



result = extract_pdf(
    PDF_PATH
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



print("="*50)

print("解析完成")

print("页数:",result["page_count"])

print("输出:",OUTPUT)


print("\n第一页内容:")
print(
    result["pages"][0]["text"][:500]
)
