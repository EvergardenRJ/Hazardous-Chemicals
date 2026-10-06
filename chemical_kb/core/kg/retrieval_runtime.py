"""CPU-backed Schema and verified Case retrieval for full-corpus extraction.

The Qwen extractor owns the GPU. The same BGE-M3 encoder is reused for
Schema, Success Case, and Failure Case lookup of a chunk.
"""
from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

from core.config import BASE_DIR, EMBED_MODEL
from core.kg.case_repository import CaseRepository
from core.kg.case_retriever import CaseRetriever
from core.kg.schema_repository import SCHEMA_INDEX_DIR
from core.kg.schema_retriever import SchemaRetriever


class CachedCPUEmbedding:
    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(EMBED_MODEL, device="cpu")
        self.dimension = self.model.get_sentence_embedding_dimension()
        self._last_text = None
        self._last_vector = None

    def encode(self, text):
        text = str(text or "")
        if text != self._last_text:
            self._last_vector = np.asarray(
                self.model.encode(
                    [text], normalize_embeddings=True,
                    convert_to_numpy=True, show_progress_bar=False,
                ),
                dtype="float32",
            )
            self._last_text = text
        return self._last_vector


def _verified_cases():
    repo = CaseRepository()
    cases = repo.verified_cases()
    review_path = BASE_DIR / "data/kg/review/reviewed.jsonl"
    reviews = {
        row.get("review_id"): row
        for row in (json.loads(line) for line in review_path.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    for case in cases:
        review = reviews.get(case.get("review_id"))
        expected = {"success": {"approved"}, "failure": {"modified", "rejected"}}
        if not review or review.get("decision") not in expected.get(case.get("case_type"), set()):
            raise RuntimeError(f"Case lacks a matching reviewed event: {case.get('case_id')}")
        if not case.get("source_text"):
            raise RuntimeError(f"Case lacks source text: {case.get('case_id')}")
    if not cases:
        raise RuntimeError("No verified cases; Case retrieval cannot be enabled")
    return repo, cases


def build_case_index():
    repo, cases = _verified_cases()
    repo._embedding_model = CachedCPUEmbedding()
    counts = repo.rebuild_index()
    print(json.dumps({"verified": len(cases), "indexed": counts}, ensure_ascii=False))
    return counts


def _check_index(index_path: Path, metadata_path: Path, dimension: int):
    if not index_path.is_file() or not metadata_path.is_file():
        raise RuntimeError(f"Missing retrieval index: {index_path}")
    index = faiss.read_index(str(index_path))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if index.d != dimension or index.ntotal != len(metadata):
        raise RuntimeError(f"Retrieval index/metadata mismatch: {index_path}")
    return metadata


def load_retrievers():
    repo, cases = _verified_cases()
    embedding = CachedCPUEmbedding()
    _check_index(
        SCHEMA_INDEX_DIR / "schema.index",
        SCHEMA_INDEX_DIR / "schema_metadata.json",
        embedding.dimension,
    )
    for kind in ("success", "failure"):
        folder = repo.success_dir if kind == "success" else repo.failure_dir
        metadata = _check_index(folder / "faiss.index", folder / "metadata.json", embedding.dimension)
        expected = [case for case in cases if case.get("case_type") == kind]
        if metadata != expected:
            raise RuntimeError(f"Case index is stale: {kind}; rebuild before extraction")
    schema = SchemaRetriever(embedding_model=embedding)
    case = CaseRetriever(repository=repo, embedding_model=embedding)
    print(json.dumps({
        "retrieval": "edc-r-case", "embedding_device": "cpu",
        "schema_items": schema.index.ntotal,
        "verified_cases": len(cases),
    }, ensure_ascii=False), flush=True)
    return schema, case


if __name__ == "__main__":
    build_case_index()
