from transformers import AutoTokenizer
from transformers import AutoModelForSequenceClassification
import torch


model_path="/root/autodl-tmp/models/bge-reranker-v2-m3"


print("加载tokenizer")

tokenizer=AutoTokenizer.from_pretrained(
    model_path
)


print("加载模型")

model=AutoModelForSequenceClassification.from_pretrained(
    model_path
)


model.cuda()

model.eval()


print("GPU:")
print(torch.cuda.get_device_name(0))


text1="液氯使用安全要求有哪些？"

text2="""
DB32/T 3617-2019
液氯使用安全技术规范
规定液氯使用单位应建立安全管理制度。
"""


inputs=tokenizer(
    text1,
    text2,
    return_tensors="pt",
    truncation=True
)


inputs={
    k:v.cuda()
    for k,v in inputs.items()
}


with torch.no_grad():

    score=model(**inputs).logits[0].item()


print("score:",score)