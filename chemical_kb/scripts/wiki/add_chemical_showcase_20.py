"""Add 20 provenance-labelled showcase drafts without model/GPU or graph writes."""
import argparse, copy, hashlib, json, os, re, shutil, sqlite3, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(os.environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))
sys.path.insert(0,str(BASE))
from core.wiki.service import WikiService
from core.wiki.citations import SECTIONS, bind_sections, validate_revision, CITATION, digest

HERE=Path(__file__).resolve().parent
DATA=json.loads((HERE/"chemical_showcase_20.json").read_text(encoding="utf-8"))
BATCH=DATA["batch"]
MODEL_SOURCE=DATA["source"]
PROFILES=[dict(zip(DATA["fields"],x)) for x in DATA["chemicals"]]
METADATA=BASE/"data/vector_store/index_metadata.json"

# Identity checks stop title substring matches from binding other chemicals.
EXCLUDES={
"氢气":["硫化氢气","氯化氢气","氟化氢气"],
"氧气":["化学氧气发生器"],
"乙醇":["乙醇胺","乙二醇"],
"苯":["甲苯","二甲苯","三甲苯","四甲苯","乙苯","氯苯","溴苯","氟苯","硝基苯","苯乙烯","苯酚","苯胺","苯甲","苯基","苯醚","苯肼","苯磺","苯二","苯三","苯四","苯环"],
"甲苯":["二甲苯","三甲苯","四甲苯","甲苯二异氰酸","甲苯磺","甲苯胺","甲苯酚","硝基甲苯","氯甲苯"],
"二甲苯":["三甲苯","二甲苯胺","二甲苯酚"],
"丙酮":["丙酮氰醇","丙酮酸","六氟丙酮","丙酮肟"],
"硫酸":["硫酸二甲","硫酸二乙","硫酸氢","硫酸盐","硫酸酯","硫酸钠","硫酸铜","硫酸铵","硫酸镁","硫酸钾","硫酸锌","硫酸亚","硫酸铁","硫酸钡","硫酸铅","硫酸钙","硫酸铝","硫酸镍","硫酸锰","硫酸银"],
"盐酸":["盐酸盐","盐酸羟"],
"乙烯":["聚乙烯","氯乙烯","苯乙烯","乙烯基","乙酸乙烯","乙烯醇","乙烯酮","乙烯醚"],
"丙烯":["聚丙烯","丙烯酸","丙烯腈","丙烯醛","环氧丙烯","丙烯基","丙烯酰"],
}
def valid_positions(name,text):
    masked=text
    for word in sorted(EXCLUDES.get(name,[]),key=len,reverse=True):
        masked=masked.replace(word," " * len(word))
    # Additional short-name compound boundaries.
    pattern=re.escape(name)
    if name=="苯":
        pattern=r"(?<![甲乙丙丁二三四五六氯溴氟碘硝基])苯(?![甲乙丙丁胺酚醚基环磺肼醛硫酰])"
    return [m.start() for m in re.finditer(pattern,masked)]

def quote_for(name,row):
    text=str(row.get("text",""))
    pos=valid_positions(name,text)
    if not pos:return None
    # Exact substring, preserving OCR text; no paraphrases masquerading as quotations.
    center=pos[0]
    boundaries=list(re.finditer(r"[。！？;\n]",text[:center]))
    start=boundaries[-1].end() if boundaries else max(0,center-60)
    if center-start>120:start=max(0,center-60)
    stop=min(len(text),start+260)
    after=re.search(r"[。！？;\n]",text[max(center+len(name),start+100):stop])
    if after:
        stop=max(center+len(name),start+100)+after.end()
    q=text[start:stop].strip()
    if len(q)<45 or not valid_positions(name,q):return None
    if "\ufffd" in q or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]",q):return None
    if CITATION.search(q):return None
    return q

CATEGORY={
"基本概述":["名称","物质","用途","性状","范围"],
"危险特性":["危险","爆炸","燃烧","窒息","中毒","腐蚀","泄漏"],
"储存要求":["储存","贮存","仓库","储罐","容器","气瓶"],
"运输与装卸":["装卸","运输","卸料","软管","槽车"],
"设备设施与自动化控制":["报警","检测","切断","联锁","设备","管道","通风"],
"典型事故经验":["事故","调查","死亡","原因","教训"],
"相关标准法规":["应","禁止","必须","检验","规范","标准"],
}
def choose_evidence(name,rows):
    candidates=[]
    for row in rows:
        if str(row.get("status","")).lower() in {"repealed","withdrawn","inactive","deleted","废止","撤回"}:continue
        if not row.get("chunk_id") or not row.get("doc_id"):continue
        q=quote_for(name,row)
        if q is None:continue
        title=str(row.get("title",""))
        score=4 if valid_positions(name,title) else 0
        score+=min(3,len(valid_positions(name,str(row.get("text","")))))
        score-=2 if row.get("quality") not in (None,"normal","good") else 0
        candidates.append((score,row,q))
    candidates.sort(key=lambda c:(-c[0],str(c[1].get("chunk_id"))))
    used=set(); selected={}
    for section,words in CATEGORY.items():
        eligible=[]
        for score,row,q in candidates:
            if row["chunk_id"] in used:continue
            matches=sum(word in q for word in words)
            if section=="典型事故经验":
                if not any(x in str(row.get("document_type",""))+str(row.get("source",""))+str(row.get("title","")) for x in ["事故","调查"]):continue
                if not matches:continue
            elif section=="相关标准法规":
                if not any(x in str(row.get("document_type",""))+str(row.get("source",""))+str(row.get("title","")) for x in ["标准","法规","规范"]):continue
                if not matches:continue
            elif section!="基本概述" and not matches:continue
            eligible.append((score+matches,row,q))
        if eligible:
            _,row,q=max(eligible,key=lambda c:c[0])
            used.add(row["chunk_id"])
            selected[section]=(row,q)
    return selected

def model_content(p,section):
    name=p["name"];cls=p["class"]
    gas=cls.endswith("gas") or cls in ("co2",)
    transport=("供货可能采用气瓶、管束、槽车或低温容器，须按实际物态确认。" if gas else
               "固体、溶液或混合产品的容器和分类须按实际组分确认。")
    if section=="基本概述":
        return (f"{p['overview']}\n\n物质标识：中文名 {name}；英文名 {p['english']}；化学式 {p['formula']}。"
                f"适用范围：{p['scope']}。\n\n本页由 Codex 当前会话依据模型背景知识编写（2026-10-01），具体模型版本未由环境提供。"
                "本地原文摘录单独绑定证据；每个摘录仅说明原文所述内容，其他段落保留模型补充来源。")
    if section=="理化性质":
        return p["properties"]+" 查询定量物性时应同时记录物态、浓度、温度、压力及测试条件。当前草稿未填入未经核实的闪点、爆炸极限或暴露限值。"
    if section=="危险特性":
        return p["hazard"]+" 场景评估需关联泄漏源、人员位置、环境条件和点火或反应条件，分别识别起始事件与后果，不能仅用危险类别代替设施分析。"
    if section=="健康危害":
        return p["health"]+" 职业暴露管理还需确定接触路径、接触时长及实际产品组成，并由具备资质的人员核实检测与健康管理要求。"
    if section=="生产与使用":
        return p["uses"]+" 使用记录应关联实际 SDS、工艺单元、设备和变更记录；这部分用途概述不提供生产或反应操作参数。"
    if section=="储存要求":
        return p["storage"]+" 需要补证：当前产品 SDS、设施设计文件、检查记录及适用标准版本。具体储量、间距和设定值须经核实后填写。"
    if section=="运输与装卸":
        return (transport+f" 本批草稿的产品边界是：{p['scope']}。交接需核对物料、容器、接口、检验状态和异常处置责任。"
               "具体运输身份、危险货物编号和装卸条件应引用实际产品资料，不凭总称推定。")
    if section=="设备设施与自动化控制":
        return p["equipment"]+" 将检查项目关联设备编号、检测对象、维护周期和责任人，保存功能试验记录；报警阈值与动作条件须来自经核实的设计依据。"
    if section=="个体防护":
        specific=("低温接触、压力介质及气体环境需分别评价，缺氧或浓度未知场景的救援须具备专业呼吸防护能力。" if gas else
                  "需分别评价飞溅、皮肤接触和蒸气、粉尘或雾滴；手套、服装及呼吸用品应有实际产品适用性依据。")
        return specific+f" {p['health']} 个体用品选择还需记录适用范围和使用条件，并与密闭、通风及其他工程控制共同评估。"
    if section=="泄漏应急":
        return (p["special"]+" 预案需明确报警、人员避险、专业检测、远程隔离和现场处置职责。普通人员不得进入未知危险环境处置。"
               "本段是待核实的知识框架，具体警戒距离、处置介质和恢复条件须按产品 SDS 与现场预案确认。")
    if section=="火灾/爆炸处置":
        return p["hazard"]+" "+p["special"]+" 消防决策需考虑持续泄漏、受热容器、邻近物料和烟气；具体灭火介质、操作顺序与设备保护方式由核实的预案确定。"
    if section=="急救":
        return (p["health"]+f" 向医疗人员提供 {name} 的产品资料、接触途径、时长及现场监测信息，并启动现场医疗响应。"
               "救援人员需先确认环境和防护能力，避免连续伤亡。具体急救步骤和治疗属于待补证内容，本页不提供药物剂量或自行治疗方案。")
    if section=="典型事故经验":
        return p["lessons"]+" 本段是模型归纳的复盘问题，未把它表述为某起已核实事故。下方如有调查报告摘录，事故事实仅限其原文；完整时间线、伤亡和原因还需阅读全文核实。"
    if section=="常见事故原因":
        return p["prevention"]+" 这些是需要验证的原因候选，不能直接视为已发生事故的调查结论。验证应关联现场状态、检维修、检测和交接记录。"
    if section=="防范与整改措施":
        return p["equipment"]+" "+p["prevention"]+" 整改建议应进一步转为责任人、对象、完成依据和复验记录；是否适用须结合具体设施确认。"
    if section=="相关标准法规":
        return (f"对 {name} 应检索实际产品 SDS，并按 {p['scope']} 确认适用范围。重点核对危险化学品管理、储运、职业接触和相应设施标准的适用性。"
               "本地摘录显示的是文档原始登记与文本，未完成主管部门现行有效性核验，不据此宣布所有条款现行或适用于该设施。"
               "本页未编造标准编号、法定限值或条款号；后续补证需记录版本、有效日期、地域、对象和适用条件。")
    if section=="知识总结":
        return (f"{name} 的阅读主线：{p['hazard']} 优先核对：{p['scope']}；随后查看设施控制、人员暴露及应急依据。"
               "本页与本地资料共同构成待审核知识入口。模型补充可以用于导航和提出核实问题，转为正式发布前仍需核实高风险章节的证据和专家审核。")
    raise ValueError(section)

def make_sections(p,selected):
    result=[]
    for title in SECTIONS:
        body="**来源：模型背景知识（Codex 当前会话生成，待核实）**\n\n"+model_content(p,title)
        if title=="基本概述" and p.get("url"):
            body+=f"\n\n基础危害核对入口：[官方参考页面]({p['url']})。该入口供后续核对使用；本页模型段落仍按模型补充登记。"
        blocks=[{"text":body,"knowledge_source":"model_prior","evidence_ids":[],
                 "model_source":copy.deepcopy(MODEL_SOURCE),"verification_status":"needs_review",
                 "reference_urls":[p["url"]] if p.get("url") else []}]
        evidence=[]
        if title in selected:
            row,q=selected[title]
            prefix=("**本地调查报告摘录（事故事实仅限原文片段）**" if title=="典型事故经验" else
                    "**本地文档原文摘录（仅支持本片段，登记信息待核实）**")
            quote=prefix+"\n\n"+q+"\n\n[Wiki证据1]"
            body+="\n\n"+quote
            blocks.append({"text":quote,"knowledge_source":"grounded","evidence_ids":[1],
                           "verification_status":"original_excerpt_not_expert_review",
                           "quote_text":q,"scope":"原文逐字摘录；不作为上方模型段落的自动事实背书"})
            evidence=[{"metadata":copy.deepcopy(row)}]
        result.append({"section":title,"content":body,"knowledge_blocks":blocks,
                       "evidence":evidence,"_validated":True,"status":"draft"})
    return result

def verify(payload,p,rows_by_chunk):
    assert [s["section"] for s in payload["sections"]]==SECTIONS
    val=validate_revision(payload);assert val["ok"],val
    assert not validate_revision(payload,publication=True)["ok"],"High-risk publication gate must remain active"
    assert len(payload["sections"])==17
    for s in payload["sections"]:
        assert len(s["content"])>80, (p["name"],s["section"],len(s["content"]))
        assert any(b["knowledge_source"]=="model_prior" for b in s["knowledge_blocks"])
        for b in s["knowledge_blocks"]:
            if b["knowledge_source"]=="model_prior":
                assert not b["evidence_ids"] and not b["evidence_refs"]
                assert b["model_source"]["provider"]=="Codex"
            if b["knowledge_source"]=="grounded":
                assert b["quote_text"] in s["content"]
                for n in b["evidence_ids"]:
                    m=payload["evidence"][n-1]["metadata"]
                    assert m==rows_by_chunk[m["chunk_id"]]
                    assert b["quote_text"] in m["text"]
                    assert valid_positions(p["name"],b["quote_text"])
    assert len(payload["evidence"])>=2, f"{p['name']}: insufficient local references"

def snapshot(service):
    state={}
    for e in service.repo.list():
        p=service.repo.read(e["entity"])
        state[e["entity"]]={"entry":e,"payload_hash":digest(p),
                           "reviews_hash":digest(service.repo.reviews(p["revision_id"]))}
    return state

def file_hash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    rows=json.loads(METADATA.read_text(encoding="utf-8"))
    lookup={r["chunk_id"]:r for r in rows}
    assert len(PROFILES)==20 and len({p["name"] for p in PROFILES})==20
    plans=[]
    for p in PROFILES:
        sections=make_sections(p,choose_evidence(p["name"],rows))
        bound,evidence,errors=bind_sections(sections)
        payload={"sections":bound,"evidence":evidence,"binding_errors":errors}
        verify(payload,p,lookup)
        plans.append((p,sections,payload))
    # Verify persistence and API service behaviour in a disposable repository.
    with tempfile.TemporaryDirectory(prefix="wiki20_verify_") as tmp:
        svc=WikiService(tmp)
        for p,sections,_ in plans:
            saved=svc.create_draft(p["name"],sections,reason=BATCH,extra={
                "page_type":"chemical","showcase_batch":BATCH,"model_provenance":MODEL_SOURCE})
            verify(saved,p,lookup)
            detail=svc.detail(p["name"])
            assert not detail["is_published"]
            assert all(s["review_status"]=="pending" for s in detail["sections"])
        assert len(svc.list())==20
    report={"batch":BATCH,"created_at":datetime.now(timezone.utc).isoformat(),
            "mode":"apply" if args.apply else "dry_run","isolation_verification":"passed",
            "provenance_policy":MODEL_SOURCE,"new_entries":[],
            "publication":"draft_only_pending_review"}
    if args.apply:
        live=WikiService()
        before=snapshot(live)
        # No names are overwritten; repeated application resumes only this same authored batch.
        for p,_,_ in plans:
            if p["name"] in before:
                current=live.repo.read(p["name"])
                assert current.get("showcase_batch")==BATCH, f"Existing unrelated page: {p['name']}"
        backup=BASE/"backups"/(BATCH+"_"+datetime.now().strftime("%H%M%S"))
        backup.mkdir(parents=True,exist_ok=False)
        with live.repo.connect() as src:
            with sqlite3.connect(str(backup/"registry.sqlite")) as dest:src.backup(dest)
        (backup/"before.json").write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding="utf-8")
        protected=[METADATA,BASE/"data/vector_store/faiss.index",BASE/"data/knowledge/documents.json"]
        protected=[f for f in protected if f.exists()]
        hashes={str(f):file_hash(f) for f in protected}
        for p,sections,_ in plans:
            if p["name"] in before:
                saved=live.repo.read(p["name"])
            else:
                saved=live.create_draft(p["name"],sections,reason=BATCH,extra={
                    "page_type":"chemical","showcase_batch":BATCH,
                    "generation_method":"assistant_model_background_plus_local_exact_excerpts",
                    "model_provenance":copy.deepcopy(MODEL_SOURCE),"product_scope":p["scope"],
                    "verification_status":"draft_pending_expert_review"})
            verify(saved,p,lookup)
            detail=live.detail(p["name"])
            assert not detail["is_published"] and all(s["review_status"]=="pending" for s in detail["sections"])
            report["new_entries"].append({"entity":p["name"],"revision":saved["revision_id"],
                 "sections":17,"evidence":len(saved["evidence"]),
                 "model_blocks":sum(b["knowledge_source"]=="model_prior" for s in saved["sections"] for b in s["knowledge_blocks"]),
                 "grounded_blocks":sum(b["knowledge_source"]=="grounded" for s in saved["sections"] for b in s["knowledge_blocks"]),
                 "characters":sum(len(s["content"]) for s in saved["sections"]),"review":"pending"})
        after=snapshot(live)
        for name,original in before.items():
            if name not in {p["name"] for p in PROFILES}:assert after[name]==original, name
        for path,h in hashes.items():assert file_hash(Path(path))==h,path
        report.update(backup=str(backup),before_count=len(before),after_count=len(after),
                      existing_entries_unchanged=True,protected_files_unchanged=True,protected_sha256=hashes)
    else:
        for p,_,payload in plans:
            report["new_entries"].append({"entity":p["name"],"sections":17,"evidence":len(payload["evidence"]),
                     "characters":sum(len(s["content"]) for s in payload["sections"])})
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    md=args.report.with_suffix(".md")
    lines=["# 20 个化学品 Wiki 展示草稿", "",
           "正文来源：Codex 当前会话的模型背景知识。具体模型版本未由环境提供；本地逐字摘录另绑定原始文档证据。",
           "新增内容均为待审核草稿，未自动发布。技术校验确认结构和引用对应，不代表专家已确认事实。",
           "", "| 化学品 | 章节 | 本地证据 | 正文字数（含标签与摘录） |", "|---|---:|---:|---:|"]
    lines += [f"| {r['entity']} | {r['sections']} | {r['evidence']} | {r['characters']} |" for r in report["new_entries"]]
    lines += ["", "验证：20 篇在隔离注册表中完成创建、读取、章节、来源标识及逐字引用校验；高风险章节发布门槛仍生效。"]
    if args.apply:
        lines += [f"生产目录：{BASE}/data/wiki；条目总数：{report['before_count']} → {report['after_count']}。",
                  "原有条目的版本和审核记录保持不变；FAISS、向量元数据和文档登记文件哈希保持不变。",
                  f"注册表备份：{report['backup']}。"]
    md.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"report":str(args.report),"mode":report["mode"],"entries":len(report["new_entries"]),
          "sections":sum(r["sections"] for r in report["new_entries"]),
          "evidence":sum(r["evidence"] for r in report["new_entries"]),
          "characters":sum(r["characters"] for r in report["new_entries"]),
          "after_count":report.get("after_count"),"verification":"passed"},ensure_ascii=False))
if __name__=="__main__":main()
