import re


class WikiQualityEvaluator:


    def __init__(self):

        """
        化工安全Wiki质量评价器

        评价维度：

        1. 内容完整性
        2. Evidence引用
        3. 文档长度
        4. 结构完整性

        """


        # 化工安全Wiki核心章节

        self.sections = {


            "definition":[

                "概述",
                "定义",
                "基本信息",
                "简介"

            ],



            "hazard":[

                "危险性",
                "危害",
                "风险",
                "危险特性"

            ],



            "storage":[

                "储存",
                "贮存",
                "储存安全要求"

            ],



            "operation":[

                "使用",
                "操作",
                "作业",
                "生产"

            ],



            "facility":[

                "设施",
                "安全设施",
                "自动化",
                "控制措施",
                "风险控制"

            ],



            "protection":[

                "防护",
                "个体防护",
                "防护措施",
                "防护用品"

            ],



            "emergency":[

                "应急",
                "泄漏",
                "事故处置",
                "应急处理"

            ]

        }



    # =================================================
    # 判断章节覆盖
    # =================================================


    def check_sections(
            self,
            wiki
    ):


        coverage={}


        for category, keywords in self.sections.items():


            found=False


            for word in keywords:

                if word in wiki:

                    found=True

                    break



            coverage[category]=found



        return coverage



    # =================================================
    # Evidence检测
    # =================================================


    def check_evidence(
            self,
            wiki
    ):


        citations=re.findall(

            r"\[Wiki证据\d+\]",

            wiki

        )


        return {


            "citation_count":
                len(citations),


            "has_reference":

                len(citations)>0

        }



    # =================================================
    # 长度评分
    # =================================================


    def length_score(
            self,
            wiki
    ):


        length=len(wiki)


        # 太短

        if length < 500:

            return 30



        # 正常Wiki

        elif length < 3000:

            return 70



        else:

            return 100



    # =================================================
    # 完整性评分
    # =================================================


    def coverage_score(
            self,
            coverage
    ):


        total=len(
            coverage
        )


        count=sum(

            1 for v in coverage.values()
            if v

        )


        return (

            count /
            total
            *
            100

        )



    # =================================================
    # Evidence评分
    # =================================================


    def evidence_score(
            self,
            evidence_info
    ):


        count=evidence_info[
            "citation_count"
        ]


        if count==0:

            return 0


        elif count < 5:

            return 60


        elif count < 15:

            return 80


        else:

            return 100



    # =================================================
    # 等级
    # =================================================


    def get_level(
            self,
            score
    ):


        if score>=90:

            return "Excellent"


        elif score>=75:

            return "Good"


        elif score>=60:

            return "Acceptable"


        else:

            return "Poor"



    # =================================================
    # 主评价函数
    # =================================================


    def evaluate(
            self,
            wiki,
            evidence=None
    ):


        # ----------------------------
        # 章节覆盖
        # ----------------------------

        coverage=self.check_sections(
            wiki
        )


        coverage_score=self.coverage_score(
            coverage
        )



        # ----------------------------
        # Evidence
        # ----------------------------

        evidence_info=self.check_evidence(
            wiki
        )


        evidence_score=self.evidence_score(
            evidence_info
        )



        # ----------------------------
        # 长度
        # ----------------------------


        length_score=self.length_score(
            wiki
        )



        # ----------------------------
        # 总分
        # ----------------------------


        final_score=(

            coverage_score*0.5

            +

            evidence_score*0.3

            +

            length_score*0.2

        )


        final_score=round(
            final_score,
            2
        )



        # ----------------------------
        # 缺失内容
        # ----------------------------


        missing=[]


        for key,value in coverage.items():

            if not value:

                missing.append(
                    key
                )



        result={


            "score":
                final_score,


            "level":
                self.get_level(
                    final_score
                ),



            "coverage":
                coverage,



            "missing_sections":
                missing,



            "citation_count":
                evidence_info[
                    "citation_count"
                ],



            "length":
                len(wiki)

        }



        return result