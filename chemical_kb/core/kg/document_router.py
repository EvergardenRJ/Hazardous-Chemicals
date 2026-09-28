# -*- coding: utf-8 -*-
"""Document Router：按 chunk 元数据把文档路由到 accident / standard / regulation / unknown。

依据真实 chunk 字段：事故 chunk 有 source="事故"、document_type="事故"、doc_type="accident"；
标准/法规 chunk 有 document_type="标准"/"法规"、code。仅做确定性路由，不调 LLM。
"""


class DocumentRouter:
    TYPE_MAP = {
        # 中文
        "事故": "accident", "事故报告": "accident",
        "标准": "standard", "国标": "standard", "行业标准": "standard",
        "地方标准": "standard", "企业标准": "standard",
        "法规": "regulation", "法律": "regulation", "规章": "regulation",
        "规范性文件": "regulation", "部门规章": "regulation",
        # 英文
        "accident": "accident",
        "standard": "standard",
        "regulation": "regulation",
    }

    # 标准代号前缀（用于 code 兜底）
    STD_PREFIXES = ("GB", "AQ", "DB", "HG", "TSG", "SY", "JT", "NB", "SN",
                    "YS", "JB", "JGJ", "CJJ", "Q/", "GA", "WS")

    def route(self, metadata):
        """返回 accident / standard / regulation / unknown 之一。"""
        if not isinstance(metadata, dict):
            return "unknown"

        # 1) 显式字段：source / document_type / doc_type / source_type
        for key in ("source", "document_type", "doc_type", "source_type"):
            value = metadata.get(key)
            if value is None or value == "":
                continue
            hit = self.TYPE_MAP.get(str(value).strip())
            if hit is None:
                hit = self.TYPE_MAP.get(str(value).strip().lower())
            if hit:
                return hit

        # 2) code 兜底：标准代号开头视为 standard
        code = str(metadata.get("code", "") or "").strip().upper()
        if code and code.startswith(self.STD_PREFIXES):
            return "standard"

        # 3) doc_id 前缀兜底
        doc_id = str(metadata.get("doc_id", "") or "")
        if doc_id.upper().startswith("STD"):
            return "standard"
        if doc_id.upper().startswith("REG"):
            return "regulation"
        if doc_id.upper().startswith("ACC"):
            return "accident"

        return "unknown"
