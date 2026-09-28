import re


class EvidenceQualityRanker:


    def __init__(self):

        # 文档权威等级
        self.source_weight = {

            "国家标准": 1.0,

            "行业标准": 0.95,

            "地方标准": 0.9,

            "法规": 1.0,

            "通知": 0.85,

            "指南": 0.8

        }



    def score(
            self,
            evidence,
            intent=None
    ):


        metadata = evidence.get(
            "metadata",
            {}
        )


        text = metadata.get(
            "text",
            ""
        )


        score = 0



        # ======================
        # 1. Reranker 分数
        # ======================

        rerank_score = evidence.get(
            "rerank_score",
            0
        )


        score += min(
            rerank_score / 3,
            1
        ) * 40



        # ======================
        # 2. 文档权威性
        # ======================

        doc_type = metadata.get(
            "document_type",
            ""
        )


        for key,value in self.source_weight.items():

            if key in doc_type:

                score += value * 20

                break



        # ======================
        # 3. 内容完整度
        # ======================

        length=len(text)


        if length>1000:

            score +=20

        elif length>500:

            score +=15

        elif length>200:

            score+=10



        # ======================
        # 4. Intent匹配
        # ======================

        if intent:

            score += self.intent_score(
                text,
                intent
            )



        return round(
            score,
            2
        )




    def intent_score(
            self,
            text,
            intent
    ):


        rules={


            "emergency":[
                "泄漏",
                "应急",
                "处置",
                "堵漏",
                "疏散",
                "救援"
            ],


            "storage":[
                "储存",
                "存放",
                "库房",
                "储罐"
            ],


            "protection":[
                "防护",
                "呼吸器",
                "防护服",
                "手套"
            ],


            "facility":[
                "报警",
                "联锁",
                "阀",
                "安全仪表",
                "检测"
            ]

        }


        keywords = rules.get(
            intent,
            []
        )


        count=0


        for k in keywords:

            if k in text:

                count+=1



        if count>=3:

            return 20

        elif count>=1:

            return 10

        else:

            return 0