import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from core.wiki.routes import register
from core.wiki.service import WikiService
from core.wiki.generation import Generator
from core.wiki.citations import validate_revision
from test_wiki_v2 import ev,raw
class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.env=patch.dict(os.environ,{"CHEM_KB_BASE_DIR":str(self.base)});self.env.start()
        self.meta=self.base/"data/vector_store/index_metadata.json";self.meta.parent.mkdir(parents=True)
        self.meta.write_text(json.dumps([ev("A")["metadata"]]),encoding="utf-8")
        self.service=WikiService(self.base/"wiki")
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_changed_source_status_marks_stale(self):
        self.service.create_draft("氨",[raw()])
        rows=json.loads(self.meta.read_text());rows[0]["status"]="REPEALED";self.meta.write_text(json.dumps(rows))
        result=self.service.refresh_sources(self.meta)
        self.assertEqual(result["entries"][0]["freshness"],"stale")
    def test_new_relevant_document_requires_check(self):
        self.service.create_draft("氨",[raw()])
        rows=json.loads(self.meta.read_text());rows.append(ev("B","氨新增原文")["metadata"]);self.meta.write_text(json.dumps(rows))
        self.service.refresh_sources(self.meta)
        self.assertEqual(self.service.repo.entry("氨")["freshness"],"needs_check")
    def test_body_block_mismatch_is_rejected(self):
        x=raw();x["knowledge_blocks"][0]["text"]="正文中不存在的事实"
        p=self.service.create_draft("氨",[x])
        self.assertFalse(validate_revision(p)["ok"])
    def test_partial_refresh_preserves_manually_edited_section(self):
        p=self.service.create_draft("氨",[raw(),raw("理化性质","B")]);s=p["sections"][0]
        self.service.review("氨",{"expected_revision":p["revision_id"],"section_id":s["section_id"],"review_status":"modified",
            "reviewer":"reviewer","review_comment":"原文核实","reviewed_content":"人工编辑。[Wiki证据1]。"})
        p=self.service.repo.read("氨")
        q=self.service.create_draft("氨",[p["sections"][0],raw("理化性质","C")],fallback=p["evidence"],expected=p["revision_id"])
        self.assertEqual(q["sections"][0]["content"],"人工编辑。[Wiki证据1]。")
        self.assertEqual(q["sections"][0]["content_hash"],p["sections"][0]["content_hash"])
        self.assertEqual(self.service.repo.reviews(q["revision_id"])["基本概述"]["review_status"],"modified")
    def test_unpublished_export_is_not_mislabeled(self):
        app=Flask(__name__);service=register(app,self.base/"wiki");service.create_draft("氨",[raw()])
        client=app.test_client()
        self.assertEqual(client.get("/api/wiki/氨/export").status_code,404)
        self.assertEqual(client.get("/api/wiki/氨/export?view=draft").status_code,200)
    def test_pdf_path_cannot_escape_pdf_root(self):
        outside=self.base/"outside.pdf";outside.write_bytes(b"%PDF-1.0")
        x=raw();x["evidence"][0]["metadata"]["pdf_path"]=str(outside)
        app=Flask(__name__);service=register(app,self.base/"wiki");p=service.create_draft("氨",[x])
        eid=p["evidence"][0]["evidence_id"]
        self.assertEqual(app.test_client().get("/api/wiki/氨/evidence/"+eid+"/pdf").status_code,404)
    def test_compare_keeps_versions_intact(self):
        p=self.service.create_draft("氨",[raw()])
        q=self.service.create_draft("氨",[raw(text="新正文。[Wiki证据1]。")],expected=p["revision_id"])
        result=self.service.compare("氨",p["revision_id"],q["revision_id"])
        self.assertEqual(result["changed_sections"],["基本概述"]);self.assertIn("新正文",result["diff"])
    def test_truncated_json_is_not_recovered_as_success(self):
        class LLM:
            def generate(self,*args,**kwargs):return '{"content":"半截'
        class RAG:llm=LLM()
        with self.assertRaises(ValueError):Generator(RAG()).call("prompt")
