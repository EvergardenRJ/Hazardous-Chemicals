#封装Reranker
import torch

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification
)

from core.config import RERANK_MODEL



class Reranker:


    def __init__(self):

        print(
            "加载Reranker"
        )


        self.tokenizer=AutoTokenizer.from_pretrained(
            RERANK_MODEL
        )


        self.model=AutoModelForSequenceClassification.from_pretrained(
            RERANK_MODEL
        )


        self.model.cuda()

        self.model.eval()



    def rerank(
        self,
        question,
        docs
    ):


        pairs=[]


        for doc in docs:

            text=doc["metadata"].get(
                "text",
                ""
            )

            pairs.append(
                [
                    question,
                    text
                ]
            )



        inputs=self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )


        inputs={
            k:v.cuda()
            for k,v in inputs.items()
        }



        with torch.no_grad():

            scores=self.model(
                **inputs
            ).logits.flatten()



        for doc,score in zip(
            docs,
            scores
        ):

            doc["rerank_score"]=float(score)



        docs.sort(
            key=lambda x:x["rerank_score"],
            reverse=True
        )


        return docs[:5]