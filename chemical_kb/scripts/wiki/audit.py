import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core.wiki.service import WikiService
p=argparse.ArgumentParser();p.add_argument("--root",default=str(ROOT/"data/wiki"));args=p.parse_args()
s=WikiService(args.root)
print(json.dumps({"entries":s.list(),"findings":s.lint()},ensure_ascii=False,indent=2))
