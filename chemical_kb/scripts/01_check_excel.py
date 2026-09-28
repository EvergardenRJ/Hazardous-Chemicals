import pandas as pd
import os


excel_path = (
    "/root/autodl-tmp/chemical_kb/"
    "data/source/标准汇总.xlsx"
)


print("=" * 60)
print("检查Excel文件")
print("=" * 60)


# 查看文件是否存在

if not os.path.exists(excel_path):
    raise FileNotFoundError(
        f"找不到文件: {excel_path}"
    )


print("Excel存在:")
print(excel_path)


# 查看所有sheet

xls = pd.ExcelFile(excel_path)

print("\n发现Sheet:")
for sheet in xls.sheet_names:
    print("-", sheet)


# 分别读取

for sheet in xls.sheet_names:

    print("\n" + "="*60)
    print("Sheet:", sheet)
    print("="*60)

    df = pd.read_excel(
        excel_path,
        sheet_name=sheet
    )


    print("\n行数:")
    print(len(df))


    print("\n字段:")
    for col in df.columns:
        print("-", col)


    print("\n前3行:")
    print(df.head(3).to_string())
