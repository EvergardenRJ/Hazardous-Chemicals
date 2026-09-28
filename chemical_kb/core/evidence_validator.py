import re


class EvidenceValidator:

    def __init__(
        self,
        min_rerank_score=None,
        default_intent_threshold=2
    ):

        # ==================================================
        # 1. 危险化学品实体别名
        # ==================================================

        self.entity_aliases = {

            "液氯": [
                "液氯",
                "氯气"
            ],

            "液氨": [
                "液氨",
                "氨气"
            ],

            "保险粉": [
                "保险粉",
                "连二亚硫酸钠"
            ],

            "液化石油气": [
                "液化石油气",
                "lpg"
            ],

            "盐酸": [
                "盐酸",
                "氯化氢"
            ],

            "甲醇": [
                "甲醇"
            ],

            "乙醇": [
                "乙醇"
            ],

            "苯": [
                "苯"
            ],

            "甲苯": [
                "甲苯"
            ],

            "硫酸": [
                "硫酸"
            ]
        }


        # ==================================================
        # 2. Intent规则
        #
        # question_keywords:
        #   用于判断“用户问题想问什么”
        #
        # strong_keywords:
        #   Evidence中命中一个 +2分
        #
        # weak_keywords:
        #   Evidence中命中一个 +1分
        #
        # required_keywords:
        #   如果不为空，则至少命中其中一个
        #
        # threshold:
        #   Intent最低通过分数
        # ==================================================

        self.intent_rules = {

            # ==================================================
            # 定义 / 概述
            # ==================================================

            "definition": {

                "question_keywords": [
                    "是什么",
                    "定义",
                    "概念",
                    "基本情况",
                    "基本定义",
                    "适用范围",
                    "主要用途",
                    "用途",
                    "性质"
                ],

                "strong_keywords": [
                    "定义",
                    "术语",
                    "适用范围",
                    "范围",
                    "性质",
                    "用途"
                ],

                "weak_keywords": [
                    "用于",
                    "分子量",
                    "熔点",
                    "沸点",
                    "密度",
                    "外观",
                    "气味",
                    "相对密度",
                    "蒸气密度"
                ],

                "required_keywords": [],

                "threshold": 2
            },


            # ==================================================
            # 危险性 / 风险
            # ==================================================

            "hazard": {

                "question_keywords": [
                    "危险性",
                    "危险",
                    "风险",
                    "危害",
                    "安全风险",
                    "有什么危害"
                ],

                "strong_keywords": [
                    "危险性",
                    "危险",
                    "毒性",
                    "中毒",
                    "爆炸",
                    "燃烧",
                    "腐蚀"
                ],

                "weak_keywords": [
                    "剧毒",
                    "刺激性",
                    "氧化",
                    "火灾",
                    "助燃",
                    "有毒",
                    "反应",
                    "危害",
                    "风险"
                ],

                "required_keywords": [
                    "危险",
                    "毒性",
                    "中毒",
                    "爆炸",
                    "燃烧",
                    "腐蚀",
                    "剧毒",
                    "刺激性",
                    "氧化",
                    "有毒"
                ],

                "threshold": 2
            },


            # ==================================================
            # 储存
            # ==================================================

            "storage": {

                "question_keywords": [
                    "储存",
                    "贮存",
                    "仓储",
                    "存放",
                    "库房",
                    "储存要求",
                    "贮存要求"
                ],

                "strong_keywords": [
                    "储存",
                    "贮存",
                    "存放",
                    "库房",
                    "储存区",
                    "贮存区"
                ],

                "weak_keywords": [
                    "储罐",
                    "实瓶",
                    "空瓶",
                    "围堰",
                    "围堤",
                    "仓库",
                    "仓储",
                    "瓶库",
                    "储存量",
                    "充装量"
                ],

                "required_keywords": [
                    "储存",
                    "贮存",
                    "存放",
                    "库房",
                    "储存区",
                    "贮存区",
                    "仓库"
                ],

                "threshold": 2
            },


            # ==================================================
            # 使用 / 生产 / 操作 / 输送
            # ==================================================

            "operation": {

                # 注意：
                # 不再使用单独“作业”作为Question关键词，
                # 防止“作业人员需要哪些防护措施”
                # 被错误识别为operation。

                "question_keywords": [
                    "使用要求",
                    "生产要求",
                    "生产过程",
                    "使用过程",
                    "操作",
                    "操作要求",
                    "接卸",
                    "输送",
                    "搬运",
                    "充装",
                    "气化",
                    "作业安全",
                    "作业要求"
                ],

                "strong_keywords": [
                    "操作",
                    "接卸",
                    "输送",
                    "搬运",
                    "充装",
                    "气化",
                    "装卸"
                ],

                "weak_keywords": [
                    "生产",
                    "使用",
                    "管道",
                    "阀门",
                    "设备",
                    "作业",
                    "工艺"
                ],

                "required_keywords": [
                    "操作",
                    "接卸",
                    "输送",
                    "搬运",
                    "充装",
                    "气化",
                    "装卸",
                    "生产",
                    "使用"
                ],

                "threshold": 2
            },


            # ==================================================
            # 安全设施 / 自动化控制
            # ==================================================

            "facility": {

                "question_keywords": [
                    "安全设施",
                    "设施",
                    "报警",
                    "联锁",
                    "自动控制",
                    "自动化控制",
                    "安全仪表",
                    "sis",
                    "紧急切断",
                    "检测装置",
                    "风险控制"
                ],

                "strong_keywords": [
                    "自动控制",
                    "自动化控制",
                    "安全仪表",
                    "紧急切断",
                    "紧急停车",
                    "检测报警",
                    "联锁",
                    "sis"
                ],

                "weak_keywords": [
                    "报警",
                    "集中控制",
                    "泄漏检测",
                    "在线监测",
                    "安全设施",
                    "防雷",
                    "防静电",
                    "安全阀",
                    "压力表",
                    "液位计",
                    "温度计"
                ],

                "required_keywords": [
                    "自动控制",
                    "自动化控制",
                    "安全仪表",
                    "紧急切断",
                    "紧急停车",
                    "检测报警",
                    "联锁",
                    "sis",
                    "报警"
                ],

                "threshold": 2
            },


            # ==================================================
            # 个体防护
            # ==================================================

            "protection": {

                "question_keywords": [
                    "个体防护",
                    "个人防护",
                    "防护用品",
                    "防护措施",
                    "呼吸器",
                    "防护服",
                    "防毒面具"
                ],

                "strong_keywords": [
                    "个体防护",
                    "个人防护",
                    "防护用品",
                    "防护服",
                    "空气呼吸器",
                    "正压空气呼吸器",
                    "防毒面具"
                ],

                "weak_keywords": [
                    "滤毒口罩",
                    "防化手套",
                    "防化靴",
                    "护目镜",
                    "安全防护眼镜",
                    "面罩",
                    "防静电工作服",
                    "呼吸防护"
                ],

                "required_keywords": [
                    "个体防护",
                    "个人防护",
                    "防护用品",
                    "防护服",
                    "空气呼吸器",
                    "正压空气呼吸器",
                    "防毒面具",
                    "滤毒口罩",
                    "防化手套",
                    "防化靴",
                    "护目镜",
                    "安全防护眼镜",
                    "面罩"
                ],

                "threshold": 2
            },


            # ==================================================
            # 泄漏 / 事故现场应急处置
            # ==================================================

            "emergency": {

                "question_keywords": [
                    "泄漏",
                    "事故处置",
                    "应急处置",
                    "应急措施",
                    "怎么处置",
                    "如何处置",
                    "疏散",
                    "堵漏",
                    "断源"
                ],

                "strong_keywords": [
                    "泄漏",
                    "断源",
                    "堵漏",
                    "倒罐",
                    "疏散",
                    "隔离"
                ],

                "weak_keywords": [
                    "事故现场",
                    "泄漏源",
                    "事故罐",
                    "污染区",
                    "上风侧",
                    "无害化处理",
                    "泄漏物",
                    "吸收装置"
                ],

                # 非常重要：
                # 不能只因为出现“应急”就认为是事故处置。
                #
                # 应急预案、应急演练属于training，
                # 不应该混入现场泄漏处置。
                "required_keywords": [
                    "泄漏",
                    "断源",
                    "堵漏",
                    "倒罐",
                    "疏散",
                    "隔离",
                    "事故现场",
                    "泄漏源",
                    "事故罐",
                    "泄漏物"
                ],

                "threshold": 2
            },


            # ==================================================
            # 中毒急救 / 医疗救治
            # ==================================================

            "first_aid": {

                "question_keywords": [
                    "急救",
                    "中毒怎么办",
                    "中毒处置",
                    "吸入后",
                    "人员中毒",
                    "医疗救治"
                ],

                "strong_keywords": [
                    "急救",
                    "就医",
                    "吸氧",
                    "人工呼吸",
                    "院前急救"
                ],

                "weak_keywords": [
                    "中毒",
                    "呼吸道",
                    "空气新鲜处",
                    "冲洗",
                    "生理盐水",
                    "医疗救治"
                ],

                "required_keywords": [
                    "急救",
                    "就医",
                    "吸氧",
                    "人工呼吸",
                    "空气新鲜处",
                    "冲洗"
                ],

                "threshold": 2
            },


            # ==================================================
            # 应急准备 / 预案 / 物资 / 培训 / 演练
            # ==================================================

            "training": {

                "question_keywords": [
                    "应急准备",
                    "应急预案",
                    "应急物资",
                    "应急演练",
                    "培训",
                    "气防站",
                    "救援协议"
                ],

                "strong_keywords": [
                    "应急预案",
                    "应急演练",
                    "应急物资",
                    "气防站",
                    "救援协议"
                ],

                "weak_keywords": [
                    "培训",
                    "联络机制",
                    "桌面演练",
                    "现场演练",
                    "应急器材",
                    "应急抢修器材",
                    "备用气瓶"
                ],

                "required_keywords": [
                    "应急预案",
                    "应急演练",
                    "应急物资",
                    "气防站",
                    "救援协议",
                    "桌面演练",
                    "现场演练"
                ],

                "threshold": 2
            }
        }


        # ==================================================
        # 默认Intent通过阈值
        # ==================================================

        self.default_intent_threshold = (
            default_intent_threshold
        )


        # ==================================================
        # Reranker最低分
        #
        # None表示暂不启用硬阈值
        # ==================================================

        self.min_rerank_score = (
            min_rerank_score
        )


    # ==================================================
    # 文本标准化
    # ==================================================

    def _normalize_text(
        self,
        text
    ):

        if text is None:

            return ""

        text = str(
            text
        ).lower()

        # 删除换行、空格等空白字符
        text = re.sub(
            r"\s+",
            "",
            text
        )

        return text


    # ==================================================
    # 提取目标实体
    # ==================================================

    def extract_target_entities(
        self,
        question
    ):

        question_normalized = (
            self._normalize_text(
                question
            )
        )

        entities = []


        for canonical_name, aliases in (
            self.entity_aliases.items()
        ):

            for alias in aliases:

                alias_normalized = (
                    self._normalize_text(
                        alias
                    )
                )

                if (
                    alias_normalized
                    in question_normalized
                ):

                    entities.append(
                        {
                            "entity":
                                canonical_name,

                            "aliases":
                                aliases
                        }
                    )

                    break


        return entities


    # ==================================================
    # 提取问题Intent
    # ==================================================

    def extract_intents(
        self,
        question
    ):

        question_normalized = (
            self._normalize_text(
                question
            )
        )


        intents = []


        # ==================================================
        # 基础关键词识别
        # ==================================================

        for intent_name, rule in (
            self.intent_rules.items()
        ):

            question_keywords = (
                rule.get(
                    "question_keywords",
                    []
                )
            )


            for keyword in question_keywords:

                normalized_keyword = (
                    self._normalize_text(
                        keyword
                    )
                )


                if (
                    normalized_keyword
                    in question_normalized
                ):

                    intents.append(
                        intent_name
                    )

                    break


        # ==================================================
        # 去重，保持顺序
        # ==================================================

        unique_intents = []


        for intent in intents:

            if intent not in unique_intents:

                unique_intents.append(
                    intent
                )


        # ==================================================
        # Intent消歧
        #
        # 解决：
        #
        # “液氯相关作业人员需要采取哪些个体防护措施？”
        #
        # 不应该因为出现“作业人员”
        # 就被误认为operation。
        # ==================================================

        protection_phrases = [
            "个体防护",
            "个人防护",
            "防护用品",
            "防护服",
            "防毒面具",
            "呼吸器"
        ]


        has_protection_phrase = any(

            self._normalize_text(
                phrase
            )
            in question_normalized

            for phrase in protection_phrases
        )


        if (
            has_protection_phrase
            and
            "protection" in unique_intents
        ):

            # ==================================================
            # 如果问题真的同时在问操作，
            # 则保留operation。
            #
            # 例如：
            # “液氯充装操作时需要采取哪些个体防护措施？”
            #
            # 应识别：
            # operation + protection
            # ==================================================

            explicit_operation_phrases = [
                "操作要求",
                "生产过程",
                "使用过程",
                "接卸",
                "输送",
                "搬运",
                "充装",
                "气化"
            ]


            has_explicit_operation = any(

                self._normalize_text(
                    phrase
                )
                in question_normalized

                for phrase
                in explicit_operation_phrases
            )


            if (
                not has_explicit_operation
                and
                "operation" in unique_intents
            ):

                unique_intents.remove(
                    "operation"
                )


        return unique_intents


    # ==================================================
    # Entity Validation使用的内容
    #
    # Entity可以利用：
    #
    # 标题 + 编号 + Chunk正文
    #
    # 例如某个Chunk正文没有再次出现“液氯”，
    # 但标题是《液氯使用安全技术规范》，
    # 仍然可以确认该Chunk属于液氯语境。
    # ==================================================

    def _get_entity_content(
        self,
        item
    ):

        metadata = item.get(
            "metadata",
            {}
        )


        title = metadata.get(
            "title",
            ""
        )


        code = metadata.get(
            "code",
            ""
        )


        text = metadata.get(
            "text",
            ""
        )


        return self._normalize_text(

            title
            +
            "\n"
            +
            code
            +
            "\n"
            +
            text

        )


    # ==================================================
    # Intent Validation使用的内容
    #
    # 非常重要：
    #
    # Intent只看Chunk正文。
    #
    # 不能使用文档标题，
    # 否则：
    #
    # 《液氯使用安全技术规范》
    #
    # 标题里的“使用”
    # 会让所有Chunk错误获得operation得分。
    # ==================================================

    def _get_intent_content(
        self,
        item
    ):

        metadata = item.get(
            "metadata",
            {}
        )


        text = metadata.get(
            "text",
            ""
        )


        return self._normalize_text(
            text
        )


    # ==================================================
    # Entity Match
    # ==================================================

    def _entity_match(
        self,
        item,
        target_entities
    ):

        # ==================================================
        # 如果问题没有明确实体
        # 则不做实体过滤
        # ==================================================

        if not target_entities:

            return (
                True,
                ""
            )


        content = (
            self._get_entity_content(
                item
            )
        )


        for entity_info in target_entities:

            aliases = entity_info.get(
                "aliases",
                []
            )


            for alias in aliases:

                alias_normalized = (
                    self._normalize_text(
                        alias
                    )
                )


                if (
                    alias_normalized
                    in content
                ):

                    return (
                        True,
                        ""
                    )


        entity_names = [

            entity_info.get(
                "entity",
                ""
            )

            for entity_info
            in target_entities

        ]


        return (

            False,

            (
                "实体不一致：未发现目标实体或别名："
                +
                ", ".join(
                    entity_names
                )
            )

        )


    # ==================================================
    # 计算一个Intent的Evidence匹配分数
    # ==================================================

    def _calculate_intent_score(
        self,
        content,
        intent_name
    ):

        rule = self.intent_rules.get(
            intent_name,
            {}
        )


        strong_keywords = rule.get(
            "strong_keywords",
            []
        )


        weak_keywords = rule.get(
            "weak_keywords",
            []
        )


        required_keywords = rule.get(
            "required_keywords",
            []
        )


        strong_hits = []

        weak_hits = []

        required_hits = []


        # ==================================================
        # Strong关键词
        # ==================================================

        for keyword in strong_keywords:

            keyword_normalized = (
                self._normalize_text(
                    keyword
                )
            )


            if (
                keyword_normalized
                in content
            ):

                strong_hits.append(
                    keyword
                )


        # ==================================================
        # Weak关键词
        # ==================================================

        for keyword in weak_keywords:

            keyword_normalized = (
                self._normalize_text(
                    keyword
                )
            )


            if (
                keyword_normalized
                in content
            ):

                weak_hits.append(
                    keyword
                )


        # ==================================================
        # Required关键词
        # ==================================================

        for keyword in required_keywords:

            keyword_normalized = (
                self._normalize_text(
                    keyword
                )
            )


            if (
                keyword_normalized
                in content
            ):

                required_hits.append(
                    keyword
                )


        # ==================================================
        # Intent Score
        #
        # strong = 2
        # weak   = 1
        # ==================================================

        score = (
            len(
                strong_hits
            )
            * 2
            +
            len(
                weak_hits
            )
        )


        return {

            "intent":
                intent_name,

            "score":
                score,

            "strong_hits":
                strong_hits,

            "weak_hits":
                weak_hits,

            "required_hits":
                required_hits
        }


    # ==================================================
    # Intent Match
    # ==================================================

    def _intent_match(
        self,
        item,
        target_intents
    ):

        # ==================================================
        # 如果问题没有识别出明确Intent
        # 则跳过Intent过滤
        # ==================================================

        if not target_intents:

            return {

                "valid":
                    True,

                "reason":
                    "",

                "matched_intent":
                    None,

                "intent_scores":
                    []
            }


        # ==================================================
        # 这里只使用Chunk正文
        # ==================================================

        content = (
            self._get_intent_content(
                item
            )
        )


        intent_scores = []


        # ==================================================
        # 多Intent采用OR策略
        #
        # 例如：
        #
        # “液氯泄漏时人员需要什么防护？”
        #
        # 可以同时识别：
        #
        # emergency
        # protection
        #
        # 只要Evidence对其中一个方面有明确价值，
        # 就允许保留。
        # ==================================================

        for intent_name in target_intents:

            result = (
                self._calculate_intent_score(

                    content=content,

                    intent_name=intent_name
                )
            )


            intent_scores.append(
                result
            )


            rule = self.intent_rules.get(
                intent_name,
                {}
            )


            threshold = rule.get(
                "threshold",
                self.default_intent_threshold
            )


            required_keywords = (
                rule.get(
                    "required_keywords",
                    []
                )
            )


            # ==================================================
            # Required校验
            # ==================================================

            if required_keywords:

                required_passed = (
                    len(
                        result.get(
                            "required_hits",
                            []
                        )
                    )
                    >
                    0
                )

            else:

                required_passed = True


            # ==================================================
            # Score校验
            # ==================================================

            score_passed = (

                result.get(
                    "score",
                    0
                )

                >=

                threshold
            )


            # ==================================================
            # 当前Intent通过
            # ==================================================

            if (
                required_passed
                and
                score_passed
            ):

                return {

                    "valid":
                        True,

                    "reason":
                        "",

                    "matched_intent":
                        intent_name,

                    "intent_scores":
                        intent_scores
                }


        # ==================================================
        # 所有Intent全部失败
        # ==================================================

        score_text_parts = []


        for score_info in intent_scores:

            score_text_parts.append(

                (
                    f"{score_info.get('intent', '')}="
                    f"{score_info.get('score', 0)}"
                )

            )


        return {

            "valid":
                False,

            "reason":
                (
                    "意图不一致：Evidence与问题意图匹配不足；"
                    "IntentScore: "
                    +
                    ", ".join(
                        score_text_parts
                    )
                ),

            "matched_intent":
                None,

            "intent_scores":
                intent_scores
        }


    # ==================================================
    # Quality Check
    # ==================================================

    def _quality_check(
        self,
        item
    ):

        metadata = item.get(
            "metadata",
            {}
        )


        text = metadata.get(
            "text",
            ""
        )


        # ==================================================
        # 无正文
        # ==================================================

        if not text:

            return (
                False,
                "正文为空"
            )


        # ==================================================
        # 文本过短
        # ==================================================

        if len(
            text.strip()
        ) < 30:

            return (
                False,
                "正文过短"
            )


        # ==================================================
        # 历史Chunk如果有quality字段
        # 则检查异常状态
        # ==================================================

        quality = str(
            metadata.get(
                "quality",
                ""
            )
        ).lower()


        if quality in [
            "empty",
            "failed",
            "bad"
        ]:

            return (

                False,

                (
                    "Chunk质量异常："
                    f"{quality}"
                )

            )


        return (
            True,
            ""
        )


    # ==================================================
    # Reranker Score Check
    # ==================================================

    def _score_check(
        self,
        item
    ):

        # ==================================================
        # 默认不设置硬阈值
        # ==================================================

        if (
            self.min_rerank_score
            is None
        ):

            return (
                True,
                ""
            )


        score = item.get(
            "rerank_score"
        )


        # ==================================================
        # 没分数时暂时放行
        # ==================================================

        if score is None:

            return (
                True,
                ""
            )


        if (
            score
            <
            self.min_rerank_score
        ):

            return (

                False,

                (
                    "Reranker分数低于阈值："
                    f"{score:.4f}"
                )

            )


        return (
            True,
            ""
        )


    # ==================================================
    # 单条Evidence验证
    # ==================================================

    def validate_one(
        self,
        question,
        item,
        target_entities=None,
        target_intents=None
    ):

        # ==================================================
        # 避免重复解析Question
        # ==================================================

        if target_entities is None:

            target_entities = (
                self.extract_target_entities(
                    question
                )
            )


        if target_intents is None:

            target_intents = (
                self.extract_intents(
                    question
                )
            )


        # ==================================================
        # 1. Quality
        # ==================================================

        quality_passed, reason = (
            self._quality_check(
                item
            )
        )


        if not quality_passed:

            return {

                "valid":
                    False,

                "reason":
                    reason,

                "matched_intent":
                    None,

                "intent_scores":
                    []
            }


        # ==================================================
        # 2. Reranker Score
        # ==================================================

        score_passed, reason = (
            self._score_check(
                item
            )
        )


        if not score_passed:

            return {

                "valid":
                    False,

                "reason":
                    reason,

                "matched_intent":
                    None,

                "intent_scores":
                    []
            }


        # ==================================================
        # 3. Entity Validation
        # ==================================================

        entity_passed, reason = (
            self._entity_match(

                item=item,

                target_entities=target_entities
            )
        )


        if not entity_passed:

            return {

                "valid":
                    False,

                "reason":
                    reason,

                "matched_intent":
                    None,

                "intent_scores":
                    []
            }


        # ==================================================
        # 4. Intent Validation
        # ==================================================

        intent_result = (
            self._intent_match(

                item=item,

                target_intents=target_intents
            )
        )


        if not intent_result.get(
            "valid",
            False
        ):

            return {

                "valid":
                    False,

                "reason":
                    intent_result.get(
                        "reason",
                        "Intent验证失败"
                    ),

                "matched_intent":
                    None,

                "intent_scores":
                    intent_result.get(
                        "intent_scores",
                        []
                    )
            }


        # ==================================================
        # 全部通过
        # ==================================================

        return {

            "valid":
                True,

            "reason":
                "通过",

            "matched_intent":
                intent_result.get(
                    "matched_intent"
                ),

            "intent_scores":
                intent_result.get(
                    "intent_scores",
                    []
                )
        }


    # ==================================================
    # 批量验证
    # ==================================================

    def validate(
        self,
        question,
        results
    ):

        # ==================================================
        # Question只解析一次
        # ==================================================

        target_entities = (
            self.extract_target_entities(
                question
            )
        )


        target_intents = (
            self.extract_intents(
                question
            )
        )


        accepted = []

        rejected = []


        # ==================================================
        # 验证每条Evidence
        # ==================================================

        for item in results:

            check = self.validate_one(

                question=question,

                item=item,

                target_entities=target_entities,

                target_intents=target_intents
            )


            # ==================================================
            # 通过
            # ==================================================

            if check.get(
                "valid",
                False
            ):

                # 不直接修改原始item
                enriched_item = dict(
                    item
                )


                # 保存Validation信息
                # 方便调试、Wiki Evidence Ranking等后续功能使用
                enriched_item[
                    "validation"
                ] = {

                    "matched_intent":
                        check.get(
                            "matched_intent"
                        ),

                    "intent_scores":
                        check.get(
                            "intent_scores",
                            []
                        )
                }


                accepted.append(
                    enriched_item
                )


            # ==================================================
            # 拒绝
            # ==================================================

            else:

                rejected.append(
                    {

                        "item":
                            item,

                        "reason":
                            check.get(
                                "reason",
                                "未知原因"
                            ),

                        "intent_scores":
                            check.get(
                                "intent_scores",
                                []
                            )
                    }
                )


        # ==================================================
        # 返回结构
        #
        # 保持兼容现有RAGSystem
        # ==================================================

        return {

            "target_entities":
                target_entities,

            "target_intents":
                target_intents,

            "accepted":
                accepted,

            "rejected":
                rejected
        }