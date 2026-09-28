from pathlib import Path
import hashlib



class ChunkBuilder:


    def __init__(
        self,
        chunk_size=800,
        overlap=100
    ):

        self.chunk_size = chunk_size
        self.overlap = overlap



    def _generate_chunk_id(
        self,
        doc_id,
        page,
        index
    ):

        raw = (
            f"{doc_id}_{page}_{index}"
        )

        return hashlib.md5(
            raw.encode("utf-8")
        ).hexdigest()



    def build(
        self,
        pages,
        doc_id,
        title,
        document_type="unknown",
        code="",
        source="upload",
        pdf_path=""
    ):


        chunks=[]


        chunk_index=0



        for page in pages:


            text = page.get(
                "text",
                ""
            ).strip()



            if not text:

                continue



            start=0



            while start < len(text):


                end = (
                    start +
                    self.chunk_size
                )


                chunk_text = text[start:end]



                chunk = {

                    # 唯一ID
                    "chunk_id":
                        self._generate_chunk_id(
                            doc_id,
                            page["page"],
                            chunk_index
                        ),


                    # 文档信息
                    "doc_id":
                        doc_id,


                    "title":
                        title,


                    "document_type":
                        document_type,


                    "code":
                        code,


                    "source":
                        source,


                    "pdf_path":
                        str(pdf_path),



                    # 位置信息
                    "page":
                        page["page"],



                    # 内容
                    "text":
                        chunk_text,


                    "char_count":
                        len(chunk_text)

                }


                chunks.append(
                    chunk
                )


                chunk_index += 1



                start = (
                    end -
                    self.overlap
                )


        return chunks