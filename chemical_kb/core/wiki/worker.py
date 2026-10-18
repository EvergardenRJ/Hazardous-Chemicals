"""Separate inference worker; corpus extraction is never interrupted."""
import argparse
import json
import os
import threading
import time
import uuid
from .gpu_policy import local_gpu_allowed
from pathlib import Path
from .citations import SECTIONS, digest
from .generation import Generator
from .jobs import Jobs, kg_busy
from .repository import Conflict
from .service import WikiService

class Worker:
    def __init__(self,service,rag_factory=None,resource_check=kg_busy):
        self.service=service;self.jobs=Jobs(service.repo)
        self.rag_factory=rag_factory;self.resource_check=resource_check;self.generator=None
        self.owner="worker-"+uuid.uuid4().hex

    def load(self):
        if self.generator is None and not self.rag_factory and not local_gpu_allowed():
            raise RuntimeError("本地 GPU 已由环境变量关闭，请启用后运行生成任务")
        if self.generator is None:
            if self.rag_factory:
                rag=self.rag_factory()
            else:
                from core.rag import RAGSystem
                rag=RAGSystem()
            self.generator=Generator(rag)
            # SQLite review events are authoritative; the JSONL case export can be rebuilt.
            with self.service.repo.connect() as db:
                self.generator.cases=[{**json.loads(row[0]),"case_type":"success" if json.loads(row[0]).get("review_status")=="approved" else "failure"}
                    for row in db.execute("SELECT record FROM review_events WHERE decision IN ('approved','modified','rejected') ORDER BY rowid DESC LIMIT 100")]
            self.generator.cases.reverse()
        return self.generator

    def once(self):
        if self.generator is None and not self.rag_factory and not local_gpu_allowed():return False
        if self.resource_check():return False
        job=self.jobs.claim(self.owner)
        if not job:return False
        try:
            checkpoint=job["checkpoint"]
            metadata=Path(os.environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))/"data/vector_store/index_metadata.json"
            source_stamp=digest([metadata.stat().st_mtime_ns,metadata.stat().st_size]) if metadata.exists() else "unavailable"
            if checkpoint.get("source_stamp") and checkpoint["source_stamp"]!=source_stamp:
                checkpoint={"source_change_reset":True}
            checkpoint["source_stamp"]=source_stamp
            checkpoint.setdefault("sections",{});checkpoint.setdefault("plans",{})
            spec=job["spec"]
            generator=self.load()
            for title in spec["sections"]:
                if title in checkpoint["sections"] and checkpoint["sections"][title].get("_validated"):
                    continue
                if self.resource_check():
                    # Save progress and release the lease without touching model/extraction processes.
                    self.jobs.checkpoint(job["job_id"],self.owner,checkpoint,state="queued",seconds=0)
                    return True
                self.jobs.checkpoint(job["job_id"],self.owner,checkpoint)
                stop=threading.Event()
                heartbeat_error=[]
                def heartbeat():
                    while not stop.wait(15):
                        try:self.jobs.checkpoint(job["job_id"],self.owner,checkpoint)
                        except Exception as exc:
                            heartbeat_error.append(exc);return
                thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
                try:
                    def plan_ready(plan):
                        checkpoint["plans"][title]=plan
                        self.jobs.checkpoint(job["job_id"],self.owner,checkpoint)
                    result=generator.generate_section(spec["entity"],title,plan_ready)
                finally:
                    stop.set();thread.join(timeout=2)
                if heartbeat_error:raise heartbeat_error[0]
                checkpoint["sections"][title]=result
                self.jobs.checkpoint(job["job_id"],self.owner,checkpoint)
            self.jobs.checkpoint(job["job_id"],self.owner,checkpoint,state="validating")
            sections=[];fallback=None
            if spec.get("base_revision"):
                base=self.service.repo.read(spec["entity"],spec["base_revision"])
                sections=list(base["sections"]);fallback=base["evidence"]
                if spec.get("mode")=="replace_page":
                    reviews=self.service.repo.reviews(base["revision_id"])
                    sections=[s for s in sections if reviews.get(s["section"],{}).get("review_status")=="modified"]
            # Existing sections remain unchanged during a requested partial refresh.
            generated=list(checkpoint["sections"].values())
            requested=set(spec["sections"])
            protected={s["section"] for s in sections} if spec.get("mode")=="replace_page" else set()
            sections=[s for s in sections if s["section"] not in requested or s["section"] in protected]+[s for s in generated if s["section"] not in protected]
            order={s:i for i,s in enumerate(SECTIONS)}
            sections.sort(key=lambda s:order.get(s["section"],len(order)))
            if any(s.get("_validated") is False for s in generated):
                self.jobs.finish(job["job_id"],self.owner,"failed",error="部分章节证据不足或校验失败，已保存断点；可补充资料后重试")
                return True
            if metadata.exists() and digest([metadata.stat().st_mtime_ns,metadata.stat().st_size])!=source_stamp:
                raise Conflict("生成期间来源索引改变，需重试并重新检索证据")
            p=self.service.create_draft(spec["entity"],sections,fallback=fallback,expected=spec.get("base_revision"),reason="job",
                                        extra={"evidence_plans":checkpoint["plans"],"job_id":job["job_id"],"worker_owner":self.owner,"policy_version":generator.policy})
            self.jobs.finish(job["job_id"],self.owner,"ready_for_review",revision=p["revision_id"])
        except InterruptedError:
            self.jobs.finish(job["job_id"],self.owner,"cancelled")
        except Exception as exc:
            self.jobs.finish(job["job_id"],self.owner,"failed",error=f"{type(exc).__name__}: {exc}")
        return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root");parser.add_argument("--once",action="store_true")
    args=parser.parse_args();service=WikiService(args.root);worker=Worker(service)
    print(json.dumps({"worker":"wiki-v2","root":str(service.repo.root),"gpu_policy":"wait_for_corpus"},ensure_ascii=False),flush=True)
    while True:
        worker.once()
        if args.once:return
        try:
            with service.repo.connect() as db:pending=db.execute("SELECT COUNT(*) FROM outbox WHERE done=0").fetchone()[0]
            if pending:service.rebuild_projection()
            metadata=Path(os.environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))/"data/vector_store/index_metadata.json"
            service.refresh_sources(metadata)
        except Exception as exc:print("maintenance:",str(exc),flush=True)
        time.sleep(10)

if __name__=="__main__":main()
