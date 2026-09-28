import json
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(
    "/root/autodl-tmp/chemical_kb"
)


DOCUMENT_FILE = (
    BASE_DIR /
    "data/knowledge/documents.json"
)



class DocumentManager:


    def __init__(self):

        DOCUMENT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )


        if not DOCUMENT_FILE.exists():

            self.save_documents([])



    # ==========================
    # 读取文档库
    # ==========================

    def load_documents(self):

        with open(
            DOCUMENT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)



    # ==========================
    # 保存文档库
    # ==========================

    def save_documents(
        self,
        documents
    ):


        with open(
            DOCUMENT_FILE,
            "w",
            encoding="utf-8"
        ) as f:


            json.dump(
                documents,
                f,
                ensure_ascii=False,
                indent=2
            )



    # ==========================
    # 添加文档
    # ==========================

    def add_document(
        self,
        doc_info
    ):


        documents = self.load_documents()



        # 防止重复

        for doc in documents:

            if (
                doc["doc_id"]
                ==
                doc_info["doc_id"]
            ):

                print(
                    "文档已经存在"
                )

                return False



        doc_info.update(
            {
                "upload_time":
                    datetime.now()
                    .strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),

                "status":
                    "active"
            }
        )



        documents.append(
            doc_info
        )


        self.save_documents(
            documents
        )


        print(
            "文档登记成功:",
            doc_info["title"]
        )


        return True



    # ==========================
    # 获取全部文档
    # ==========================

    def get_all_documents(
        self
    ):


        return self.load_documents()



    # ==========================
    # 根据doc_id查找
    # ==========================

    def get_document(
        self,
        doc_id
    ):


        documents = self.load_documents()


        for doc in documents:


            if doc["doc_id"] == doc_id:

                return doc



        return None



    # ==========================
    # 删除文档记录
    # ==========================

    def delete_document(
        self,
        doc_id
    ):


        documents = self.load_documents()



        new_documents = [

            doc

            for doc in documents

            if doc["doc_id"] != doc_id

        ]



        if len(new_documents) == len(documents):

            return False



        self.save_documents(
            new_documents
        )


        return True



    # ==========================
    # 更新文档状态
    # ==========================

    def update_status(
        self,
        doc_id,
        status
    ):


        documents=self.load_documents()



        for doc in documents:


            if doc["doc_id"] == doc_id:


                doc["status"]=status


                self.save_documents(
                    documents
                )


                return True



        return False



    # ==========================
    # 统计信息
    # ==========================

    def get_statistics(
        self
    ):


        documents=self.load_documents()



        total=len(documents)



        active=sum(

            1

            for doc in documents

            if doc.get(
                "status"
            )
            ==
            "active"

        )


        chunks=sum(

            doc.get(
                "chunks",
                0
            )

            for doc in documents

        )



        return {

            "total_documents":
                total,

            "active_documents":
                active,

            "total_chunks":
                chunks

        }



if __name__ == "__main__":


    manager = DocumentManager()



    print(
        manager.get_statistics()
    )