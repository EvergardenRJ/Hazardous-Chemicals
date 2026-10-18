"""Recoverable index/metadata/keyword commit. Shared lock protects cooperating readers."""
import contextlib
import hashlib
import json
import os
import shutil
from pathlib import Path

@contextlib.contextmanager
def index_lock(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with (directory/".index-update.lock").open("a+b") as f:
        if os.name=="posix":
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX)
        else:
            import msvcrt
            f.seek(0);f.write(b"0");f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        try:yield
        finally:
            if os.name=="posix":fcntl.flock(f,fcntl.LOCK_UN)
            else:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def durable_json(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def recover(directory,allowed_targets):
    directory=Path(directory).resolve();journal=directory/".index-transaction.json"
    if not journal.exists():return False
    obj=json.loads(journal.read_text(encoding="utf-8"))
    allowed={str(Path(p).resolve()) for p in allowed_targets}
    for row in obj["files"]:
        src=Path(row["staged"]).resolve();dst=Path(row["target"]).resolve()
        if str(dst) not in allowed or not src.is_relative_to(directory):
            raise ValueError("Invalid index transaction path")
        if not src.exists() or file_hash(src)!=row["sha256"]:
            raise ValueError("Staged index transaction is incomplete; preserve journal for recovery")
    for row in obj["files"]:
        dst=Path(row["target"]);dst.parent.mkdir(parents=True,exist_ok=True)
        tmp=dst.with_name(dst.name+".committing")
        shutil.copyfile(row["staged"],tmp)
        with tmp.open("r+b") as f:os.fsync(f.fileno())
        os.replace(tmp,dst)
    if os.name=="posix":
        for parent in {Path(r["target"]).parent for r in obj["files"]}:
            fd=os.open(str(parent),os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
    journal.unlink()
    return True

def commit(directory,pairs,fail_after_journal=False):
    directory=Path(directory)
    files=[{"staged":str(Path(src).resolve()),"target":str(Path(dst).resolve()),"sha256":file_hash(src)} for src,dst in pairs]
    durable_json(directory/".index-transaction.json",{"version":1,"files":files})
    if fail_after_journal:raise RuntimeError("injected commit interruption")
    recover(directory,[dst for _,dst in pairs])
