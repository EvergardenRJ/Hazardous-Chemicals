# -*- coding: utf-8 -*-
"""Assertion Validator：对 CandidateAssertion 做 8 类校验，回填 validation_status/errors。

校验项（对应 spec）：
1. subject_type 是否存在
2. object_type 是否存在（entity 断言）
3. predicate 是否合法关系（entity 断言）
4. domain/range 方向是否合法（entity 断言）
5. object_kind=literal 时 property 是否属于 subject_type 的合法属性
6. canonical id / 引用非空
7. provenance（source_doc_id / source_chunk_id / source_text_quote / source_type）非空
8. 去重（同一 subject/predicate/object 只保留一个）
"""
from core.kg.schema_manager import SchemaManager


class AssertionValidator:
    def __init__(self, schema_manager=None):
        self.sm = schema_manager or SchemaManager()

    def validate(self, assertions):
        """原地回填 validation_status / validation_errors，返回汇总 dict。"""
        passed = failed = 0
        seen = set()
        for a in assertions:
            errors = self._check(a, seen)
            if errors:
                a.validation_status = "failed"
                a.validation_errors = errors
                failed += 1
            else:
                a.validation_status = "passed"
                passed += 1
        return {
            "total": len(assertions),
            "passed": passed,
            "failed": failed,
            "assertions": assertions,
        }

    def _check(self, a, seen):
        errors = []

        # 1. subject_type
        if not self.sm.validate_entity_type(a.subject_type):
            errors.append(f"subject_type 非法: {a.subject_type}")

        if a.object_kind == "entity":
            # 2. object_type
            if not self.sm.validate_entity_type(a.object_type):
                errors.append(f"object_type 非法: {a.object_type}")
            # 3. predicate
            if not self.sm.validate_relation(a.predicate):
                errors.append(f"predicate 非法关系: {a.predicate}")
            # 4. domain/range
            else:
                if not self.sm.validate_relation_domain(a.subject_type, a.predicate, a.object_type):
                    errors.append(
                        f"domain/range 不合法: {a.subject_type} -[{a.predicate}]-> {a.object_type}"
                    )
            # 6a. object_id 非空
            if a.object_id is None or a.object_id == "":
                errors.append("object_id 为空")
        else:
            # 5. literal 属性校验
            if not self.sm.validate_entity_type(a.subject_type):
                errors.append(f"subject_type 非法: {a.subject_type}")
            else:
                attrs = self.sm.get_entity_attributes(a.subject_type) or []
                valid_props = {x.get("name") for x in attrs if isinstance(x, dict) and x.get("name")}
                if valid_props and a.predicate not in valid_props:
                    errors.append(f"属性 {a.predicate} 不在 {a.subject_type} 的合法属性中")

        # 6b. subject_id 非空
        if a.subject_id is None or a.subject_id == "":
            errors.append("subject_id 为空")

        # 7. provenance
        if not a.source_doc_id:
            errors.append("source_doc_id 缺失")
        if not a.source_chunk_id:
            errors.append("source_chunk_id 缺失")
        if not a.source_text_quote:
            errors.append("source_text_quote 缺失")
        if not a.source_type:
            errors.append("source_type 缺失")

        # 8. 去重
        key = (a.subject_id, a.predicate, a.object_id)
        if key in seen:
            errors.append("duplicate assertion")
        else:
            seen.add(key)

        return errors
