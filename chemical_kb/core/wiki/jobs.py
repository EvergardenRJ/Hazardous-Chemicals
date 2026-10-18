"""Durable job leasing and successful-section checkpoints."""
import json
import os
import time
import uuid
from .gpu_policy import local_gpu_allowed
from pathlib import Path
from .citations import digest
from .repository import now, safe_entity, Conflict, NotFound

TERMINAL={"ready_for_review","failed","cancelled"}
def kg_busy():
    """Do not load another GPU model while the user's corpus extraction is active."""
    proc="/proc"
    if not os.path.isdir(proc):
        return False
    for pid in os.listdir(proc):
        if not pid.isdigit():continue
        try:
            cmd=Path(proc+"/"+pid+"/cmdline").read_bytes().replace(b"\0",b" ")
            if b"scripts/kg/extract_corpus.py" in cmd and b"python" in cmd:
                return True
        except (OSError,PermissionError):pass
    return False

class Jobs:
    def __init__(self,repo):
        self.repo=repo
    def _decode(self,row):
        row=dict(row)
        row["spec"]=json.loads(row["spec"]);row["checkpoint"]=json.loads(row["checkpoint"])
        row["progress"]={"completed":len(row["checkpoint"].get("sections",{})),
                         "total":len(row["spec"].get("sections",[]))}
        row["block_reason"]="关系抽取正在使用 GPU，Wiki 任务已保存并等待资源" if row["state"]=="queued" and kg_busy() else None
        if row["state"]=="queued" and not local_gpu_allowed():row["block_reason"]="本地 GPU 已由环境变量关闭；可使用资料摘录或外部模型"
        return row
    def create(self,entity,spec):
        entity=safe_entity(entity)
        spec=dict(spec);spec["entity"]=entity
        if spec.get("mode") not in (None,"create","refresh","replace_page"):raise ValueError("无效生成模式")
        try:base=self.repo.entry(entity)["draft_revision"]
        except NotFound:base=None
        expected=spec.get("base_revision",base)
        if expected!=base:raise Conflict("创建任务前 Wiki 已更新")
        spec["base_revision"]=base
        key=str(spec.get("idempotency_key") or digest([entity,base,spec]))
        job="job-"+uuid.uuid4().hex
        with self.repo.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous=db.execute("SELECT * FROM jobs WHERE dedup_key=?",(key,)).fetchone()
            if previous:return self._decode(previous)
            db.execute("INSERT INTO jobs(job_id,entity,dedup_key,spec,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                       (job,entity,key,json.dumps(spec,ensure_ascii=False),"queued",now(),now()))
        return self.get(job)
    def get(self,job):
        with self.repo.connect() as db:row=db.execute("SELECT * FROM jobs WHERE job_id=?",(job,)).fetchone()
        if not row:raise NotFound("任务不存在")
        return self._decode(row)
    def list(self,limit=30):
        with self.repo.connect() as db:
            return [self._decode(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",(limit,))]
    def claim(self,owner,seconds=600):
        with self.repo.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A cancelled expired job must not remain permanently active.
            db.execute("UPDATE jobs SET state='cancelled' WHERE cancel_requested=1 AND lease_until<? AND state NOT IN ('ready_for_review','failed','cancelled')",(time.time(),))
            row=db.execute("SELECT * FROM jobs WHERE cancel_requested=0 AND (state='queued' OR (state IN ('analyzing','generating','validating') AND lease_until<?)) ORDER BY created_at LIMIT 1",(time.time(),)).fetchone()
            if not row:return None
            db.execute("UPDATE jobs SET state='analyzing',lease_owner=?,lease_until=?,updated_at=? WHERE job_id=?",
                       (owner,time.time()+seconds,now(),row["job_id"]))
        return self.get(row["job_id"])
    def checkpoint(self,job,owner,value,state="generating",seconds=600):
        with self.repo.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM jobs WHERE job_id=?",(job,)).fetchone()
            if not row or row["lease_owner"]!=owner or row["lease_until"]<time.time():
                raise Conflict("任务租约已失效")
            if row["cancel_requested"]:raise InterruptedError("任务已取消")
            db.execute("UPDATE jobs SET checkpoint=?,state=?,lease_until=?,updated_at=? WHERE job_id=?",
                       (json.dumps(value,ensure_ascii=False),state,time.time()+seconds,now(),job))
    def finish(self,job,owner,state,revision=None,error=None):
        with self.repo.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM jobs WHERE job_id=?",(job,)).fetchone()
            if not row or row["lease_owner"]!=owner:raise Conflict("任务租约已改变")
            if row["cancel_requested"]:state="cancelled"
            db.execute("UPDATE jobs SET state=?,error=?,result_revision=?,lease_until=0,updated_at=? WHERE job_id=?",
                       (state,error,revision,now(),job))
    def cancel(self,job):
        with self.repo.connect() as db:
            db.execute("UPDATE jobs SET cancel_requested=1,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,updated_at=? WHERE job_id=? AND state NOT IN ('ready_for_review','failed','cancelled')",(now(),job))
        return self.get(job)
    def retry(self,job):
        with self.repo.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM jobs WHERE job_id=?",(job,)).fetchone()
            if not row:raise NotFound("任务不存在")
            if row["state"] not in ("failed","cancelled"):raise ValueError("只能恢复失败或取消任务")
            spec=json.loads(row["spec"])
            try:base=self.repo.entry(row["entity"],db)["draft_revision"]
            except NotFound:base=None
            if base!=spec.get("base_revision"):raise Conflict("基础版本已改变，请创建新任务")
            db.execute("UPDATE jobs SET state='queued',cancel_requested=0,error=NULL,lease_owner=NULL,lease_until=0,updated_at=? WHERE job_id=?",(now(),job))
        return self.get(job)
