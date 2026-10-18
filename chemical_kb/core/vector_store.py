"""Consistent FAISS/metadata reader with recoverable update journal."""
import json
from pathlib import Path
import faiss
from core.config import VECTOR_INDEX,VECTOR_METADATA,BASE_DIR
from core.index_transaction import index_lock,recover
class VectorStore:
    def __init__(self,index_path=None,metadata_path=None,keyword_path=None):
        index_path=Path(index_path or VECTOR_INDEX);metadata_path=Path(metadata_path or VECTOR_METADATA)
        keyword_path=Path(keyword_path or BASE_DIR/"data/search/keyword.sqlite")
        with index_lock(index_path.parent):
            recover(index_path.parent,[index_path,metadata_path,keyword_path])
            self.index=faiss.read_index(str(index_path))
            self.metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
            if self.index.ntotal!=len(self.metadata):raise ValueError("FAISS 与元数据数量不一致，停止检索以免引用错位")
    def search(self,vector,top_k=50):
        scores,ids=self.index.search(vector,top_k)
        return [{"score":float(score),"metadata":self.metadata[idx]} for score,idx in zip(scores[0],ids[0]) if 0<=idx<len(self.metadata)]
