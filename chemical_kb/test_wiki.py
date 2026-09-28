from core.wiki_store import WikiStore



store=WikiStore()


wiki="""
# 液氯

## 概述

液氯属于危险化学品。
"""


evidence=[

{
"title":"化工企业氯气安全技术规范",
"code":"GB11984-2024",
"page":10
}

]


print(
"保存Wiki"
)


path=store.save(
    "液氯",
    wiki,
    evidence
)


print(
path
)



print(
"读取"
)


print(
store.load(
    "液氯"
)
)



print(
"列表"
)


print(
store.list_all()
)