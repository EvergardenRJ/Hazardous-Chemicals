import os
import json
from datetime import datetime


class WikiStore:


    def __init__(
        self,
        wiki_dir="./data/wiki"
    ):

        self.wiki_dir = wiki_dir


        os.makedirs(
            self.wiki_dir,
            exist_ok=True
        )


    # =================================
    # 创建安全文件名
    # =================================

    def _safe_name(
        self,
        name
    ):

        return (
            name
            .replace(
                "/",
                "_"
            )
            .replace(
                "\\",
                "_"
            )
            .replace(
                " ",
                "_"
            )
        )



    # =================================
    # 获取Wiki目录
    # =================================

    def _wiki_path(
        self,
        entity
    ):

        name=self._safe_name(
            entity
        )


        path=os.path.join(
            self.wiki_dir,
            name
        )


        os.makedirs(
            path,
            exist_ok=True
        )


        return path



    # =================================
    # 保存Wiki
    # =================================

    def save(
        self,
        entity,
        wiki_content,
        evidence=None
    ):


        path=self._wiki_path(
            entity
        )


        # -----------------------------
        # 保存markdown
        # -----------------------------

        md_path=os.path.join(
            path,
            "wiki.md"
        )


        with open(
            md_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                wiki_content
            )



        # -----------------------------
        # 保存Evidence
        # -----------------------------

        evidence_path=os.path.join(
            path,
            "evidence.json"
        )


        with open(
            evidence_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                evidence or [],
                f,
                ensure_ascii=False,
                indent=4
            )



        # -----------------------------
        # 保存metadata
        # -----------------------------


        metadata={

            "entity":
                entity,

            "created_time":
                datetime.now()
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "evidence_count":
                len(evidence or []),

            "version":
                1
        }


        metadata_path=os.path.join(
            path,
            "metadata.json"
        )


        with open(
            metadata_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                metadata,
                f,
                ensure_ascii=False,
                indent=4
            )



        return path



    # =================================
    # 读取Wiki
    # =================================

    def load(
        self,
        entity
    ):


        path=self._wiki_path(
            entity
        )


        md_path=os.path.join(
            path,
            "wiki.md"
        )


        if not os.path.exists(
            md_path
        ):
            return None



        with open(
            md_path,
            "r",
            encoding="utf-8"
        ) as f:

            content=f.read()



        return content



    # =================================
    # 结构化 sections（v0.5）
    # =================================

    def save_sections(
        self,
        entity,
        sections
    ):

        path = self._wiki_path(entity)

        p = os.path.join(path, "sections.json")

        with open(p, "w", encoding="utf-8") as f:

            json.dump(sections or [], f, ensure_ascii=False, indent=2)


    def load_sections(
        self,
        entity
    ):

        path = self._wiki_path(entity)

        p = os.path.join(path, "sections.json")

        if not os.path.exists(p):

            return None

        with open(p, encoding="utf-8") as f:

            return json.load(f)



    # =================================
    # 获取全部Wiki
    # =================================

    def list_all(
        self
    ):


        result=[]


        for name in os.listdir(
            self.wiki_dir
        ):

            path=os.path.join(
                self.wiki_dir,
                name
            )


            if os.path.isdir(
                path
            ):

                result.append(
                    name
                )


        return result



    # =================================
    # 删除Wiki
    # =================================

    def delete(
        self,
        entity
    ):


        import shutil


        path=self._wiki_path(
            entity
        )


        if os.path.exists(
            path
        ):

            shutil.rmtree(
                path
            )

            return True


        return False