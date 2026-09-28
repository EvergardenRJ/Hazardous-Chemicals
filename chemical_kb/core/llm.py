import torch

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM
)


class QwenLLM:

    def __init__(
        self,
        model_path=(
            "/root/autodl-tmp/models/models/"
            "Qwen--Qwen3-4B-Instruct-2507/"
            "snapshots/master"
        )
    ):

        print("=" * 60)
        print("加载 Qwen LLM")
        print("=" * 60)

        self.model_path = model_path

        # ==========================
        # tokenizer
        # ==========================

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            trust_remote_code=True
        )

        # ==========================
        # model
        # ==========================

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True
        )

        self.model.eval()

        print("Qwen LLM 加载完成")


    def generate_batch(self, prompts, system_prompt=None, max_new_tokens=1024,
                       temperature=0.2):
        """Generate several independent responses in one GPU forward batch."""
        if not prompts:
            return []
        if system_prompt is None:
            system_prompt = "你是一名危险化学品安全领域知识助手。请只依据文本作答。"
        texts = [self.tokenizer.apply_chat_template([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ], tokenize=False, add_generation_prompt=True) for prompt in prompts]
        previous_side = self.tokenizer.padding_side
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        try:
            inputs = self.tokenizer(texts, return_tensors="pt", padding=True).to(self.model.device)
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs, max_new_tokens=max_new_tokens,
                    do_sample=True, temperature=temperature, top_p=0.9,
                    repetition_penalty=1.05,
                    pad_token_id=self.tokenizer.pad_token_id,
                )
            new_ids = outputs[:, inputs["input_ids"].shape[1]:]
            return [text.strip() for text in self.tokenizer.batch_decode(new_ids,
                                                                          skip_special_tokens=True)]
        finally:
            self.tokenizer.padding_side = previous_side

    # ==================================================
    # 通用生成
    # ==================================================

    def generate(
        self,
        prompt,
        system_prompt=None,
        max_new_tokens=1024,
        temperature=0.2
    ):

        if system_prompt is None:

            system_prompt = (
                "你是一名危险化学品安全领域知识助手。"
                "请准确、清晰地回答问题。"
                "不得编造不存在的标准、法规、条款或数值。"
            )


        messages = [

            {
                "role": "system",
                "content": system_prompt
            },

            {
                "role": "user",
                "content": prompt
            }

        ]


        # ==========================
        # Chat Template
        # ==========================

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )


        # ==========================
        # tokenize
        # ==========================

        inputs = self.tokenizer(
            text,
            return_tensors="pt"
        ).to(
            self.model.device
        )


        # ==========================
        # generate
        # ==========================

        with torch.no_grad():

            outputs = self.model.generate(

                **inputs,

                max_new_tokens=max_new_tokens,

                do_sample=True,

                temperature=temperature,

                top_p=0.9,

                repetition_penalty=1.05
            )


        # ==========================
        # 只保留新生成部分
        # ==========================

        generated_ids = outputs[0][
            inputs["input_ids"].shape[1]:
        ]


        answer = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True
        )


        return answer.strip()