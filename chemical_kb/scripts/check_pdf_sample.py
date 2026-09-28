import pandas as pd


pdf = pd.read_csv(
    "/root/autodl-tmp/chemical_kb/data/pdf_inventory.csv"
)


print(
    pdf[
        [
            "filename",
            "standard_code"
        ]
    ]
    .head(50)
    .to_string()
)