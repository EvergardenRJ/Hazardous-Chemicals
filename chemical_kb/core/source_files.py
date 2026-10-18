"""Resolve registered source files inside controlled directories, without guessing ambiguity."""
import json
import re
import time
import unicodedata
from pathlib import Path

_cache = {}

def normalized(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", str(value)).casefold()).replace("_", "")

def files_under(root):
    root = Path(root).resolve()
    cached = _cache.get(str(root))
    if cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    paths = []
    if root.exists():
        for item in root.rglob("*"):
            if item.is_file():
                target = item.resolve()
                if target.is_relative_to(root) and target.suffix.lower() in {".pdf", ".docx", ".doc", ".txt", ".md", ".html"}:
                    paths.append(target)
    _cache[str(root)] = (time.monotonic(), paths)
    return paths

def resolve_source(base, metadata, pdf_only=False):
    base = Path(base).resolve()
    roots = [(base / "data/pdf").resolve(), (base / "data/wiki/sources").resolve(), (base / "data/wiki/platform/sources").resolve()]
    registered = base / "data/knowledge/documents.json"
    rows = []
    if registered.exists():
        try:
            rows = [r for r in json.loads(registered.read_text("utf-8")) if r.get("doc_id") == metadata.get("doc_id")]
        except (OSError, ValueError, TypeError):
            pass
    candidates = []
    for row in [metadata] + rows:
        for key in ("pdf_path", "source_path", "file_path"):
            value = row.get(key)
            if value and str(value).lower() not in {"nan", "none", "null"}:
                item = Path(value)
                item = (item if item.is_absolute() else base / item).resolve()
                if any(item.is_relative_to(root) for root in roots) and item.is_file():
                    if not pdf_only or item.suffix.lower() == ".pdf":
                        candidates.append(item)
    if candidates:
        unique = set(candidates)
        return next(iter(unique)) if len(unique) == 1 else None
    title = normalized(metadata.get("title", ""))
    code = normalized(metadata.get("code", ""))
    docid = str(metadata.get("doc_id") or "")
    if docid.startswith("STD_"):
        short = normalized(docid[4:])
        if not code or len(short) > len(code):
            code = short
    quoted = [normalized(x.removeprefix("全省")) for x in re.findall(r"《([^》]+)》", str(metadata.get("title", "")))]
    years = set(re.findall(r"(?:19|20)\d{2}", str(metadata.get("code", ""))))
    tails = [normalized(x) for x in re.split(r"关于|印发", str(metadata.get("title", ""))) if len(normalized(x)) >= 12]
    ranked = []
    for root in roots:
        for item in files_under(root):
            if pdf_only and item.suffix.lower() != ".pdf":
                continue
            name = normalized(item.stem)
            score = 0
            if title and name == title:
                score = 100
            elif title and len(title) >= 8 and title in name:
                score = 90
            if code and len(code) >= 7 and code in name:
                score = max(score, 95)
            if any(tail in name for tail in tails):
                score = max(score, 80)
            if any(len(t) >= 8 and t in name for t in quoted):
                if not years or any(item.name.startswith(year) for year in years):
                    score = max(score, 85)
            if score:
                ranked.append((score, item))
    if not ranked:
        return None
    best = max(score for score, _ in ranked)
    winners = {item for score, item in ranked if score == best}
    return next(iter(winners)) if len(winners) == 1 else None

