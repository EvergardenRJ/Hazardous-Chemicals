import json,tempfile,unittest
from pathlib import Path
import numpy as np
import faiss
from core.updater import KnowledgeUpdater
from core.vector_store import VectorStore
from core.index_transaction import commit,index_lock,recover
class Model:
    def __init__(self):self.calls=0;self.model=self
    def encode(self,texts,**kwargs):
        self.calls+=1
        return np.array([[len(t),1] for t in texts],dtype="float32")
class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.fi=self.root/"faiss.index";self.fm=self.root/"metadata.json";self.fk=self.root/"keyword.sqlite"
        index=faiss.IndexFlatIP(2);index.add(np.array([[1,1]],dtype="float32"));faiss.write_index(index,str(self.fi))
        self.fm.write_text(json.dumps([{"chunk_id":"a","text":"氨"}]),encoding="utf-8")
        self.model=Model();self.updater=KnowledgeUpdater(self.model,self.fi,self.fm,self.fk)
    def tearDown(self):self.temp.cleanup()
    def test_duplicate_is_noop_before_embedding(self):
        result=self.updater.update([{"chunk_id":"a","text":"氨"}]*2)
        self.assertEqual(result["added"],0);self.assertEqual(self.model.calls,0)
    def test_dedup_and_version_replacement_preserve_positions(self):
        r=self.updater.update([{"chunk_id":"b","text":"液氯"}]*2+[{"chunk_id":"a","text":"氨更新"}])
        self.assertEqual((r["added"],r["updated"],r["count"]),(1,1,2))
        store=VectorStore(self.fi,self.fm,self.fk)
        self.assertEqual([m["chunk_id"] for m in store.metadata],["a","b"])
        self.assertEqual(store.index.ntotal,2)
    def test_conflicting_batch_is_rejected_without_write(self):
        before=self.fi.read_bytes()
        with self.assertRaises(ValueError):self.updater.update([{"chunk_id":"b","text":"x"},{"chunk_id":"b","text":"y"}])
        self.assertEqual(before,self.fi.read_bytes())
    def test_inconsistent_existing_pair_is_rejected(self):
        self.fm.write_text("[]")
        with self.assertRaises(ValueError):self.updater.update([{"chunk_id":"b","text":"x"}])
        self.assertEqual(self.model.calls,0)
    def test_interrupted_commit_rolls_forward_all_files(self):
        stage=self.root/".generation-test";stage.mkdir()
        sources=[]
        for i,dst in enumerate([self.fi,self.fm,self.fk]):
            src=stage/str(i);src.write_bytes(("new-"+str(i)).encode());sources.append((src,dst))
        with self.assertRaises(RuntimeError):commit(self.root,sources,fail_after_journal=True)
        # Simulate interruption after the first replacement.
        self.fi.write_bytes(b"new-0")
        with index_lock(self.root):self.assertTrue(recover(self.root,[self.fi,self.fm,self.fk]))
        self.assertEqual([d.read_bytes() for _,d in sources],[b"new-0",b"new-1",b"new-2"])
        self.assertFalse(recover(self.root,[self.fi,self.fm,self.fk]))
