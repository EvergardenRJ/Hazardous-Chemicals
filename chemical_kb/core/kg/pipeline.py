# -*- coding: utf-8 -*-
"""EDC + R Pipeline：串联 Document Router -> Rule -> Retriever -> Extractor ->
Definer -> Canonicalizer -> Assertion Builder -> Validator，跑通单个真实 chunk。

v0.2：存在 verified cases 时调用 CaseRetriever 注入 Success / Failure 上下文；
冷启动（无 verified）时 case_context 为空，与 v0.1 完全一致。
"""
import json
from pathlib import Path

from core.kg.schema_manager import SchemaManager
from core.kg.schema_repository import OUTPUT_DIR
from core.kg.document_router import DocumentRouter
from core.kg.rule_extractor import RuleExtractor
from core.kg.extractor import Extractor, ExtractionDraft, parse_llm_json, EXTRACTION_SYSTEM_PROMPT
from core.kg.definer import Definer
from core.kg.canonicalizer import Canonicalizer
from core.kg.assertion import AssertionBuilder
from core.kg.validator import AssertionValidator


class KGExtractionPipeline:
    def __init__(self, schema_manager=None, retriever=None, verbose=False,
                 use_definer_llm=False, use_canonicalizer_llm=False, case_retriever=None):
        self.sm = schema_manager or SchemaManager()
        self.router = DocumentRouter()
        self.rule_extractor = RuleExtractor()
        self.extractor = Extractor(llm=None, schema_manager=self.sm)
        self.definer = Definer(schema_manager=self.sm, use_llm=use_definer_llm)
        self.canonicalizer = Canonicalizer(schema_manager=self.sm, use_llm=use_canonicalizer_llm)
        self.builder = AssertionBuilder(schema_manager=self.sm)
        self.validator = AssertionValidator(schema_manager=self.sm)
        self.retriever = retriever  # 可选；None 时跳过 Schema Retriever
        self.case_retriever = case_retriever  # 可选；None 时跳过 Case Retriever
        self.verbose = verbose
        # 累计统计（用于回传第 10 节 JSON 解析统计）
        self.parse_stats = {"json.loads": 0, "code_fence": 0, "object_scan": 0,
                            "failed": 0, "retry": 0}

    # ------------------------------------------------------------------ #
    def process_chunk(self, chunk):
        """Run the full extraction pipeline for one indexed chunk."""
        text = str(chunk.get("text", "") or "")
        metadata = self._extract_metadata(chunk)
        doc_type = self.router.route(metadata)
        rule_annotations = self.rule_extractor.extract(text, metadata, doc_type)
        schema_context = self.retriever.retrieve(text) if self.retriever else None
        case_context = self._case_context(text, doc_type)
        draft = self.extractor.extract(text, doc_type, rule_annotations,
                                       schema_context, case_context)
        return self._finish_draft(chunk, metadata, doc_type, rule_annotations,
                                  schema_context, case_context, draft)

    def process_batch(self, chunks):
        """Run LLM extraction for several chunks together, then validate separately."""
        if len(chunks) <= 1:
            return [self.process_chunk(chunk) for chunk in chunks]
        prepared = []
        prompts = []
        for chunk in chunks:
            text = str(chunk.get("text", "") or "")
            metadata = self._extract_metadata(chunk)
            doc_type = self.router.route(metadata)
            rules = self.rule_extractor.extract(text, metadata, doc_type)
            schema_context = self.retriever.retrieve(text) if self.retriever else None
            case_context = self._case_context(text, doc_type)
            prompts.append(self.extractor._build_prompt(text, doc_type, rules,
                                                        schema_context, case_context))
            prepared.append((chunk, metadata, doc_type, rules, schema_context, case_context))
        raw_outputs = self.extractor.llm.generate_batch(
            prompts, system_prompt=EXTRACTION_SYSTEM_PROMPT,
            max_new_tokens=2048, temperature=0.2,
        )
        if len(raw_outputs) != len(prepared):
            raise RuntimeError("LLM batch returned an unexpected number of outputs")
        results = []
        for prep, raw in zip(prepared, raw_outputs):
            chunk, metadata, doc_type, rules, schema_context, case_context = prep
            obj, method = parse_llm_json(raw)
            if obj is None or not isinstance(obj, dict):
                draft = self.extractor.extract(str(chunk.get("text", "") or ""),
                                               doc_type, rules, schema_context, case_context)
            else:
                draft = ExtractionDraft(
                    status="ok", entity_mentions=obj.get("entity_mentions", []) or [],
                    relation_phrases=obj.get("relation_phrases", []) or [],
                    attribute_mentions=obj.get("attribute_mentions", []) or [],
                    requirement_candidates=obj.get("requirement_candidates", []) or [],
                    clause_mentions=obj.get("clause_mentions", []) or [],
                    raw=raw, parse_method=method,
                )
            results.append(self._finish_draft(chunk, metadata, doc_type, rules,
                                              schema_context, case_context, draft))
        return results

    def _case_context(self, text, doc_type):
        if self.case_retriever is None:
            return None
        try:
            return self.case_retriever.retrieve(
                text, doc_type, self._source_type(doc_type),
                top_k_success=3, top_k_failure=3,
            )
        except Exception:
            return None

    def _finish_draft(self, chunk, metadata, doc_type, rule_annotations,
                      schema_context, case_context, draft):
        self._record_parse(draft)
        if draft.status == "extraction_failed":
            return self._wrap_result(chunk, doc_type, metadata, rule_annotations,
                                     schema_context, case_context, draft, [], [], [], [],
                                     "extraction_failed")
        define_results = self.definer.define(draft.relation_phrases, schema_context,
                                             draft.entity_mentions,
                                             section=str(metadata.get("section", "") or ""))
        canonical_results = self.canonicalizer.canonicalize(draft, metadata, doc_type)
        assertions, unresolved = self.builder.build(
            draft, define_results, canonical_results, metadata, doc_type,
            rule_annotations=rule_annotations,
        )
        validation = self.validator.validate(assertions)
        return self._wrap_result(chunk, doc_type, metadata, rule_annotations,
                                 schema_context, case_context, draft, define_results,
                                 canonical_results, assertions, unresolved, "ok", validation)

    # ------------------------------------------------------------------ #
    def _wrap_result(self, chunk, doc_type, metadata, rule_annotations,
                     schema_context, case_context, draft, define_results,
                     canonical_results, assertions, unresolved, status, validation=None):
        return {
            "chunk_id": chunk.get("chunk_id", ""),
            "doc_id": metadata.get("doc_id", ""),
            "doc_type": doc_type,
            "title": metadata.get("title", ""),
            "code": metadata.get("code", ""),
            "section": metadata.get("section", ""),
            "page_start": metadata.get("page_start", ""),
            "page_end": metadata.get("page_end", ""),
            "status": status,
            "text": chunk.get("text", ""),
            "rule_annotations": rule_annotations.to_dict(),
            "schema_context": schema_context,
            "case_context": case_context,
            "extraction_draft": draft.to_dict(),
            "define_results": [d.to_dict() for d in define_results],
            "canonical_results": [c.to_dict() for c in canonical_results],
            "assertions": [a.to_dict() for a in assertions],
            "unresolved_relations": unresolved,
            "validation": validation,
        }

    # ------------------------------------------------------------------ #
    def _record_parse(self, draft):
        if draft.status == "ok":
            self.parse_stats[draft.parse_method] = self.parse_stats.get(draft.parse_method, 0) + 1
        else:
            self.parse_stats["failed"] += 1
        if draft.retry_used:
            self.parse_stats["retry"] += 1

    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_metadata(chunk):
        keys = ("doc_id", "chunk_id", "title", "document_type", "doc_type", "code",
                "source", "source_type", "page", "page_start", "page_end", "section")
        meta = {k: chunk.get(k) for k in keys if chunk.get(k) is not None}
        # 统一 page_start/page_end：标准类 chunk 用 page，事故用 page_start/page_end
        if not meta.get("page_start") and chunk.get("page") is not None:
            meta["page_start"] = chunk.get("page")
        if not meta.get("page_end") and chunk.get("page") is not None:
            meta["page_end"] = chunk.get("page")
        return meta

    @staticmethod
    def _source_type(doc_type):
        return {"accident": "事故", "standard": "标准", "regulation": "法规"}.get(doc_type, doc_type)


# --------------------------------------------------------------------------- #
# 落盘候选层
# --------------------------------------------------------------------------- #
def save_candidate_layer(result, output_dir=None, prefix=""):
    """把 pipeline 结果落盘为 candidate_assertions / validation_failed / unresolved_relations。

    output_dir 默认 data/kg/output/，prefix 用于区分事故/标准测试（如 "accident_"/"standard_"）。
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    assertions = result.get("assertions", [])
    # 只写通过的断言到 candidate_assertions.jsonl
    passed = [a for a in assertions if a.get("validation_status") == "passed"]
    failed = [a for a in assertions if a.get("validation_status") == "failed"]

    files = {}
    files["candidate_assertions"] = output_dir / f"{prefix}candidate_assertions.jsonl"
    files["validation_failed"] = output_dir / f"{prefix}validation_failed.jsonl"
    files["unresolved_relations"] = output_dir / f"{prefix}unresolved_relations.jsonl"
    files["full_result"] = output_dir / f"{prefix}pipeline_result.json"

    _write_jsonl(files["candidate_assertions"], passed)
    _write_jsonl(files["validation_failed"], failed)
    _write_jsonl(files["unresolved_relations"], result.get("unresolved_relations", []))
    # 全量结果（便于人工检查），校验汇总单独字段
    full = dict(result)
    full.pop("text", None)
    with open(files["full_result"], "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2, default=str)

    return {name: str(p) for name, p in files.items()}


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
