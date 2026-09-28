# -*- coding: utf-8 -*-
"""Schema Manager：读取 data/kg/schema_v1.json，提供实体/关系类型查询与校验。

严格依据 schema_v1.json，不重新硬编码 15 实体 / 32 关系。
"""
import json
from pathlib import Path

from core.config import BASE_DIR

DEFAULT_SCHEMA_PATH = BASE_DIR / "data" / "kg" / "schema_v1.json"


class SchemaManager:
    """Schema v1 的只读管理器。

    entity_types / relation_types 均以 id 为键；同时建立 中文名 / 英文名 / id 的反查表，
    保证 get_entity("chemical") / get_entity("化学品") / get_entity("Chemical") 都能命中。
    """

    def __init__(self, schema_path=None):
        self.schema_path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
        with open(self.schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)

        self._entities = {}          # id -> entity dict
        self._relations = {}         # id -> relation dict
        self._entity_by_name = {}    # name(zh/en/id) -> id
        self._relation_by_name = {}  # name(zh/en/id) -> id

        for e in self.schema.get("entity_types", []):
            self._entities[e["id"]] = e
            for key in (e.get("id"), e.get("name"), e.get("name_en")):
                if key:
                    self._entity_by_name[key] = e["id"]
        for r in self.schema.get("relation_types", []):
            self._relations[r["id"]] = r
            for key in (r.get("id"), r.get("name"), r.get("name_en")):
                if key:
                    self._relation_by_name[key] = r["id"]

    # ------------------------------------------------------------------ #
    # 基础属性
    # ------------------------------------------------------------------ #
    @property
    def version(self):
        return self.schema.get("schema_version", "")

    @property
    def entity_count(self):
        return len(self._entities)

    @property
    def relation_count(self):
        return len(self._relations)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get_entity_types(self):
        """返回全部实体类型 id 列表。"""
        return list(self._entities.keys())

    def get_relation_types(self):
        """返回全部关系类型 id 列表。"""
        return list(self._relations.keys())

    def get_entity(self, name):
        """按 id / 中文名 / 英文名 返回实体 dict，找不到返回 None。"""
        eid = self._entity_by_name.get(name)
        return self._entities.get(eid) if eid else None

    def get_relation(self, name):
        """按 id / 中文名 / 英文名 返回关系 dict，找不到返回 None。"""
        rid = self._relation_by_name.get(name)
        return self._relations.get(rid) if rid else None

    def get_entity_attributes(self, entity_type):
        """返回某实体类型的 attributes 列表（每个元素为 {name,type,description}）。"""
        e = self._entities.get(self.normalize_entity_type(entity_type) or entity_type)
        return e.get("attributes", []) if e else None

    # ------------------------------------------------------------------ #
    # 校验
    # ------------------------------------------------------------------ #
    def validate_entity_type(self, name):
        return self._entity_by_name.get(name) is not None

    def validate_relation(self, name):
        return self._relation_by_name.get(name) is not None

    def normalize_entity_type(self, name):
        """把中文名/英文名归一化为 schema 实体 id，未知返回 None。"""
        return self._entity_by_name.get(name)

    def normalize_relation(self, name):
        """把中文名/英文名归一化为 schema 关系 id，未知返回 None。"""
        return self._relation_by_name.get(name)

    def validate_relation_domain(self, subject_type, predicate, object_type):
        """校验 (subject_type) -[predicate]-> (object_type) 是否符合 domain/range。

        会先把 subject_type/object_type 归一化为 schema id，再判断其是否落入
        关系的 domain / range（两者均可能是 str 或 list）。
        """
        rel = self._relations.get(self.normalize_relation(predicate) or predicate)
        if rel is None:
            return False
        s = self.normalize_entity_type(subject_type)
        o = self.normalize_entity_type(object_type)
        if s is None or o is None:
            return False
        domain = self.as_list(rel.get("domain"))
        rng = self.as_list(rel.get("range"))
        return s in domain and o in rng

    @staticmethod
    def as_list(value):
        """把 str / list / None 统一为 list。"""
        if value is None:
            return []
        return value if isinstance(value, list) else [value]
