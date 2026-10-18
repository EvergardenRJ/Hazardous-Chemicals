import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core.wiki_store import WikiStore
import importlib.util
spec=importlib.util.spec_from_file_location("wiki_review_compat",Path(__file__).resolve().parents[1]/"core/kg/wiki_review_manager.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
WikiReviewManager=module.WikiReviewManager
from core.wiki.service import WikiService
from test_wiki_v2 import raw
class CompatTests(unittest.TestCase):
    def test_compat_paths_and_reviews_share_authority(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{"CHEM_KB_BASE_DIR":temp}):
            service=WikiService();p=service.create_draft("氨",[raw()])
            store=WikiStore();manager=WikiReviewManager()
            self.assertEqual(Path(store.wiki_dir),Path(temp)/"data/wiki")
            self.assertEqual(store.list_all(),["氨"])
            self.assertEqual(manager.get_statistics()["pending"],1)
            r=manager.submit_review("氨",{"revision_id":p["revision_id"],"section":"基本概述",
                "reviewer":"reviewer","review_status":"approved"})
            self.assertEqual(r["reviewer"],"reviewer")
            self.assertEqual(manager.get_statistics()["approved"],1)
    def test_missing_revision_legacy_review_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            manager=WikiReviewManager(wiki_dir=temp)
            with self.assertRaises(ValueError):manager.submit_review("氨",{"review_status":"approved"})
    def test_unknown_entity_read_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            store=WikiStore(temp)
            self.assertIsNone(store.load("不存在"))
            self.assertFalse((Path(temp)/"不存在").exists())
