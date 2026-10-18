"""Risk-based tests; every write uses TemporaryDirectory. Never import GPU/RAG."""
import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from core.wiki.citations import bind_sections, digest, validate_revision, validate_section
from core.wiki.repository import Conflict, Repository, NotFound
from core.wiki.service import WikiService
from core.wiki.jobs import Jobs
from core.wiki.worker import Worker

def ev(cid,text="原文依据。"):
    return {"metadata":{"chunk_id":cid,"doc_id":"doc-"+cid,"text":text,"title":cid,"page_start":1,"page_end":1}}
def raw(title="基本概述",cid="A",text="原文支持的描述。[Wiki证据1]。"):
    return {"section":title,"content":text,"evidence":[ev(cid)],"knowledge_blocks":[{"text":text,"knowledge_source":"grounded","evidence_ids":[1]}],"_validated":True}
class WikiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/"wiki"
        self.service=WikiService(self.root);self.jobs=Jobs(self.service.repo)
    def tearDown(self):self.temp.cleanup()
    def draft(self,sections=None):
        return self.service.create_draft("氨",sections or [raw()])
    def review(self,p,status="approved",text=None):
        s=p["sections"][0]
        return self.service.review("氨",{"expected_revision":p["revision_id"],"section_id":s["section_id"],
            "content_hash":s["content_hash"],"review_status":status,"reviewer":"reviewer",
            "review_comment":"核实并修订" if status!="approved" else "","reviewed_content":text})
    def test_per_section_reference_binding(self):
        s,e,errors=bind_sections([raw(cid="A"),raw("理化性质","B")])
        self.assertFalse(errors);self.assertIn("[Wiki证据2]",s[1]["content"])
        self.assertEqual(e[1]["metadata"]["chunk_id"],"B")
    def test_shared_evidence_deduplicates(self):
        s,e,_=bind_sections([raw(cid="A"),raw("理化性质","A")])
        self.assertEqual(len(e),1);self.assertIn("[Wiki证据1]",s[1]["content"])
    def test_reorder_preserves_stable_content_hash(self):
        sections,table,_=bind_sections([raw(cid="A"),raw("理化性质","B")])
        reordered,other,_=bind_sections(list(reversed(sections)),table)
        self.assertEqual({s["section_id"]:s["content_hash"] for s in sections},{s["section_id"]:s["content_hash"] for s in reordered})
    def test_bad_citation_rejected_even_without_blocks(self):
        s,e,errors=bind_sections([{"section":"基本概述","content":"描述。[Wiki证据999]。","evidence":[]}])
        self.assertFalse(validate_revision({"sections":s,"evidence":e,"binding_errors":errors})["ok"])
    def test_grounded_without_evidence_rejected(self):
        self.assertIn("文档证据块没有引用",validate_section({"content":"描述。","knowledge_blocks":[{"knowledge_source":"grounded","evidence_ids":[]}]},[]))
    def test_failed_section_cannot_publish(self):
        x=raw();x["_validated"]=False;p=self.draft([x])
        with self.assertRaises(ValueError):self.review(p)
    def test_high_risk_model_prior_block_cannot_publish(self):
        x={"section":"急救","content":"（模型补充）候选内容。","knowledge_blocks":[{"text":"（模型补充）候选内容。","knowledge_source":"model_prior","evidence_ids":[]}]}
        p=self.draft([x]);self.review(p)
        with self.assertRaises(ValueError):self.service.publish("氨",{"reviewer":"reviewer","expected_revision":p["revision_id"]})
    def test_review_requires_identity(self):
        p=self.draft()
        with self.assertRaises(ValueError):self.service.review("氨",{"expected_revision":p["revision_id"],"section":"基本概述","review_status":"approved"})
    def test_edit_updates_candidate_and_keeps_original(self):
        p=self.draft();edited="已经人工修改的内容。[Wiki证据1]。"
        r=self.review(p,"modified",edited)
        d=self.service.detail("氨")
        self.assertEqual(d["sections"][0]["content"],edited)
        self.assertNotEqual(d["revision_id"],p["revision_id"])
        self.assertEqual(self.service.repo.read("氨",p["revision_id"])["sections"][0]["content"],p["sections"][0]["content"])
        self.assertEqual(r["reviewer"],"reviewer")
    def test_stale_edit_returns_conflict(self):
        p=self.draft();self.review(p,"modified","改文。[Wiki证据1]。")
        with self.assertRaises(Conflict):self.review(p,"modified","另一改文。[Wiki证据1]。")
    def test_publish_requires_current_review(self):
        p=self.draft()
        with self.assertRaises(ValueError):self.service.publish("氨",{"reviewer":"reviewer","expected_revision":p["revision_id"]})
        self.review(p);self.service.publish("氨",{"reviewer":"reviewer","expected_revision":p["revision_id"]})
        self.assertTrue(self.service.detail("氨","published")["is_published"])
    def test_re_review_does_not_mutate_published_revision(self):
        p=self.draft();self.review(p);self.service.publish("氨",{"reviewer":"reviewer","expected_revision":p["revision_id"]})
        self.review(p,"rejected")
        self.assertEqual(self.service.repo.reviews(p["revision_id"])["基本概述"]["review_status"],"approved")
        self.assertEqual(self.service.detail("氨")["sections"][0]["review_status"],"rejected")
    def test_new_content_loses_old_approval(self):
        p=self.draft();self.review(p)
        q=self.service.create_draft("氨",[raw(text="新内容。[Wiki证据1]。")],expected=p["revision_id"])
        self.assertEqual(self.service.detail("氨")["sections"][0]["review_status"],"pending")
    def test_manifest_detects_corruption(self):
        p=self.draft();path=self.root/"entries"/p["wiki_id"]/"revisions"/p["revision_id"]/"payload.json"
        path.write_text("{}",encoding="utf-8")
        with self.assertRaises(ValueError):self.service.repo.read("氨")
    def test_orphan_revision_is_not_registered(self):
        p=self.draft()
        with self.assertRaises(Conflict):self.service.repo.commit("氨",p,"wrong")
        self.assertEqual(self.service.repo.entry("氨")["draft_revision"],p["revision_id"])
        self.assertEqual(len(self.service.repo.history("氨")["revisions"]),1)
    def test_sources_changed_invalidates_search(self):
        p=self.draft();self.review(p);self.service.publish("氨",{"reviewer":"reviewer","expected_revision":p["revision_id"]})
        path=Path(self.temp.name)/"metadata.json"
        path.write_text(json.dumps([ev("A")["metadata"]]),encoding="utf-8")
        self.service.refresh_sources(path);self.assertTrue(self.service.search("描述"))
        path.write_text(json.dumps([{**ev("A")["metadata"],"text":"来源已改"}]),encoding="utf-8")
        self.service.refresh_sources(path)
        self.assertEqual(self.service.search("描述"),[])
        self.assertEqual(self.service.repo.entry("氨")["freshness"],"stale")
    def test_only_published_content_searchable(self):
        p=self.draft();self.assertEqual(self.service.search("描述"),[])
        self.review(p);self.service.publish("氨",{"reviewer":"reviewer","expected_revision":p["revision_id"]})
        self.assertEqual(self.service.search("描述")[0]["revision_id"],p["revision_id"])
    def test_job_idempotency(self):
        a=self.jobs.create("氨",{"sections":["基本概述"],"idempotency_key":"same"})
        b=self.jobs.create("氨",{"sections":["基本概述"],"idempotency_key":"same"})
        self.assertEqual(a["job_id"],b["job_id"])
    def test_job_expired_lease_recovered(self):
        a=self.jobs.create("氨",{"sections":["基本概述"]});self.jobs.claim("old",seconds=-1)
        b=self.jobs.claim("new");self.assertEqual(a["job_id"],b["job_id"])
    def test_cancelled_job_not_claimed(self):
        a=self.jobs.create("氨",{"sections":["基本概述"]});self.jobs.cancel(a["job_id"])
        self.assertIsNone(self.jobs.claim("worker"))
    def test_stale_owner_cannot_write_checkpoint(self):
        self.jobs.create("氨",{"sections":["基本概述"]});a=self.jobs.claim("old",seconds=-1);self.jobs.claim("new")
        with self.assertRaises(Conflict):self.jobs.checkpoint(a["job_id"],"old",{})
    def test_cancel_before_commit_keeps_pointer(self):
        p=self.draft();j=self.jobs.create("氨",{"sections":["基本概述"]});self.jobs.claim("owner")
        self.jobs.cancel(j["job_id"])
        with self.assertRaises(InterruptedError):self.service.repo.commit("氨",{**p,"job_id":j["job_id"],"worker_owner":"owner"},p["revision_id"])
        self.assertEqual(self.service.repo.entry("氨")["draft_revision"],p["revision_id"])
    def test_worker_does_not_load_model_when_kg_busy(self):
        self.jobs.create("氨",{"sections":["基本概述"]})
        worker=Worker(self.service,rag_factory=lambda:(_ for _ in ()).throw(AssertionError("model loaded")),resource_check=lambda:True)
        self.assertFalse(worker.once());self.assertEqual(self.jobs.list()[0]["state"],"queued")
    def test_worker_fake_generation_creates_draft_only(self):
        job=self.jobs.create("氨",{"sections":["基本概述"]})
        class Fake:
            policy="test"
            def generate_section(self,entity,title,callback):return raw(title)
        worker=Worker(self.service,resource_check=lambda:False);worker.generator=Fake()
        self.assertTrue(worker.once())
        self.assertEqual(self.jobs.get(job["job_id"])["state"],"ready_for_review")
        self.assertIsNone(self.service.repo.entry("氨")["published_revision"])
    def test_legacy_import_filters_internal_directories(self):
        for name in ["pages","review","天然气"]:(self.root/name).mkdir(exist_ok=True)
        (self.root/"天然气"/"wiki.md").write_text("# 天然气\n\n## 概述\n\n旧正文。",encoding="utf-8")
        result=self.service.import_legacy();self.assertEqual([r["entity"] for r in result],["天然气"])
        self.assertEqual(self.service.import_legacy(),[])
        self.assertEqual((self.root/"天然气"/"wiki.md").read_text(encoding="utf-8"),"# 天然气\n\n## 概述\n\n旧正文。")
    def test_path_traversal_rejected(self):
        for name in ["..","../other","a/b","a\\b","bad\nname"]:
            with self.assertRaises(ValueError):self.service.create_draft(name,[raw()])

class RouteTests(unittest.TestCase):
    def setUp(self):
        from flask import Flask
        from core.wiki.routes import register
        self.temp=tempfile.TemporaryDirectory();app=Flask(__name__)
        self.service=register(app,self.temp.name);self.client=app.test_client()
    def tearDown(self):self.temp.cleanup()
    def test_creation_is_durable_202(self):
        response=self.client.post("/api/wiki/氨/generate",json={})
        self.assertEqual(response.status_code,202)
        self.assertTrue(response.json["job"]["job_id"])
    def test_invalid_sections_and_identity(self):
        self.assertEqual(self.client.post("/api/wiki/氨/generate",json={"sections":["evil"]}).status_code,400)
        p=self.service.create_draft("氨",[raw()])
        self.assertEqual(self.client.post("/api/wiki/氨/review",json={"expected_revision":p["revision_id"],"section":"基本概述","review_status":"approved"}).status_code,400)
    def test_internal_directories_not_listed(self):
        for n in ["review","pages"]:(Path(self.temp.name)/n).mkdir()
        self.assertEqual(self.client.get("/api/wiki").json["entities"],[])
if __name__=="__main__":unittest.main()
