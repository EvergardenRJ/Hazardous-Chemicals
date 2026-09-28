# -*- coding: utf-8 -*-
"""Wiki Review Manager：Wiki section 级人工审核队列。

每个 Wiki section 一条审核记录（v0.4 规格 3）：
wiki_id / entity / section / content / knowledge_source / evidence_ids /
review_status / review_comment / reviewed_content / reviewed_at / error_type。

存储：data/wiki/review/{entity}.json（keyed by section，幂等更新，不物理删历史）。
knowledge_source 由是否有 [Wiki证据N] 引用决定：有 = grounded，无 = model_prior。
"""
import json
import re
from datetime import datetime
from pathlib import Path

from core.config import BASE_DIR

WIKI_REVIEW_DIR = BASE_DIR / "data" / "wiki" / "review"
WIKI_DIR = BASE_DIR / "data" / "wiki"

_EVIDENCE_RE = re.compile(r"\[Wiki证据(\d+)\]")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _safe(name):
    return re.sub(r"[\\/\s]+", "_", str(name or ""))


class WikiReviewManager:
    def __init__(self, review_dir=None):
        self.review_dir = Path(review_dir) if review_dir else WIKI_REVIEW_DIR
        self.review_dir.mkdir(parents=True, exist_ok=True)

    def _file(self, entity):
        return self.review_dir / f"{_safe(entity)}.json"

    # ------------------------------------------------------------------ #
    # 解析 section
    # ------------------------------------------------------------------ #
    @staticmethod
    def parse_sections(markdown):
        """把 wiki.md 按 '## ' 切分，返回 [{section, content, knowledge_source, evidence_ids}]。"""
        sections = []
        current = None
        for line in (markdown or "").splitlines():
            if line.startswith("## "):
                if current is not None:
                    sections.append(current)
                current = {"section": line[3:].strip(), "content": ""}
            elif current is not None:
                current["content"] += line + "\n"
        if current is not None:
            sections.append(current)
        for s in sections:
            ids = _EVIDENCE_RE.findall(s["content"])
            s["knowledge_source"] = "grounded" if ids else "model_prior"
            s["evidence_ids"] = ids
        return sections

    # ------------------------------------------------------------------ #
    # 结构化 sections（v0.5：直接读 knowledge_blocks，不再靠"有没有引用"猜）
    # ------------------------------------------------------------------ #
    def load_structured_sections(self, entity):
        p = WIKI_DIR / _safe(entity) / "sections.json"
        if not p.exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return None
        return [self._normalize_section(s) for s in raw if isinstance(s, dict) and s.get("section")]

    def get_sections(self, entity, markdown=None):
        """优先读结构化 sections.json，否则回退到 markdown 启发式解析。"""
        structured = self.load_structured_sections(entity)
        if structured:
            return structured
        return self.parse_sections(markdown or "")

    @staticmethod
    def _normalize_section(s):
        content = (s.get("content") or "").strip()
        blocks = s.get("knowledge_blocks") or []
        ks, ids = WikiReviewManager._derive_knowledge_source(content, blocks)
        return {
            "section": s.get("section", ""),
            "content": content,
            "knowledge_source": ks,
            "evidence_ids": ids,
            "knowledge_blocks": blocks,
        }

    @staticmethod
    def _derive_knowledge_source(content, blocks):
        grounded_ids = []
        has_grounded = False
        has_model = False
        for b in blocks:
            if not isinstance(b, dict):
                continue
            src = b.get("knowledge_source", "")
            if src == "grounded":
                has_grounded = True
                for eid in (b.get("evidence_ids") or []):
                    if str(eid) not in grounded_ids:
                        grounded_ids.append(str(eid))
            elif src == "model_prior":
                has_model = True
        if has_grounded and has_model:
            return "mixed", grounded_ids
        if has_grounded:
            return "grounded", grounded_ids
        if has_model:
            return "model_prior", []
        ids = _EVIDENCE_RE.findall(content)
        return ("grounded" if ids else "model_prior"), ids

    # ------------------------------------------------------------------ #
    # 读取 / 初始化 / 提交
    # ------------------------------------------------------------------ #
    def get_reviews(self, entity):
        path = self._file(entity)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def init_review(self, entity, markdown, force=False):
        """幂等：为每个 section 建 pending 记录（已存在则保留原状态）。"""
        reviews = {} if force else self.get_reviews(entity)
        created = 0
        for s in self.get_sections(entity, markdown):
            sec = s["section"]
            if sec not in reviews:
                reviews[sec] = {
                    "wiki_id": entity,
                    "entity": entity,
                    "section": sec,
                    "content": s["content"].strip(),
                    "knowledge_source": s["knowledge_source"],
                    "evidence_ids": s["evidence_ids"],
                    "review_status": "pending",
                    "review_comment": "",
                    "reviewed_content": "",
                    "error_type": "",
                    "reviewed_at": "",
                    "review_id": f"WREV_{_safe(entity)}_{_safe(sec)}",
                }
                created += 1
        self._write(entity, reviews)
        return {"total": len(reviews), "created": created}

    def submit_review(self, entity, record):
        """写/更新某 section 的审核记录（幂等，按 section 覆盖）。"""
        reviews = self.get_reviews(entity)
        record = dict(record)
        record.setdefault("wiki_id", entity)
        record.setdefault("entity", entity)
        record.setdefault("section", record.get("section", ""))
        record.setdefault("review_id", f"WREV_{_safe(entity)}_{_safe(record.get('section',''))}")
        record.setdefault("reviewed_at", _now())
        reviews[record.get("section", "")] = record
        self._write(entity, reviews)
        return record

    def _write(self, entity, reviews):
        self._file(entity).write_text(
            json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def get_statistics(self):
        stats = {"pending": 0, "approved": 0, "rejected": 0, "modified": 0, "total": 0}
        for f in self.review_dir.glob("*.json"):
            try:
                reviews = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for r in reviews.values():
                st = r.get("review_status", "")
                if st in stats:
                    stats[st] += 1
                stats["total"] += 1
        return stats
