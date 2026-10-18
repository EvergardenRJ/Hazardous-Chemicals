"""Verify each migrated marker against its original section-local source. No source writes."""
import argparse,json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from core.wiki.service import WikiService
from core.wiki.citations import CITATION,evidence_id
p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--output");args=p.parse_args()
service=WikiService(args.root);results=[]
for entity in ("氨","液氯"):
    payload=service.repo.read(entity);table=payload["evidence"];pairs=[]
    for section in payload["sections"]:
        before=CITATION.findall(section.get("original_content",""))
        after=CITATION.findall(section["content"]);local=section.get("evidence",[])
        if len(before)!=len(after):raise AssertionError("citation count changed")
        for old,new in zip(before,after):
            expected=evidence_id(local[int(old)-1]) if 0<int(old)<=len(local) else None
            actual=table[int(new)-1]["evidence_id"] if 0<int(new)<=len(table) else None
            pairs.append({"section":section["section"],"old_local":int(old),"new_global":int(new),
                "expected_id":expected,"actual_id":actual,"aligned":bool(expected and actual==expected)})
    results.append({"entity":entity,"references":len(pairs),"aligned":sum(x["aligned"] for x in pairs),"unknown":sum(not x["aligned"] for x in pairs),"pairs":pairs})
report={"method":"section-local evidence identity -> immutable revision global evidence identity","results":results}
if args.output:Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps([{k:v for k,v in r.items() if k!="pairs"} for r in results],ensure_ascii=False))
assert all(r["unknown"]==0 for r in results)
