import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from core.wiki.routes import register
from core.wiki.service import WikiService
from core.wiki.jobs import Jobs
from core.wiki.worker import Worker
from test_wiki_v2 import raw
class Stub:
    policy="test"
    def generate_section(self,entity,title,checkpoint):return raw(title)
class FullTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.env=patch.dict(os.environ,{"CHEM_KB_BASE_DIR":str(self.base)});self.env.start()
        self.service=WikiService(self.base/"wiki");self.jobs=Jobs(self.service.repo)
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_full_refresh_replaces_nonstandard_legacy_sections(self):
        p=self.service.create_draft("氨",[raw("1. 概述")])
        self.jobs.create("氨",{"mode":"replace_page","sections":["基本概述","理化性质"]})
        worker=Worker(self.service,resource_check=lambda:False);worker.generator=Stub();worker.once()
        q=self.service.repo.read("氨")
        self.assertEqual([s["section"] for s in q["sections"]],["基本概述","理化性质"])
        self.assertEqual(self.service.repo.read("氨",p["revision_id"])["sections"][0]["section"],"1. 概述")
    def test_full_refresh_preserves_expert_edits(self):
        p=self.service.create_draft("氨",[raw()]);s=p["sections"][0]
        self.service.review("氨",{"expected_revision":p["revision_id"],"section_id":s["section_id"],
            "review_status":"modified","reviewer":"expert","review_comment":"核查原文","reviewed_content":"专家编辑。[Wiki证据1]。"})
        self.jobs.create("氨",{"mode":"replace_page","sections":["基本概述","理化性质"]})
        worker=Worker(self.service,resource_check=lambda:False);worker.generator=Stub();worker.once()
        q=self.service.repo.read("氨")
        self.assertEqual(q["sections"][0]["content"],"专家编辑。[Wiki证据1]。")
        self.assertEqual(self.service.repo.reviews(q["revision_id"])["基本概述"]["reviewer"],"expert")
    def test_export_uses_requested_history_revision(self):
        app=Flask(__name__);service=register(app,self.base/"other")
        p=service.create_draft("氨",[raw(text="旧正文。[Wiki证据1]。")])
        service.create_draft("氨",[raw(text="新正文。[Wiki证据1]。")],expected=p["revision_id"])
        response=app.test_client().get("/api/wiki/氨/export?view=history&revision="+p["revision_id"])
        text=response.data.decode()
        self.assertEqual(response.status_code,200);self.assertIn("旧正文",text);self.assertNotIn("新正文",text)
        self.assertIn(p["revision_id"],text)
    def test_revision_freshness_is_not_published_entry_freshness(self):
        p=self.service.create_draft("氨",[raw()])
        with self.service.repo.connect() as db:db.execute("UPDATE revisions SET freshness='stale' WHERE revision_id=?",(p["revision_id"],))
        self.assertEqual(self.service.detail("氨")["freshness"],"stale")
