# -*- coding: utf-8 -*-
"""Hybrid search with vector, BM25 keyword and approved graph evidence routes."""
import json
from pathlib import Path
import numpy as np
from core.config import BASE_DIR
from core.knowledge import KeywordIndex, fuse_rrf, _approved


class HybridRetriever:
    def __init__(self, embedding, vector_store, reranker, graph_service=None,
                 keyword_path=None, review_path=None):
        self.embedding = embedding
        self.vector_store = vector_store
        self.reranker = reranker
        self.keyword = KeywordIndex(keyword_path or BASE_DIR / "data/search/keyword.sqlite")
        self.graph_service = graph_service
        self.review_path = Path(review_path or BASE_DIR / "data/kg/review/reviewed.jsonl")

    def _graph_search_local(self, question, limit=30):
        if not self.review_path.exists():
            return []
        with self.review_path.open(encoding="utf-8") as stream:
            reviews = [json.loads(line) for line in stream if line.strip()]
        lookup = {str(meta.get("chunk_id")): meta for meta in self.vector_store.metadata
                  if meta.get("chunk_id")}
        results, seen = [], set()
        for assertion in _approved(reviews):
            labels = (assertion.get("subject_label", ""), assertion.get("object_label", ""))
            if not any(len(label) >= 2 and label in question for label in labels):
                continue
            chunk_id = str(assertion.get("source_chunk_id") or "")
            if chunk_id in seen or chunk_id not in lookup:
                continue
            seen.add(chunk_id)
            meta = {**lookup[chunk_id],
                    "valid_from": assertion.get("valid_from") or lookup[chunk_id].get("valid_from"),
                    "valid_to": assertion.get("valid_to") or lookup[chunk_id].get("valid_to")}
            results.append({"score": float(assertion.get("confidence") or 0), "metadata": meta})
            if len(results) >= limit:
                break
        return results

    def _graph_search(self, question, limit=30):
        if self.graph_service is None:
            try:
                from core.kg.graph_query_service import GraphQueryService
                self.graph_service = GraphQueryService()
            except Exception:
                return self._graph_search_local(question, limit)
        try:
            with self.graph_service.store.connect().session() as session:
                nodes = list(session.run(
                    "MATCH (n) WHERE n.name IS NOT NULL AND size(n.name) >= 2 "
                    "AND $question CONTAINS n.name "
                    "RETURN n.canonical_id AS canonical_id "
                    "ORDER BY size(n.name) DESC LIMIT 8", question=question))
            ids = [n["canonical_id"] for n in nodes if n["canonical_id"]]
            if not ids:
                return self._graph_search_local(question, limit)
            with self.graph_service.store.connect().session() as session:
                recs = session.run(
                    "MATCH (a)-[r]-(b) WHERE a.canonical_id IN $ids "
                    "AND r.review_status = 'approved' AND r.source_chunk_id IS NOT NULL "
                    "RETURN r.source_chunk_id AS chunk_id, r.source_doc_id AS doc_id, "
                    "r.valid_from AS valid_from, r.valid_to AS valid_to "
                    "LIMIT $limit", ids=ids, limit=limit)
                matches = list(recs)
            lookup = {str(m.get("chunk_id")): m for m in self.vector_store.metadata
                      if m.get("chunk_id")}
            results = []
            for rec in matches:
                meta = lookup.get(str(rec["chunk_id"]))
                if meta:
                    meta = {**meta, "valid_from": rec.get("valid_from") or meta.get("valid_from"),
                            "valid_to": rec.get("valid_to") or meta.get("valid_to")}
                    results.append({"score": 1.0, "metadata": meta})
            return results or self._graph_search_local(question, limit)
        except Exception:
            return self._graph_search_local(question, limit)

    def query(self, question, search_top_k=50, final_top_k=15, as_of=None):
        vector = self.embedding.encode(question)
        if not isinstance(vector, np.ndarray):
            vector = np.asarray(vector, dtype="float32")
        routes = {
            "vector": self.vector_store.search(vector, top_k=search_top_k),
            "keyword": self.keyword.search(question, limit=search_top_k),
            "graph": self._graph_search(question, limit=search_top_k),
        }
        fused = fuse_rrf(routes, at=as_of, limit=search_top_k)
        if not fused:
            return []
        reranked = self.reranker.rerank(question, fused)
        # Existing reranker may limit to five records.
        out, per_doc = [], {}
        for item in reranked:
            doc = item.get("metadata", {}).get("doc_id")
            if per_doc.get(doc, 0) >= 2:
                continue
            per_doc[doc] = per_doc.get(doc, 0) + 1
            out.append(item)
        return out[:final_top_k]

