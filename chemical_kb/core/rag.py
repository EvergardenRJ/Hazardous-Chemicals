from core.retriever import Retriever
from core.hybrid_retriever import HybridRetriever
from core.llm import QwenLLM
from core.evidence_validator import EvidenceValidator
from core.embedding import EmbeddingModel
from core.vector_store import VectorStore
from core.reranker import Reranker
from core.retriever import Retriever
from core.evidence_ranker import EvidenceQualityRanker



def generate(self,prompt):

    return self.llm.generate(prompt)

class RAGSystem:

    def __init__(
        self,
        retrieve_top_k=5,
        rerank_top_k=5
    ):

        print("="*60)
        print("初始化 RAG System")
        print("="*60)


        self.retrieve_top_k = retrieve_top_k
        self.rerank_top_k = rerank_top_k



        # ============================
        # Embedding
        # ============================

        print("加载Embedding")

        self.embedding = EmbeddingModel()



        # ============================
        # Vector Store
        # ============================

        print("加载Vector Store")

        self.vector_store = VectorStore()



        # ============================
        # Reranker
        # ============================

        print("加载Reranker")

        self.reranker = Reranker()



        # ============================
        # Retriever
        # ============================

        self.retriever = HybridRetriever(
            embedding=self.embedding,
            vector_store=self.vector_store,
            reranker=self.reranker,
        )
        self.evidence_ranker = EvidenceQualityRanker()


        print("Retriever 初始化完成")

        # ==================================================
        # Evidence Validator
        # ==================================================

        self.validator = EvidenceValidator()

        # ==================================================
        # LLM
        # ==================================================

        self.llm = QwenLLM()

        # ==================================================
        # 最终交给LLM的证据数量
        # ==================================================

        self.retrieve_top_k = retrieve_top_k

        print("RAG System 初始化完成")


    # ==================================================
    # 获取页码显示
    # ==================================================

    def _get_page_text(
        self,
        metadata
    ):

        page_start = metadata.get(
            "page_start",
            metadata.get(
                "page",
                ""
            )
        )

        page_end = metadata.get(
            "page_end",
            page_start
        )

        if (
            page_start != ""
            and page_end != ""
            and page_start != page_end
        ):

            return f"{page_start}-{page_end}"

        return str(
            page_start
        )


    # ==================================================
    # 单条Evidence转Prompt文本
    # ==================================================

    def _build_evidence_block(
        self,
        item,
        index
    ):

        metadata = item.get(
            "metadata",
            {}
        )

        title = metadata.get(
            "title",
            "未知文档"
        )

        code = metadata.get(
            "code",
            ""
        )

        document_type = metadata.get(
            "document_type",
            ""
        )

        status = metadata.get(
            "status",
            ""
        )

        source = metadata.get(
            "source",
            ""
        )

        text = metadata.get(
            "text",
            ""
        )

        page_text = self._get_page_text(
            metadata
        )

        faiss_score = item.get(
            "score",
            0
        )

        rerank_score = item.get(
            "rerank_score",
            0
        )

        block = f"""
[证据{index}]

文档标题：{title}

文档编号：{code}

文档类型：{document_type}

文档状态：{status}

来源：{source}

页码：{page_text}

FAISS相关度：{faiss_score:.4f}

Reranker相关度：{rerank_score:.4f}

原文：
{text}
"""

        return block.strip()


    # ==================================================
    # 构建Context
    # ==================================================

    def _build_context(
        self,
        results
    ):

        blocks = []

        for index, item in enumerate(
            results,
            start=1
        ):

            block = self._build_evidence_block(
                item=item,
                index=index
            )

            blocks.append(
                block
            )

        return "\n\n".join(
            blocks
        )


    # ==================================================
    # 输出Validator信息
    # ==================================================

    def _print_validation_result(
        self,
        validation_result
    ):

        target_entities = (
            validation_result.get(
                "target_entities",
                []
            )
        )

        target_intents = (
            validation_result.get(
                "target_intents",
                []
            )
        )

        accepted = (
            validation_result.get(
                "accepted",
                []
            )
        )

        rejected = (
            validation_result.get(
                "rejected",
                []
            )
        )


        # ==================================================
        # Entity
        # ==================================================

        if target_entities:

            print("\n识别目标实体:")

            for entity in target_entities:

                print(
                    " -",
                    entity.get(
                        "entity",
                        ""
                    ),
                    "别名:",
                    entity.get(
                        "aliases",
                        []
                    )
                )

        else:

            print(
                "\n未识别到明确危险化学品实体，"
                "跳过实体一致性过滤"
            )


        # ==================================================
        # Intent
        # ==================================================

        if target_intents:

            print(
                "\n识别问题Intent:"
            )

            for intent in target_intents:

                print(
                    " -",
                    intent
                )

        else:

            print(
                "\n未识别到明确Intent，"
                "跳过Intent一致性过滤"
            )


        # ==================================================
        # 统计
        # ==================================================

        print(
            f"\n通过验证: {len(accepted)}"
        )

        print(
            f"被过滤: {len(rejected)}"
        )


        # ==================================================
        # 输出被过滤Evidence
        # ==================================================

        for rejected_item in rejected:

            item = rejected_item.get(
                "item",
                {}
            )

            metadata = item.get(
                "metadata",
                {}
            )

            print(
                "\n[过滤证据]"
            )

            print(
                "标题:",
                metadata.get(
                    "title",
                    ""
                )
            )

            print(
                "编号:",
                metadata.get(
                    "code",
                    ""
                )
            )

            print(
                "页码:",
                metadata.get(
                    "page_start",
                    metadata.get(
                        "page",
                        ""
                    )
                )
            )

            print(
                "原因:",
                rejected_item.get(
                    "reason",
                    ""
                )
            )
            intent_scores = rejected_item.get(
                "intent_scores",
                []
            )


            if intent_scores:

                print(
                    "Intent评分:"
                )


                for score_info in intent_scores:

                    print(
                        "  -",
                        score_info.get(
                            "intent",
                            ""
                        ),
                        "score=",
                        score_info.get(
                            "score",
                            0
                        ),
                        "strong=",
                        score_info.get(
                            "strong_hits",
                            []
                        ),
                        "weak=",
                        score_info.get(
                            "weak_hits",
                            []
                        ),
                        "required=",
                        score_info.get(
                            "required_hits",
                            []
                        )
                    )   


    # ==================================================
    # 只检索Evidence，不调用LLM
    #
    # Wiki主要调用这个接口
    # ==================================================

    def retrieve_evidence(
        self,
        question,
        top_k=None,
        verbose=True,
        as_of=None
    ):

        question = str(
            question
        ).strip()

        if not question:

            raise ValueError(
                "问题不能为空"
            )


        # ==================================================
        # Top-K
        # ==================================================

        if top_k is None:

            top_k = (
                self.retrieve_top_k
            )


        # ==================================================
        # Step 1 Retriever
        # ==================================================

        if verbose:

            print(
                "\n" + "=" * 60
            )

            print(
                "Step 1: 检索知识库"
            )

            print(
                "=" * 60
            )


        results = (
            self.retriever.query(
                question,
                as_of=as_of
            )
        )


        # ==================================================
        # 完全无召回
        # ==================================================

        if not results:

            return {

                "question":
                    question,

                "evidence":
                    [],

                "rejected_evidence":
                    [],

                "target_entities":
                    [],

                "target_intents":
                    [],

                "context":
                    "",

                "candidate_count":
                    0,

                "valid_count":
                    0,

                "final_count":
                    0
            }


        candidate_count = len(
            results
        )


        if verbose:

            print(
                f"Retriever返回 {candidate_count} 条候选证据"
            )


        # ==================================================
        # Step 2 Evidence Validator
        # ==================================================

        if verbose:

            print(
                "\n" + "=" * 60
            )

            print(
                "Step 2: Evidence Validation"
            )

            print(
                "=" * 60
            )


        validation_result = (
            self.validator.validate(
                question=question,
                results=results
            )
        )

        print("="*60)
        print("DEBUG VALIDATION RESULT")
        print(type(validation_result))
        print(validation_result)
        print("="*60)

        #validated_results = validation_result["accepted"]
        if isinstance(validation_result, dict):

            if "accepted" in validation_result:

                validated_results = validation_result["accepted"]


            elif "valid" in validation_result:

                validated_results = validation_result["valid"]


            elif "results" in validation_result:

                validated_results = validation_result["results"]


            else:

                raise ValueError(
                    f"Unknown validation result format: {validation_result.keys()}"
                )


        else:

            validated_results = validation_result
        ranked_results = []


        for item in validated_results:


            quality_score = self.evidence_ranker.score(

                item,

                validation_result.get(
                    "intent"
                )

            )


            item["quality_score"] = quality_score


            ranked_results.append(item)



        ranked_results.sort(

            key=lambda x:x["quality_score"],

            reverse=True

        )



        validated_results = ranked_results[:5]

        if verbose:

            self._print_validation_result(
                validation_result
            )


        valid_results = (
            validation_result.get(
                "accepted",
                []
            )
        )

        rejected_results = (
            validation_result.get(
                "rejected",
                []
            )
        )

        target_entities = (
            validation_result.get(
                "target_entities",
                []
            )
        )

        target_intents = (
            validation_result.get(
                "target_intents",
                []
            )
        )


        # ==================================================
        # Validator通过数量
        # ==================================================

        valid_count = len(
            valid_results
        )


        # ==================================================
        # 最终Top-K
        # ==================================================

        final_results = (
            valid_results[
                :top_k
            ]
        )


        final_count = len(
            final_results
        )


        if verbose:

            print(
                f"\n最终保留 {final_count} 条可靠证据"
            )


        # ==================================================
        # Context
        # ==================================================

        context = self._build_context(
            final_results
        )


        return {

            "question":
                question,

            "evidence":
                final_results,

            "rejected_evidence":
                rejected_results,

            "target_entities":
                target_entities,

            "target_intents":
                target_intents,

            "context":
                context,

            "candidate_count":
                candidate_count,

            "valid_count":
                valid_count,

            "final_count":
                final_count
        }


    # ==================================================
    # 构建普通RAG Prompt
    # ==================================================

    def _build_prompt(
        self,
        question,
        context
    ):

        prompt = f"""
请严格根据下面提供的危险化学品安全标准、法规和技术文件原文，
回答用户提出的问题。

必须遵守以下规则：

1. 只能依据“检索证据”回答。

2. 不允许依赖模型自身记忆补充具体：
   - 法律法规名称
   - 标准编号
   - 条款编号
   - 技术参数
   - 数值
   - 距离
   - 时间
   - 浓度
   - 温度
   - 压力
   - 应急措施

3. 如果某个结论没有在证据中出现，
   不要自行补充。

4. 如果证据不足，
   请明确说明：

   “根据当前检索到的资料，无法确定。”

5. 所有关键结论必须引用证据：

   [证据1]

   [证据2]

6. 一个结论由多个证据支持时，
   可以写：

   [证据1][证据2]

7. 可以综合多个证据，
   但不得改变原文含义。

8. 如果证据之间存在不同要求或冲突，
   必须明确指出差异，
   不要擅自选择其中一个作为唯一正确结论。

9. 如果问题涉及某一种危险化学品，
   不要使用其他危险化学品的安全要求。

10. 不要把其他危险化学品的：

    - 急救措施
    - 泄漏措施
    - 灭火方法
    - 疏散距离
    - 防护要求

    应用于当前化学品。

11. 必须优先回答用户当前问题的意图。

    例如：

    - 用户问储存要求，
      不要把大量篇幅用于中毒急救；

    - 用户问个体防护，
      不要主要回答储罐设计；

    - 用户问安全设施，
      应重点回答报警、联锁、自动控制、
      SIS、紧急切断等工程措施。

12. 回答尽量结构化。

13. 最后输出：

    参考依据

14. 参考依据只列出实际使用过的证据文档。

15. 每条参考依据尽量包含：

    - 文档标题
    - 文档编号
    - 页码

16. 不输出内部推理过程。

17. 使用中文。


==================================================
用户问题
==================================================

{question}


==================================================
检索证据
==================================================

{context}


==================================================
请根据以上证据回答
==================================================
"""

        return prompt.strip()


    # ==================================================
    # 普通RAG问答
    #
    # Streamlit继续使用这个接口
    # ==================================================

    def answer(
        self,
        question,
        as_of=None
    ):

        question = str(
            question
        ).strip()

        if not question:

            raise ValueError(
                "问题不能为空"
            )


        # ==================================================
        # Step 1 + Step 2
        # Retriever + Validator
        # ==================================================

        retrieval_result = (
            self.retrieve_evidence(

                question=question,

                top_k=self.retrieve_top_k,

                verbose=True,
                as_of=as_of
            )
        )


        evidence = (
            retrieval_result.get(
                "evidence",
                []
            )
        )

        rejected_evidence = (
            retrieval_result.get(
                "rejected_evidence",
                []
            )
        )

        target_entities = (
            retrieval_result.get(
                "target_entities",
                []
            )
        )

        target_intents = (
            retrieval_result.get(
                "target_intents",
                []
            )
        )

        context = (
            retrieval_result.get(
                "context",
                ""
            )
        )


        # ==================================================
        # 没可靠Evidence
        # ==================================================

        if not evidence:

            # 区分：
            # 完全没召回
            # 和
            # 召回后全部被Validator过滤

            if (
                retrieval_result.get(
                    "candidate_count",
                    0
                )
                ==
                0
            ):

                answer_text = (
                    "知识库中没有检索到相关资料。"
                )

            else:

                answer_text = (
                    "知识库检索到了候选资料，"
                    "但经过实体、意图和质量一致性检查后，"
                    "没有找到足够可靠的证据。"
                )


            return {

                "question":
                    question,

                "answer":
                    answer_text,

                "evidence":
                    [],

                "rejected_evidence":
                    rejected_evidence,

                "target_entities":
                    target_entities,

                "target_intents":
                    target_intents,

                "context":
                    context,

                "candidate_count":
                    retrieval_result.get(
                        "candidate_count",
                        0
                    ),

                "valid_count":
                    retrieval_result.get(
                        "valid_count",
                        0
                    ),

                "final_count":
                    0
            }


        # ==================================================
        # Step 3 Context
        # ==================================================

        print(
            "\n" + "=" * 60
        )

        print(
            "Step 3: 构建检索上下文"
        )

        print(
            "=" * 60
        )

        print(
            f"Context中包含 {len(evidence)} 条Evidence"
        )


        # ==================================================
        # Prompt
        # ==================================================

        prompt = self._build_prompt(
            question=question,
            context=context
        )


        # ==================================================
        # Step 4 Qwen
        # ==================================================

        print(
            "\n" + "=" * 60
        )

        print(
            "Step 4: Qwen生成RAG答案"
        )

        print(
            "=" * 60
        )


        answer = self.llm.generate(

            prompt=prompt,

            system_prompt=(
                "你是一名危险化学品安全领域专业知识助手。"
                "回答必须严格基于当前提供的标准、法规和技术文件证据。"
                "不要依赖自身记忆补充具体安全要求、标准、法规、"
                "条款、数值或应急措施。"
                "必须同时遵守证据实体一致性和问题意图一致性。"
                "所有关键结论必须能够追溯到检索证据。"
                "如果证据不足，应明确说明。"
            ),

            max_new_tokens=1500,

            temperature=0.1
        )


        # ==================================================
        # 保持Streamlit兼容
        #
        # 原字段全部保留
        # 新增target_intents和统计字段
        # ==================================================

        return {

            "question":
                question,

            "answer":
                answer,

            "evidence":
                evidence,

            "rejected_evidence":
                rejected_evidence,

            "target_entities":
                target_entities,

            "target_intents":
                target_intents,

            "context":
                context,

            "candidate_count":
                retrieval_result.get(
                    "candidate_count",
                    0
                ),

            "valid_count":
                retrieval_result.get(
                    "valid_count",
                    0
                ),

            "final_count":
                len(
                    evidence
                )
        }


# ==================================================
# 单文件测试
# ==================================================

if __name__ == "__main__":

    rag = RAGSystem(
        retrieve_top_k=5
    )


    questions = [

        "液氯在储存过程中有哪些安全要求？",

        "液氯相关作业人员需要采取哪些个体防护措施？",

        "液氯发生泄漏后应该采取哪些应急处置措施？",

        "液氯需要配置哪些安全设施和自动控制措施？"

    ]


    for question in questions:

        print("\n")
        print("#" * 80)
        print("问题")
        print("#" * 80)

        print(
            question
        )


        # ==================================================
        #这里只测试Evidence，不调用Qwen
        # ==================================================

        result = (
            rag.retrieve_evidence(

                question=question,

                top_k=5,

                verbose=True
            )
        )


        print("\n识别实体:")

        print(
            result.get(
                "target_entities",
                []
            )
        )


        print("\n识别Intent:")

        print(
            result.get(
                "target_intents",
                []
            )
        )


        print("\n最终Evidence:")


        for i, item in enumerate(
            result.get(
                "evidence",
                []
            ),
            start=1
        ):

            metadata = item.get(
                "metadata",
                {}
            )


            print(
                f"\n------ Evidence {i} ------"
            )

            print(
                "标题:",
                metadata.get(
                    "title",
                    ""
                )
            )

            print(
                "编号:",
                metadata.get(
                    "code",
                    ""
                )
            )

            print(
                "页码:",
                metadata.get(
                    "page_start",
                    ""
                ),
                "-",
                metadata.get(
                    "page_end",
                    ""
                )
            )

            print(
                "Reranker:",
                item.get(
                    "rerank_score",
                    ""
                )
            )

            print(
                "正文:"
            )

            print(
                metadata.get(
                    "text",
                    ""
                )[:300]
            )