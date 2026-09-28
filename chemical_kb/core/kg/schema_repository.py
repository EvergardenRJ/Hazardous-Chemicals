# -*- coding: utf-8 -*-
"""Schema Repository：由 Schema v1 的可用字段构造检索条目（不用 LLM）。

每个 Entity Type 一条、每个 Relation Type 一条。embedding_text 由
name + 中文名称 + definition + subject/object + aliases + keywords + examples 组合。
"""
from core.config import BASE_DIR
from core.kg.schema_manager import SchemaManager

KG_DATA_DIR = BASE_DIR / "data" / "kg"
SCHEMA_INDEX_DIR = KG_DATA_DIR / "schema_index"
OUTPUT_DIR = KG_DATA_DIR / "output"


def _to_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class SchemaRepository:
    """把 SchemaManager 转成可检索的 repository items。"""

    def __init__(self, schema_manager=None):
        self.sm = schema_manager or SchemaManager()
        self.items = self._build_items()

    # ------------------------------------------------------------------ #
    def _build_items(self):
        items = []
        for eid in self.sm.get_entity_types():
            e = self.sm.get_entity(eid)
            name_en = e.get("name_en", eid)
            name_zh = e.get("name", "")
            definition = e.get("description", "")
            examples = " ".join(_to_list(e.get("examples")))
            aliases = _to_list(e.get("aliases"))
            attrs = _to_list(e.get("attributes"))
            keywords = [a.get("name", "") for a in attrs if isinstance(a, dict) and a.get("name")]
            embedding_text = self._build_embedding_text(
                name_en, name_zh, definition, [], [], aliases, keywords, examples
            )
            items.append({
                "schema_id": eid,
                "schema_kind": "entity",
                "name": name_en,
                "name_zh": name_zh,
                "definition": definition,
                "subject_types": [],
                "object_types": [],
                "aliases": aliases,
                "keywords": keywords,
                "examples": examples,
                "embedding_text": embedding_text,
            })

        for rid in self.sm.get_relation_types():
            r = self.sm.get_relation(rid)
            name_en = r.get("name_en", rid)
            name_zh = r.get("name", "")
            definition = r.get("description", "")
            domain = _to_list(r.get("domain"))
            rng = _to_list(r.get("range"))
            props = _to_list(r.get("properties"))
            embedding_text = self._build_embedding_text(
                name_en, name_zh, definition, domain, rng, [], props, ""
            )
            items.append({
                "schema_id": rid,
                "schema_kind": "relation",
                "name": name_en,
                "name_zh": name_zh,
                "definition": definition,
                "subject_types": domain,
                "object_types": rng,
                "aliases": [],
                "keywords": props,
                "examples": "",
                "embedding_text": embedding_text,
            })
        return items

    @staticmethod
    def _build_embedding_text(name_en, name_zh, definition, subject_types,
                              object_types, aliases, keywords, examples):
        parts = [name_en, name_zh, definition]
        if subject_types:
            parts.append("主体类型: " + ", ".join(subject_types))
        if object_types:
            parts.append("客体类型: " + ", ".join(object_types))
        if aliases:
            parts.append("别名: " + ", ".join(aliases))
        if keywords:
            parts.append("关键词: " + ", ".join(keywords))
        if examples:
            parts.append("示例: " + examples)
        return "。".join(p for p in parts if p)

    # ------------------------------------------------------------------ #
    def entity_items(self):
        return [it for it in self.items if it["schema_kind"] == "entity"]

    def relation_items(self):
        return [it for it in self.items if it["schema_kind"] == "relation"]
