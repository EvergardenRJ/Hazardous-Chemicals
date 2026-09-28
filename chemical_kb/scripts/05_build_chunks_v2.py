import os
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed


BASE="/root/autodl-tmp/chemical_kb"


INPUT_DIR=BASE+"/data/parsed_documents"

OUTPUT_DIR=BASE+"/data/chunks"

OUTPUT_FILE=OUTPUT_DIR+"/chunks_v2.jsonl"



# chunk参数

MIN_SIZE=300

MAX_SIZE=1200


WORKERS=12



os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)



def clean_text(text):

    text=text.replace(
        "\x00",
        ""
    )

    text=re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()



def split_text(text):


    """
    按中文法规结构切割
    """

    # 优先章节

    parts=re.split(
        r'(?=(?:第[一二三四五六七八九十百]+章|'
        r'第\d+条|'
        r'\d+(?:\.\d+)+\s))',
        text
    )


    chunks=[]

    buffer=""


    for p in parts:

        p=p.strip()


        if not p:
            continue


        if len(buffer)+len(p)<MAX_SIZE:

            buffer+=p+"\n"

        else:

            if buffer:

                chunks.append(buffer)

            buffer=p+"\n"



    if buffer:

        chunks.append(buffer)



    # 二次切割超长

    final=[]


    for c in chunks:

        if len(c)<=MAX_SIZE:

            final.append(c)

        else:

            for i in range(
                0,
                len(c),
                MAX_SIZE
            ):

                final.append(
                    c[i:i+MAX_SIZE]
                )


    return final





def process_file(file):


    path=os.path.join(
        INPUT_DIR,
        file
    )


    with open(
        path,
        encoding="utf-8"
    ) as f:

        doc=json.load(f)



    pages=doc.get(
        "pages",
        []
    )


    results=[]


    index=0



    for page in pages:


        text=clean_text(
            page.get(
                "text",
                ""
            )
        )


        if len(text)<50:

            continue



        page_chunks=split_text(
            text
        )


        for chunk in page_chunks:


            if len(chunk)<MIN_SIZE:

                quality="short"

            else:

                quality="normal"



            index+=1



            results.append({

                "chunk_id":
                    f"{doc['doc_id']}_p{page['page']}_c{index}",


                "doc_id":
                    doc.get(
                        "doc_id",
                        ""
                    ),


                "code":
                    doc.get(
                        "code",
                        ""
                    ),


                "title":
                    doc.get(
                        "title",
                        ""
                    ),


                "document_type":
                    doc.get(
                        "document_type",
                        ""
                    ),


                "status":
                    doc.get(
                        "status",
                        ""
                    ),


                "source":
                    doc.get(
                        "source",
                        ""
                    ),


                "page_start":
                    page["page"],


                "page_end":
                    page["page"],


                "text":
                    chunk,


                "char_count":
                    len(chunk),


                "quality":
                    quality

            })



    return results





def main():


    files=[
        f for f in os.listdir(INPUT_DIR)
        if f.endswith(".json")
    ]


    print(
        "文档数量:",
        len(files)
    )



    all_chunks=[]



    with ThreadPoolExecutor(
        max_workers=WORKERS
    ) as executor:


        tasks=[
            executor.submit(
                process_file,
                f
            )
            for f in files
        ]


        for i,t in enumerate(
            as_completed(tasks),
            1
        ):


            all_chunks.extend(
                t.result()
            )


            if i%50==0:

                print(
                    "完成:",
                    i
                )



    print(
        "Chunk数量:",
        len(all_chunks)
    )



    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:


        for c in all_chunks:

            f.write(
                json.dumps(
                    c,
                    ensure_ascii=False
                )
                +"\n"
            )



    print(
        "保存:",
        OUTPUT_FILE
    )




if __name__=="__main__":

    main()