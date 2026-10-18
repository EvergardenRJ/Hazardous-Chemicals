"""Create 10 drafts and enrich current Wiki drafts with attributed encyclopedias."""
import argparse,copy,hashlib,json,os,re,sqlite3,sys,tempfile,unicodedata
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(os.environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE));sys.path.insert(0,os.environ.get("CHEM_KB_WIKI_CODE_ROOT",str(BASE)))
from core.wiki.service import WikiService
from core.wiki.citations import SECTIONS,bind_sections,display_source_text,digest,evidence_id,validate_revision
from core.wiki.repository import NotFound
sys.path.insert(0,str(HERE))
import add_chemical_showcase_20 as author
CFG=json.loads((HERE/"chemical_showcase_10_20261002.json").read_text(encoding="utf-8"))
SOURCE=json.loads((HERE/"encyclopedia_sources_20261002.json").read_text(encoding="utf-8"))
ABSTRACT=json.loads((HERE/"encyclopedia_abstracts_20261002.json").read_text(encoding="utf-8"))
BATCH=CFG["batch"]
NEW=[dict(zip(CFG["fields"],row)) for row in CFG["chemicals"]]
author.MODEL_SOURCE=CFG["source"]
author.EXCLUDES.update({
"硝酸":["硝酸盐","硝酸钠","硝酸钾","硝酸铵","硝酸银","硝酸锂","硝酸铅","硝酸钙","硝酸镁","硝酸铜","硝酸锌","硝酸亚","硝酸铁","硝酸酯"],
"乙酸":["乙酸乙","乙酸甲","乙酸丙","乙酸丁","乙酸酯","乙酸钠","乙酸钾","乙酸铵","乙酸酐","乙酸盐","氯乙酸","溴乙酸","三氟乙酸","过氧乙酸","乙酰乙酸","羟基乙酸","乙酸铜"],
"乙酸乙酯":["乙酰乙酸乙酯"],
"氯乙烯":["聚氯乙烯","氯乙烯树脂","二氯乙烯","三氯乙烯","四氯乙烯","偏氯乙烯"],
"环氧乙烷":["甲基环氧乙烷"],
"丙烷":["环丙烷","氯丙烷","溴丙烷","氟丙烷","硝基丙烷","环氧丙烷","二氯丙烷","三氯丙烷"],
"丁烷":["环丁烷","氯丁烷","溴丁烷","氟丁烷"],
"硫化钠":["多硫化钠","硫化钠盐"]})
PACK={}
for i,row in enumerate(SOURCE["sources"]):
    sources=[]
    for key,abstract in (("wikipedia",ABSTRACT["wikipedia"][i]),("baidu",ABSTRACT["baidu"][i])):
        raw=row.get(key)
        if not raw:continue
        src={k:v for k,v in raw.items() if k not in ("original_intro",)}
        src.update(summary=abstract,summary_method="人工整理的百科要点",
                   source_text_hash=raw.get("original_intro_hash") or digest(raw.get("original_intro","")),
                   external_source_id="ext-"+digest([raw["source_name"],raw["url"],raw.get("revision"),abstract])[:24])
        if src["content_status"]!="fetched":src["summary"]=""
        sources.append(src)
    PACK[row["entity"]]={"external_sources":sources,"illustration":row.get("image"),
                         "source_home_links":[{"name":"Wikipedia","url":"https://gpe.wikipedia.org/"},{"name":"百度百科","url":"https://baike.baidu.com/"}]}
EXTERNAL_CASES={
"氢氟酸":[{"source_name":"CSB","title":"PES 炼油厂火灾与爆炸调查（2019）",
"url":"https://www.csb.gov/philadelphia-energy-solutions-pes-refinery-fire-and-explosions-/",
"reason":"阅读氟化氢相关装置的腐蚀、隔离与安全关键设施问题；报告工况与本页水溶液产品须区分。",
"relation_type":"相关介质与工况","retrieved_at":"2026-10-02"}],
"丙烷":[{"source_name":"CSB","title":"PES 炼油厂火灾与爆炸调查（2019）",
"url":"https://www.csb.gov/philadelphia-energy-solutions-pes-refinery-fire-and-explosions-/",
"reason":"可结合报告阅读烃类释放、可燃云和远程隔离。事故介质为工艺混合物，不能当作纯丙烷试验。",
"relation_type":"混合物释放场景","retrieved_at":"2026-10-02"},
{"source_name":"CSB","title":"Williams Olefins 工厂爆炸与火灾调查（2013）",
"url":"https://www.csb.gov/williams-olefins-plant-explosion-and-fire-/",
"reason":"建议核对换热设备的隔离、压力保护和变更管理，并阅读全文确认实际介质。",
"relation_type":"设备与压力保护","retrieved_at":"2026-10-02"}],
"氯乙烯":[{"source_name":"NTSB","title":"East Palestine 脱轨与危险品释放调查（2023）",
"url":"https://www.ntsb.gov/investigations/Pages/RRD23MR005.aspx",
"reason":"阅读脱轨后氯乙烯罐车及应急决策的调查；列车起因、危险品释放与处置决定需分别理解。",
"relation_type":"直接涉及单体运输","retrieved_at":"2026-10-02"}]}
def cleaned_sections(payload):
    table=copy.deepcopy(payload["evidence"])
    sections=copy.deepcopy(payload["sections"])
    for s in sections:
        s["content"]=display_source_text(s["content"])
        s.pop("original_content",None);s.pop("original_knowledge_blocks",None)
        for b in s.get("knowledge_blocks",[]):b["text"]=display_source_text(b.get("text"))
        s["citation_scope"]="global";s["evidence"]=table
    return sections,table
def cases(name,rows):
    hits=[]
    for row in rows:
        typ=str(row.get("document_type",""))+str(row.get("source",""))+str(row.get("title",""))
        if not any(w in typ for w in ("事故","调查")):continue
        if not row.get("chunk_id") or not row.get("doc_id"):continue
        q=author.quote_for(name,row)
        if not q:continue
        score=5*bool(author.valid_positions(name,str(row.get("title",""))))+sum(w in q for w in ("事故","泄漏","爆炸","中毒","原因","死亡"))
        hits.append((score,row,q))
    hits.sort(key=lambda x:(-x[0],str(x[1]["chunk_id"])))
    selected=[];seen=set()
    for _,row,q in hits:
        if row["doc_id"] in seen:continue
        seen.add(row["doc_id"]);selected.append((row,q))
        if len(selected)>=2:break
    return selected
PROFILE={p["name"]:{k:p[k] for k in ("formula","english","class","scope")} for p in author.PROFILES+NEW}
PROFILE.update({"氨":{"formula":"NH₃","english":"Ammonia","scope":"气态氨与液氨分别确认"},
                "液氯":{"formula":"Cl₂","english":"Chlorine","scope":"液化氯储运与氯气暴露分别确认"},
                "天然气":{"formula":"混合物","english":"Natural gas","scope":"组成、来源及气态或液化产品分别确认"}})
def norm(value):return re.sub(r"[^\w]","",unicodedata.normalize("NFKC",str(value)).casefold())
PDF_NAMES={}
for path in (BASE/"data/pdf").rglob("*.pdf"):PDF_NAMES.setdefault(norm(path.stem),[]).append(path)
def has_pdf(row):return any(len(PDF_NAMES.get(norm(row.get(key,"")),[]))==1 for key in ("title","doc_id","code"))
def extra_for(name,rows):
    extra=copy.deepcopy(PACK.get(name,{}));extra.update(multisource_batch=BATCH,chemical_profile=PROFILE.get(name,{}),product_scope=PROFILE.get(name,{}).get("scope",""))
    case_rows=cases(name,rows)
    relation="原文提及"
    target=name
    if not case_rows:
        target="硫化氢" if name=="硫化钠" else "乙醇" if name in ("乙酸","乙酸乙酯") else "丙烷" if name=="丁烷" else name
        if target!=name:case_rows=cases(target,rows);relation="相关风险场景"
    reason=("原文片段提及"+name+"，建议核对报告中的实际介质、工况及事故链。" if target==name else
            "报告原文提及"+target+"；用于阅读相关释放或储运风险，不能据此认定事故由"+name+"造成。")
    extra["accident_reading"]=[{"source_name":"本地事故调查报告","title":r["title"],"doc_id":r["doc_id"],
     "chunk_id":r["chunk_id"],"page":r.get("page_start"),"evidence_id":evidence_id({"metadata":r}),
     "reason":reason,"pdf_available":has_pdf(r),
     "relation_type":relation,"excerpt":q} for r,q in case_rows]+EXTERNAL_CASES.get(name,[])
    return extra,[{"metadata":copy.deepcopy(r)} for r,_ in case_rows]
def add_sources(sections,table,extra):
    byid={evidence_id(e) for e in table}
    for item in extra.pop("_case_evidence",[]):
        if evidence_id(item) not in byid:table.append(item);byid.add(evidence_id(item))
    for s in sections:
        s["evidence"]=table;s["citation_scope"]="global"
        if s["section"]!=sections[0]["section"]:continue
        for src in extra.get("external_sources",[]):
            if not src.get("summary"):continue
            content=f"**来源：{src['source_name']}**\n\n{src['summary']}"
            if src.get("scope_note"):content+=" "+src["scope_note"]
            content+=f"\n\n[阅读词条：{src['title']}]({src['url']}) · 获取日期：2026-10-02"
            if src.get("license"):content+=f" · [{src['license']}]({src['license_url']})"
            s["content"]+="\n\n"+content
            s.setdefault("knowledge_blocks",[]).append({"text":content,"knowledge_source":"external",
             "evidence_ids":[],"source_name":src["source_name"],"source_url":src["url"],
             "external_source_id":src["external_source_id"],"retrieved_at":src["retrieved_at"],
             "verification_status":"encyclopedia_summary","license":src.get("license")})
    return sections
def verify_payload(p,rows_by_chunk,is_new=False):
    validation=validate_revision(p)
    if is_new or not p.get("legacy_validation_errors"):
        assert validation["ok"],validation
    else:
        assert set(validation["errors"]).issubset(set(p["legacy_validation_errors"])),validation
    assert "来源：模型背景知识（Codex 当前会话生成，待核实）" not in p["markdown"]
    for e in p["evidence"]:
        if is_new:assert e["metadata"]==rows_by_chunk[e["metadata"]["chunk_id"]]
    for b in (b for s in p["sections"] for b in s.get("knowledge_blocks",[]) if b.get("knowledge_source")=="external"):
        assert not b["evidence_ids"] and not b["evidence_refs"]
        assert b["text"] in next(s["content"] for s in p["sections"] if b in s["knowledge_blocks"])
    for rec in p.get("accident_reading",[]):
        if rec.get("evidence_id"):assert rec["evidence_id"] in {e["evidence_id"] for e in p["evidence"]}
    if is_new:
        assert len(p["sections"])==17
        assert all(len(s["content"])>80 for s in p["sections"])
        assert not validate_revision(p,publication=True)["ok"]
        assert {x["source_name"] for x in p["external_sources"] if x.get("summary")}=={"Wikipedia","百度百科"}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--apply",action="store_true")
    parser.add_argument("--report",type=Path,required=True);args=parser.parse_args()
    rows=json.loads((BASE/"data/vector_store/index_metadata.json").read_text(encoding="utf-8"))
    lookup={r["chunk_id"]:r for r in rows}
    live=WikiService();before={e["entity"]:e for e in live.repo.list()}
    assert len(NEW)==10 and len({p["name"] for p in NEW})==10
    new_names={p["name"] for p in NEW}
    plans=[]
    for name,entry in before.items():
        p=live.repo.read(name)
        if p.get("multisource_batch")==BATCH:continue
        # Keep legacy thematic pages; only model labels or supported primary entries need revisions.
        if name not in PACK and "来源：模型背景知识（Codex 当前会话生成，待核实）" not in p["markdown"]:continue
        sections,table=cleaned_sections(p)
        ex={k:copy.deepcopy(v) for k,v in p.items() if k not in
            {"sections","evidence","binding_errors","markdown","validation","revision_id","wiki_id","entity","created_at","schema_version"}}
        addition,case_evidence=extra_for(name,rows);addition["_case_evidence"]=case_evidence
        baseline=validate_revision(p)
        if not baseline["ok"]:ex["legacy_validation_errors"]=baseline["errors"]
        sections=add_sources(sections,table,addition);ex.update(addition)
        plans.append((name,sections,table,ex,entry["draft_revision"],False))
    for profile in NEW:
        name=profile["name"]
        if name in before:
            assert live.repo.read(name).get("multisource_batch")==BATCH,name
            continue
        raw=author.make_sections(profile,author.choose_evidence(name,rows))
        # Bring generated locals to a coherent global table before adding source and case records.
        bound,table,issues=bind_sections(raw);assert not issues
        payload={"sections":bound,"evidence":table};sections,table=cleaned_sections(payload)
        sections[0]["content"]=sections[0]["content"].replace("（2026-10-01）","（2026-10-02）")
        # Update block text for the corresponding date label as well.
        for b in sections[0]["knowledge_blocks"]:b["text"]=b["text"].replace("（2026-10-01）","（2026-10-02）")
        addition,case_evidence=extra_for(name,rows);addition["_case_evidence"]=case_evidence
        sections=add_sources(sections,table,addition)
        ex={"page_type":"chemical","model_provenance":CFG["source"],"product_scope":profile["scope"],
            "chemical_profile":{k:profile[k] for k in ("formula","english","class","scope")},
            "generation_method":"large_model_knowledge_and_attributed_encyclopedias",**addition}
        plans.append((name,sections,table,ex,None,True))
    report={"batch":BATCH,"before_count":len(before),"mode":"apply" if args.apply else "dry_run",
            "new":10,"existing_revisions_updated":sum(not p[-1] for p in plans),"checks":[]}
    with tempfile.TemporaryDirectory(prefix="wiki_multisource_") as tmp:
        isolated=WikiService(tmp)
        for name,sections,table,extra,expected,new in plans:
            saved=isolated.create_draft(name,sections,table,reason=BATCH,extra=extra)
            verify_payload(saved,lookup,new)
            report["checks"].append({"entity":name,"new":new,"sections":len(saved["sections"]),
             "sources":[s["source_name"] for s in saved.get("external_sources",[]) if s.get("summary")],
             "image":bool(saved.get("illustration")),"accident_recommendations":len(saved.get("accident_reading",[])),
             "validation":validate_revision(saved)["ok"],"legacy_validation_errors":saved.get("legacy_validation_errors",[])})
    if args.apply:
        backup=BASE/"backups"/(BATCH+"_"+datetime.now().strftime("%H%M%S"))
        backup.mkdir(parents=True,exist_ok=False)
        with live.repo.connect() as db:
            with sqlite3.connect(str(backup/"registry.sqlite")) as dest:db.backup(dest)
        (backup/"entries_before.json").write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding="utf-8")
        protected=[BASE/"data/vector_store/faiss.index",BASE/"data/vector_store/index_metadata.json",BASE/"data/knowledge/documents.json"]
        hashes={str(f):author.file_hash(f) for f in protected if f.exists()}
        published={n:e["published_revision"] for n,e in before.items()}
        for name,sections,table,extra,expected,new in plans:
            saved=live.create_draft(name,sections,table,expected=expected,reason=BATCH,extra=extra)
            verify_payload(saved,lookup,new)
        after=live.repo.list()
        assert len(after)==len(before)+sum(p[-1] for p in plans)
        for e in after:
            if e["entity"] in published:assert e["published_revision"]==published[e["entity"]]
        for path,h in hashes.items():assert author.file_hash(Path(path))==h
        for name in new_names:
            detail=live.detail(name)
            assert all(s["review_status"]=="pending" for s in detail["sections"]) and not detail["is_published"]
        report.update(after_count=len(after),backup=str(backup),protected_files_unchanged=True,published_pointers_unchanged=True)
    report["verification"]="passed"
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"mode":report["mode"],"new":sum(p[-1] for p in plans),"updated":report["existing_revisions_updated"],
      "planned_pages":len(plans),"sections_new":sum(len(p[1]) for p in plans if p[-1]),
      "images":sum(c["image"] for c in report["checks"]),"accident_recommendations":sum(c["accident_recommendations"] for c in report["checks"]),
      "after_count":report.get("after_count"),"verification":"passed"},ensure_ascii=False))
if __name__=="__main__":main()
