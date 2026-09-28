import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from core.knowledge import KeywordIndex, active_at, overlap, fuse_rrf, entity_candidates, find_conflicts, export_graph
from core.entity_registry import EntityRegistry
from core.hybrid_retriever import HybridRetriever


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.a = {"assertion_id":"a1","subject_id":"chemical:chlorine","subject_type":"chemical",
                  "subject_label":"氯气","predicate":"has_hazard","object_id":"hazard:toxic",
                  "object_type":"hazard","object_label":"有毒","source_doc_id":"doc1",
                  "source_chunk_id":"chunk1","valid_from":"2020-01-01","valid_to":"2025-01-01"}
        self.b = {**self.a,"assertion_id":"a2","object_id":"hazard:corrosive",
                  "source_doc_id":"doc2","source_chunk_id":"chunk2","valid_from":"2024-01-01","valid_to":""}
        self.c = {**self.a,"assertion_id":"a3","object_id":"hazard:flammable",
                  "source_doc_id":"doc3","valid_from":"2025-01-01","valid_to":""}

    def test_temporal_boundary_and_cross_source_conflict(self):
        self.assertTrue(active_at(self.a, "2024-12-31"))
        self.assertFalse(active_at(self.a, "2025-01-01"))
        self.assertTrue(overlap(self.a, self.b))
        self.assertFalse(overlap(self.a, self.c))
        conflicts = find_conflicts([self.a, self.b, self.c])
        self.assertEqual(len(conflicts), 2)
        self.assertEqual(conflicts[0]["status"], "needs_review")

    def test_keyword_and_fusion(self):
        with tempfile.TemporaryDirectory() as td:
            idx = KeywordIndex(Path(td) / "search.sqlite")
            rows = [{"chunk_id":"c1","doc_id":"d1","title":"液氯泄漏","text":"氯气泄漏应急处理"},
                    {"chunk_id":"c2","doc_id":"d2","title":"甲醇储存","text":"易燃液体"}]
            idx.build(rows)
            hit = idx.search("氯气泄漏")
            self.assertEqual(hit[0]["metadata"]["chunk_id"], "c1")
            routes = {"vector":[{"score":.9,"metadata":rows[1]},{"score":.8,"metadata":rows[0]}],
                      "keyword":hit}
            fused = fuse_rrf(routes)
            self.assertEqual(fused[0]["metadata"]["chunk_id"], "c1")
            self.assertEqual(set(fused[0]["routes"]), {"vector","keyword"})

    def test_entity_review_reversible(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [self.a,{**self.a,"subject_id":"chemical:cl2","source_doc_id":"doc2"}]
            candidates = entity_candidates(rows)
            self.assertEqual(len(candidates),1)
            reg = EntityRegistry(Path(td)/"aliases.jsonl")
            reg.decide("chemical:cl2","chemical:chlorine","reviewer")
            self.assertEqual(reg.resolve("chemical:cl2"),"chemical:chlorine")
            reg.decide("chemical:cl2","chemical:chlorine","reviewer",action="revoke")
            self.assertEqual(reg.resolve("chemical:cl2"),"chemical:cl2")

    def test_hybrid_as_of_and_fallback(self):
        class Embed:
            def encode(self, text):
                return [1.0, 0.0]
        class Store:
            metadata = []
            def search(self, vector, top_k=50):
                return [
                    {"score":.9,"metadata":{"chunk_id":"old","doc_id":"d1","text":"旧规定",
                                           "valid_to":"2024-01-01"}},
                    {"score":.8,"metadata":{"chunk_id":"live","doc_id":"d2","text":"现行规定"}},
                ]
        class Ranker:
            def rerank(self, question, docs):
                return [{**d,"rerank_score":1.0} for d in docs]
        with tempfile.TemporaryDirectory() as td:
            retriever = HybridRetriever(Embed(), Store(), Ranker(),
                                        keyword_path=Path(td)/"missing.sqlite")
            retriever._graph_search = lambda question, limit: []
            result = retriever.query("现行规定", as_of="2025-01-01")
            self.assertEqual([r["metadata"]["chunk_id"] for r in result], ["live"])
            self.assertEqual(result[0]["routes"], ["vector"])

    def test_reviewed_graph_fallback(self):
        class Embed:
            def encode(self, text):
                return [1.0]
        class Store:
            metadata = [{"chunk_id":"chunk1","doc_id":"doc1","text":"液氯说明"}]
            def search(self, vector, top_k=50):
                return []
        class Ranker:
            def rerank(self, question, docs):
                return [{**d,"rerank_score":1.0} for d in docs]
        with tempfile.TemporaryDirectory() as td:
            review_path = Path(td)/"reviewed.jsonl"
            review_path.write_text(json.dumps({"decision":"approved","original_assertion":self.a},
                                              ensure_ascii=False)+"\n",encoding="utf-8")
            retriever = HybridRetriever(Embed(),Store(),Ranker(),
                                        keyword_path=Path(td)/"missing.sqlite",
                                        review_path=review_path)
            retriever.graph_service = object()  # fails connect, then uses reviewed JSONL
            result = retriever.query("氯气有什么危害",as_of="2024-01-01")
            self.assertEqual(result[0]["routes"],["graph"])
            self.assertEqual(result[0]["metadata"]["chunk_id"],"chunk1")
            self.assertEqual(retriever.query("氯气有什么危害",as_of="2025-01-01"),[])

    def test_provenance_and_exports(self):
        reviews = [{"decision":"approved","original_assertion":self.a,
                    "review_id":"review1","reviewed_by":"human","reviewed_at":"2024-01-01"}]
        body = json.loads(export_graph(reviews,"jsonld","2024-06-01"))
        self.assertEqual(len(body["@graph"]),5)
        assertion = next(e for e in body["@graph"] if "assertion/a1" in e["@id"])
        self.assertIn("prov:wasDerivedFrom",assertion)
        turtle = export_graph(reviews,"turtle")
        self.assertIn("prov:wasGeneratedBy",turtle)
        ET.fromstring(export_graph(reviews,"graphml"))
        self.assertIn("a1",export_graph(reviews,"csv"))
        self.assertEqual(len(json.loads(export_graph(reviews,"jsonld","2025-01-01"))["@graph"]),0)


if __name__ == "__main__":
    unittest.main()



