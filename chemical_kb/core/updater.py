"""Deduplicate before inference; commit FAISS, metadata and FTS as one recoverable generation."""
import json
import uuid
from pathlib import Path
import faiss
import numpy as np
from core.config import VECTOR_INDEX, VECTOR_METADATA, BASE_DIR
from core.knowledge import KeywordIndex
from core.index_transaction import index_lock, recover, commit, durable_json

class KnowledgeUpdater:
    def __init__(self,embedding=None,index_path=None,metadata_path=None,keyword_path=None):
        self.embedding=embedding
        self.index_path=Path(index_path or VECTOR_INDEX)
        self.metadata_path=Path(metadata_path or VECTOR_METADATA)
        self.keyword_path=Path(keyword_path or BASE_DIR/"data/search/keyword.sqlite")

    def update(self,chunks):
        if not chunks:return {"added":0,"updated":0}
        directory=self.index_path.parent
        with index_lock(directory):
            recover(directory,[self.index_path,self.metadata_path,self.keyword_path])
            metadata=json.loads(self.metadata_path.read_text(encoding="utf-8"))
            index=faiss.read_index(str(self.index_path))
            if index.ntotal!=len(metadata):raise ValueError("索引与元数据数量不一致，禁止追加；先隔离修复")
            ids={str(c.get("chunk_id")):i for i,c in enumerate(metadata)}
            if len(ids)!=len(metadata):raise ValueError("现有索引包含重复 chunk_id，禁止追加")
            batch={}
            for c in chunks:
                if not c.get("chunk_id") or not isinstance(c.get("text"),str):raise ValueError("新增片段必须包含 chunk_id 与正文")
                key=str(c["chunk_id"])
                if key in batch and batch[key]!=c:raise ValueError("同一批次 chunk_id 内容冲突")
                batch[key]=c
            changed=[c for key,c in batch.items() if key not in ids or metadata[ids[key]]!=c]
            if not changed:return {"added":0,"updated":0,"count":index.ntotal}
            if self.embedding is None:
                from core.embedding import EmbeddingModel
                self.embedding=EmbeddingModel()
            vectors=np.asarray(self.embedding.model.encode([c["text"] for c in changed],
                normalize_embeddings=True,batch_size=64,show_progress_bar=True),dtype="float32")
            if vectors.ndim!=2 or vectors.shape!=(len(changed),index.d):raise ValueError("Embedding shape mismatch")
            replacements={str(c["chunk_id"]):v for c,v in zip(changed,vectors) if str(c["chunk_id"]) in ids}
            added=[(c,v) for c,v in zip(changed,vectors) if str(c["chunk_id"]) not in ids]
            if replacements:
                # Current corpus uses an exact Flat index; preserve metric and positions on replacement.
                if not isinstance(index,(faiss.IndexFlatIP,faiss.IndexFlatL2)):
                    raise ValueError("此索引类型需使用专用版本重建，未修改原索引")
                existing=index.reconstruct_n(0,index.ntotal)
                for key,vector in replacements.items():existing[ids[key]]=vector;metadata[ids[key]]=batch[key]
                rebuilt=faiss.IndexFlatIP(index.d) if index.metric_type==faiss.METRIC_INNER_PRODUCT else faiss.IndexFlatL2(index.d)
                rebuilt.add(np.asarray(existing,dtype="float32"));index=rebuilt
            if added:
                index.add(np.asarray([v for _,v in added],dtype="float32"));metadata.extend(c for c,_ in added)
            if index.ntotal!=len(metadata):raise ValueError("Staged index count mismatch")
            stage=directory/(".generation-"+uuid.uuid4().hex);stage.mkdir()
            fi=stage/"faiss.index";fm=stage/"metadata.json";fk=stage/"keyword.sqlite"
            faiss.write_index(index,str(fi));durable_json(fm,metadata);KeywordIndex(fk).build(metadata)
            # Original files are retained on the server for independent rollback.
            backup=stage/"previous";backup.mkdir()
            import shutil
            for name,p in (("faiss.index",self.index_path),("metadata.json",self.metadata_path),("keyword.sqlite",self.keyword_path)):
                if p.exists():shutil.copy2(p,backup/name)
            commit(directory,[(fi,self.index_path),(fm,self.metadata_path),(fk,self.keyword_path)])
            durable_json(stage/"source_event.json",{"added":[c["chunk_id"] for c,_ in added],
                "updated":list(replacements),"generation":stage.name,"count":index.ntotal})
            return {"added":len(added),"updated":len(replacements),"count":index.ntotal,"generation":stage.name}
