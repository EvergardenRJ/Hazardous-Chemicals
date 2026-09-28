# -*- coding: utf-8 -*-
"""Graph Builder：从 approved / modified 的人工审核断言构建知识图谱（节点 + 边）。

数据只来自人工确认的断言（approved 用 original_assertion，modified 用 corrected_assertion），
绝不用 rejected / pending 数据。节点颜色按 v0.5 规格 7 分类，全局一致。
"""

# 节点类型 -> 颜色（v0.5 规格 7，科研/专业低饱和色）
TYPE_COLORS = {
    "standard": "#4c78a8",           # 标准：蓝
    "regulation": "#7b5ea7",         # 法规：紫
    "accident": "#d1453b",           # 事故：红/橙红
    "chemical": "#3b8a5e",           # 化学品：绿
    "equipment": "#2fa8a0",          # 设备：青
    "enterprise": "#e0834a",         # 企业：橙
    "causal_factor": "#d9a52f",      # 事故致因：黄/琥珀
    "requirement": "#5b7bd5",        # 安全要求：靛蓝
    "clause": "#8a6fd5",             # 条款：浅紫
    "measure": "#3ba89a",            # 措施：青绿
    "process": "#5c9c8a",            # 工艺：灰绿
    "site": "#8a9ba8",               # 场所：灰蓝
    "major_hazard_source": "#a88a5c",  # 重大危险源：棕
    "hazard_class": "#c08a4a",       # 危险类别：土橙
    "regulator": "#6f8db8",          # 监管部门：灰蓝
}
DEFAULT_COLOR = "#9aa7b0"           # 其他：中性灰

TYPE_LABELS = {
    "standard": "标准", "regulation": "法规", "accident": "事故", "chemical": "化学品",
    "equipment": "设备", "enterprise": "企业", "causal_factor": "事故致因",
    "requirement": "安全要求", "clause": "条款", "measure": "措施",
    "process": "工艺", "site": "场所", "major_hazard_source": "重大危险源",
    "hazard_class": "危险类别", "regulator": "监管部门",
}


def type_color(entity_type):
    return TYPE_COLORS.get(entity_type, DEFAULT_COLOR)


def type_label(entity_type):
    return TYPE_LABELS.get(entity_type, entity_type or "其他")


class GraphBuilder:
    def build_from_reviews(self, reviews):
        """reviews: ReviewRecord dict 列表。返回 {nodes, edges}。"""
        nodes = {}
        edges = []
        for r in reviews or []:
            if not isinstance(r, dict):
                continue
            decision = r.get("decision", "")
            assertion = None
            if decision == "approved":
                assertion = r.get("original_assertion")
            elif decision == "modified":
                assertion = r.get("corrected_assertion")
            if not isinstance(assertion, dict):
                continue
            self._add_assertion(nodes, edges, assertion)
        return {"nodes": list(nodes.values()), "edges": edges}

    def _add_assertion(self, nodes, edges, a):
        sid = a.get("subject_id", "")
        oid = a.get("object_id", "")
        if not sid or not oid:
            return
        if sid not in nodes:
            nodes[sid] = self._make_node(sid, a.get("subject_label", sid),
                                         a.get("subject_type", ""), a)
        if a.get("object_kind") != "literal" and oid not in nodes:
            nodes[oid] = self._make_node(oid, a.get("object_label", oid),
                                         a.get("object_type", ""), a)
        edges.append({
            "from": sid,
            "to": oid,
            "label": a.get("predicate", ""),
            "predicate": a.get("predicate", ""),
            "confidence": a.get("confidence", ""),
            "source_doc_id": a.get("source_doc_id", ""),
            "source_text_quote": a.get("source_text_quote", ""),
            "page": f"{a.get('page_start', '')}-{a.get('page_end', '')}",
        })

    def _make_node(self, cid, label, etype, a):
        return {
            "id": cid,
            "label": label or cid,
            "type": etype,
            "type_label": type_label(etype),
            "color": type_color(etype),
            "source_doc_id": a.get("source_doc_id", ""),
            "page": f"{a.get('page_start', '')}-{a.get('page_end', '')}",
            "section": a.get("section", ""),
        }
