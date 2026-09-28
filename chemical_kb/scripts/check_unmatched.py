import pandas as pd


mapping = pd.read_csv(
    "/root/autodl-tmp/chemical_kb/data/document_pdf_mapping.csv"
)


unmatched = mapping[
    mapping["confidence"]==0
]


print(
    "未匹配数量:",
    len(unmatched)
)


print(
    unmatched[
        [
            "doc_id",
            "title"
        ]
    ]
    .head(30)
    .to_string()
)