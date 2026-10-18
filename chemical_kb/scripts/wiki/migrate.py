"""Non-destructive legacy import. Original files are never overwritten."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from core.wiki.service import WikiService
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",default=str(ROOT/"data/wiki"));p.add_argument("--extra-root")
    p.add_argument("--apply",action="store_true");args=p.parse_args()
    if args.apply:
        service=WikiService(args.root);report=service.import_legacy(args.extra_root)
    else:
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"wiki"
            # Dry-run only small legacy wiki data; no PDF/model/index writes.
            shutil.copytree(args.root,target,ignore=shutil.ignore_patterns("entries","registry.sqlite*","source_stamp.json","wiki_cases.jsonl"))
            report=WikiService(target).import_legacy(args.extra_root)
    print(json.dumps({"applied":args.apply,"imports":report},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
