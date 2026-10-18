"""Build a human-labelled evaluation scaffold; never invent gold answers or accuracy."""
import argparse,json
from pathlib import Path
themes=["氨","液氯","天然气","氢气","氧气","氮气","硫化氢","二氧化硫","一氧化碳","二氧化碳","甲醇","乙醇","苯","甲苯","丙酮","硫酸","盐酸","氢氧化钠","保险粉","过氧化氢"]
sections=["理化性质","储存要求","泄漏应急","急救","相关标准法规"]
checks=[]
for i,theme in enumerate(themes):
    for section in sections:
        checks.append({"case_id":f"wiki-{i+1:02d}-{sections.index(section)+1}","theme":theme,"section":section,
            "split":"holdout" if i%4==0 else "development","gold_status":"needs_expert_review",
            "expected_claims":[],"source_chunk_ids":[],"reviewer":None,"reviewed_at":None,
            "check_dimensions":["source_support","numeric_unit_conditions","citation_identity","temporal_applicability","unsupported_additions"]})
questions=[]
types=["有哪些可由本地文档支持的储存要求？","当地资料中有哪些相关标准，其适用范围是什么？","现有资料有哪些冲突或证据缺口？"]
for i in range(50):
    theme=themes[i%20]
    questions.append({"case_id":f"question-{i+1:03d}","theme":theme,"query":theme+types[i%3],
        "split":"holdout" if (i%20)%4==0 else "development","expected_answer":None,
        "source_chunk_ids":[],"gold_status":"needs_expert_review","reviewer":None})
p=argparse.ArgumentParser();p.add_argument("--output",required=True);args=p.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
(out/"chapter_cases.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding="utf-8")
(out/"question_cases.json").write_text(json.dumps(questions,ensure_ascii=False,indent=2),encoding="utf-8")
(out/"README.md").write_text("""# 领域评测集待标注
20 个候选主题、100 个章节检查项、50 个问题；留出集按主题划分。
这只是标注脚手架，不代表这些主题都有足够本地证据。每个金标准须由专家核对原文、数值单位、条件、适用时点并填写审核人和来源。
没有审核完成的金标准时，事实支持率与答案准确率必须报告未测，不能将技术引用对齐率当作事实正确率。
审核案例只能使用 development 集，不把 holdout 内容输入生成提示。
""",encoding="utf-8")
print(json.dumps({"themes":20,"chapters":len(checks),"questions":len(questions),"fact_accuracy":"not_measured; expert gold labels required"}))
