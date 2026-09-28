from core.wiki_quality import WikiQualityEvaluator



wiki="""
# 液氯

## 概述

液氯属于危险化学品。[Wiki证据1]


## 储存安全要求

液氯应该专库存放。[Wiki证据2]


## 应急处置

发生泄漏需要进行应急处理。[Wiki证据3]

"""


evaluator=WikiQualityEvaluator()


result=evaluator.evaluate(
    wiki
)


print(result)