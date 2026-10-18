"""SQLite authority + immutable revision files. No inference/graph writes."""
import contextlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .citations import digest, render, validate_revision

def now():
    return datetime.now(timezone.utc).isoformat()

class Conflict(Exception):
    pass

class NotFound(Exception):
    pass

def safe_entity(value):
    value = str(value or "").strip()
    if not value or len(value) > 100 or value in (".", "..") or any(c in value for c in "/\\\x00") or any(ord(c) < 32 for c in value):
        raise ValueError("无效的 Wiki 名称")
    return value

class Repository:
    def __init__(self, root=None):
        if root is None:
            root = os.environ.get("CHEM_KB_WIKI_DIR") or str(Path(os.environ.get("CHEM_KB_BASE_DIR", "/root/autodl-tmp/chemical_kb")) / "data/wiki")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "registry.sqlite"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS entries(
                wiki_id TEXT PRIMARY KEY, entity TEXT UNIQUE NOT NULL,
                draft_revision TEXT, published_revision TEXT, freshness TEXT DEFAULT 'fresh', updated_at TEXT);
            CREATE TABLE IF NOT EXISTS revisions(
                revision_id TEXT PRIMARY KEY, wiki_id TEXT NOT NULL, base_revision TEXT, created_at TEXT,
                reason TEXT, manifest_hash TEXT, freshness TEXT DEFAULT 'fresh', FOREIGN KEY(wiki_id) REFERENCES entries(wiki_id));
            CREATE TABLE IF NOT EXISTS review_events(
                event_id TEXT PRIMARY KEY, wiki_id TEXT, revision_id TEXT, section_id TEXT, content_hash TEXT,
                decision TEXT, reviewer TEXT, reviewed_at TEXT, record TEXT);
            CREATE INDEX IF NOT EXISTS review_lookup ON review_events(revision_id,section_id);
            CREATE TABLE IF NOT EXISTS audit_events(
                event_id TEXT PRIMARY KEY, wiki_id TEXT, revision_id TEXT, action TEXT, actor TEXT, created_at TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS outbox(
                event_id TEXT PRIMARY KEY, wiki_id TEXT, revision_id TEXT, kind TEXT, done INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS jobs(
                job_id TEXT PRIMARY KEY, entity TEXT, dedup_key TEXT UNIQUE, spec TEXT, state TEXT,
                created_at TEXT, updated_at TEXT, lease_owner TEXT, lease_until REAL DEFAULT 0,
                cancel_requested INTEGER DEFAULT 0, checkpoint TEXT DEFAULT '{}', error TEXT, result_revision TEXT);
            CREATE TABLE IF NOT EXISTS source_events(
                event_id TEXT PRIMARY KEY, created_at TEXT, detail TEXT);
            """)
            if "summary" not in {r[1] for r in db.execute("PRAGMA table_info(entries)")}:db.execute("ALTER TABLE entries ADD COLUMN summary TEXT")
            columns={r[1] for r in db.execute("PRAGMA table_info(revisions)")}
            if "freshness" not in columns:
                db.execute("ALTER TABLE revisions ADD COLUMN freshness TEXT DEFAULT 'fresh'")
    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.db), timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=20000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def entry(self, entity, db=None):
        entity = safe_entity(entity)
        if db is not None:
            row = db.execute("SELECT * FROM entries WHERE entity=?", (entity,)).fetchone()
        else:
            with self.connect() as c:
                row = c.execute("SELECT * FROM entries WHERE entity=?", (entity,)).fetchone()
        if not row:
            raise NotFound(entity)
        return dict(row)

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM entries ORDER BY entity")]

    def read(self, entity, revision=None):
        entry = self.entry(entity)
        revision = revision or entry["draft_revision"]
        if not revision:
            raise NotFound("没有已发布版本")
        with self.connect() as db:
            row = db.execute("SELECT * FROM revisions WHERE revision_id=? AND wiki_id=?", (revision, entry["wiki_id"])).fetchone()
        if row is None:
            raise NotFound("版本不存在")
        path = self.root / "entries" / entry["wiki_id"] / "revisions" / revision
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        payload = json.loads((path / "payload.json").read_text(encoding="utf-8"))
        if digest(payload) != manifest["payload_hash"] or digest(manifest) != row["manifest_hash"]:
            raise ValueError("Wiki 版本校验失败")
        return payload

    def commit(self, entity, payload, expected=None, reason="draft", inherited=None):
        entity = safe_entity(entity)
        wiki_id = "wiki-" + digest(entity)[:24]
        rev = "rev-" + uuid.uuid4().hex
        path = self.root / "entries" / wiki_id / "revisions"
        path.mkdir(parents=True, exist_ok=True)
        stage = path / (".staging-" + rev)
        stage.mkdir()
        payload = json.loads(json.dumps(payload, ensure_ascii=False))
        payload.update(entity=entity, wiki_id=wiki_id, revision_id=rev, created_at=now(), base_revision=expected)
        payload["markdown"] = render(entity, payload.get("sections", []))
        try:
            for name, value in [("payload.json", payload), ("sections.json", payload.get("sections", [])), ("evidence.json", payload.get("evidence", []))]:
                with (stage / name).open("w", encoding="utf-8") as f:
                    json.dump(value, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
            with (stage / "wiki.md").open("w", encoding="utf-8") as f:
                f.write(payload["markdown"]); f.flush(); os.fsync(f.fileno())
            manifest = {"schema_version": 2, "revision_id": rev, "payload_hash": digest(payload)}
            with (stage / "manifest.json").open("w",encoding="utf-8") as f:
                json.dump(manifest,f);f.flush();os.fsync(f.fileno())
            os.replace(stage, path / rev)
            if os.name=="posix":
                fd=os.open(str(path),os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT OR IGNORE INTO entries(wiki_id,entity,updated_at) VALUES(?,?,?)", (wiki_id, entity, now()))
                entry = self.entry(entity, db)
                if entry["draft_revision"] != expected:
                    raise Conflict("内容已更新，请重新打开当前版本")
                if payload.get("job_id"):
                    job=db.execute("SELECT * FROM jobs WHERE job_id=?",(payload["job_id"],)).fetchone()
                    import time
                    if not job or job["lease_owner"] != payload.get("worker_owner") or job["lease_until"] < time.time():
                        raise Conflict("提交草稿前任务租约已失效")
                    if job["cancel_requested"]:
                        raise InterruptedError("任务已取消，未提交草稿")
                db.execute("INSERT INTO revisions(revision_id,wiki_id,base_revision,created_at,reason,manifest_hash) VALUES(?,?,?,?,?,?)", (rev,wiki_id,expected,now(),reason,digest(manifest)))
                db.execute("UPDATE entries SET draft_revision=?,updated_at=?,freshness=? WHERE wiki_id=?", (rev,now(),entry["freshness"] if entry["published_revision"] else "fresh",wiki_id))
                if payload.get("job_id"):
                    db.execute("UPDATE jobs SET state='ready_for_review',result_revision=?,lease_until=0,updated_at=? WHERE job_id=?",(rev,now(),payload["job_id"]))
                summary={"page_type":payload.get("page_type","chemical"),"section_count":len(payload.get("sections",[])),"validation_ok":validate_revision(payload)["ok"]}
                db.execute("UPDATE entries SET summary=? WHERE wiki_id=?",(json.dumps(summary),wiki_id))
                if inherited:
                    for record in inherited.values():
                        record = dict(record)
                        section = next((s for s in payload["sections"] if s["section_id"] == record.get("section_id")), None)
                        if section and section["content_hash"] == record.get("content_hash"):
                            record["inherited_from"] = record.get("revision_id")
                            record["revision_id"] = rev
                            self.insert_review(db, entry, rev, record)
            return payload
        except BaseException:
            if stage.exists():
                shutil.rmtree(stage)
            # Orphan immutable directory is safe: it is never registered/read.
            raise

    def reviews(self, revision):
        result = {}
        with self.connect() as db:
            for row in db.execute("SELECT record FROM review_events WHERE revision_id=? ORDER BY rowid", (revision,)):
                record = json.loads(row["record"]); result[record["section"]] = record
        return result

    def insert_review(self, db, entry, revision, record):
        record = dict(record)
        record["review_event_id"] = "review-" + uuid.uuid4().hex
        record["revision_id"] = revision
        db.execute("INSERT INTO review_events VALUES(?,?,?,?,?,?,?,?,?)", (
            record["review_event_id"], entry["wiki_id"], revision, record["section_id"],record["content_hash"],
            record["review_status"],record.get("reviewer","unknown"),record.get("reviewed_at",now()),
            json.dumps(record,ensure_ascii=False)))
        return record

    def add_review(self, entity, revision, record):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            entry = self.entry(entity, db)
            if entry["draft_revision"] != revision:
                raise Conflict("审核版本已改变，请重新核对")
            return self.insert_review(db,entry,revision,record)

    def history(self, entity):
        entry = self.entry(entity)
        with self.connect() as db:
            revisions = [dict(r) for r in db.execute("SELECT * FROM revisions WHERE wiki_id=? ORDER BY created_at DESC", (entry["wiki_id"],))]
            events = [dict(r) for r in db.execute("SELECT action,actor,created_at,revision_id,detail FROM audit_events WHERE wiki_id=? ORDER BY rowid DESC", (entry["wiki_id"],))]
        return {"revisions": revisions, "events": events}

    def activate(self, entity, revision, actor, action="publish", expected=None):
        self.read(entity,revision)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            entry = self.entry(entity,db)
            if action == "publish" and entry["draft_revision"] != expected:
                raise Conflict("发布前内容已更新")
            if action == "publish":
                from .citations import validate_revision
                payload=self.read(entity,revision)
                status=db.execute("SELECT freshness FROM revisions WHERE revision_id=?",(revision,)).fetchone()[0]
                if status != "fresh" or not validate_revision(payload,publication=True)["ok"]:
                    raise ValueError("来源或内容未通过发布校验")
                records={}
                for row in db.execute("SELECT record FROM review_events WHERE revision_id=? ORDER BY rowid",(revision,)):
                    rec=json.loads(row[0]);records[rec["section"]]=rec
                if any(records.get(s["section"],{}).get("review_status") not in ("approved","modified") or records.get(s["section"],{}).get("content_hash") != s["content_hash"] for s in payload["sections"]):
                    raise ValueError("发布前审核状态已变化")
            status=db.execute("SELECT freshness FROM revisions WHERE revision_id=?",(revision,)).fetchone()[0]
            db.execute("UPDATE entries SET published_revision=?,updated_at=?,freshness=? WHERE wiki_id=?", (revision,now(),status,entry["wiki_id"]))
            event = uuid.uuid4().hex
            db.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?)", (event,entry["wiki_id"],revision,action,actor,now(),json.dumps({"previous":entry["published_revision"]})))
            db.execute("INSERT INTO outbox VALUES(?,?,?,?,0)", (event,entry["wiki_id"],revision,"published"))
        return self.entry(entity)
