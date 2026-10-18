"""Shared Wiki workflow. Never writes knowledge-graph extraction/review data."""
import copy
import json
import re
from pathlib import Path
from .citations import CITATION, bind_sections, digest, infer_blocks, parse_sections, validate_revision, validate_section, section_hash, source_signature
from .repository import Repository, Conflict, NotFound, now, safe_entity

class WikiService:
    def __init__(self, root=None):
        self.repo = Repository(root)

    def list(self):
        result=[]
        with self.repo.connect() as db:
            reviews={}
            for row in db.execute("SELECT r.revision_id,r.section_id,r.decision FROM review_events r JOIN entries e ON e.draft_revision=r.revision_id ORDER BY r.rowid"):
                reviews.setdefault(row["revision_id"],{})[row["section_id"]]=row["decision"]
        for e in self.repo.list():
            if e.get("summary"):
                summary=json.loads(e["summary"])
            else:
                try:
                    p=self.repo.read(e["entity"])
                    summary={"page_type":p.get("page_type","chemical"),"section_count":len(p["sections"]),"validation_ok":validate_revision(p)["ok"]}
                    with self.repo.connect() as db:db.execute("UPDATE entries SET summary=? WHERE wiki_id=?",(json.dumps(summary),e["wiki_id"]))
                except (OSError,ValueError):result.append({**e,"error":"版本完整性校验失败"});continue
            counts={"pending":summary["section_count"],"approved":0,"modified":0,"rejected":0}
            for status in reviews.get(e["draft_revision"],{}).values():
                counts["pending"]-=1;counts[status]=counts.get(status,0)+1
            result.append({**{k:v for k,v in e.items() if k!="summary"},**summary,"review_counts":counts})
        return result

    def detail(self, entity, view="draft", revision=None):
        entry = self.repo.entry(entity)
        rid = revision or (entry["published_revision"] if view == "published" else entry["draft_revision"])
        fallback = not rid
        p = self.repo.read(entity, rid or entry["draft_revision"])
        reviews = self.repo.reviews(p["revision_id"])
        with self.repo.connect() as db:
            revision_freshness=db.execute("SELECT freshness FROM revisions WHERE revision_id=?",(p["revision_id"],)).fetchone()[0]
        p.update(freshness=revision_freshness,entry=entry, reviews=reviews, validation=validate_revision(p),
                 view="draft" if fallback else view, is_published=p["revision_id"] == entry["published_revision"])
        for s in p["sections"]:
            r = reviews.get(s["section"], {})
            s["review_status"] = r.get("review_status", "pending")
            s["candidate_content"] = s["content"]
            s["validation_errors"] = validate_section(s, p["evidence"])
        p["related"] = self.related(entity, p)
        return p

    def create_draft(self, entity, sections, fallback=None, expected=None, reason="generation", extra=None):
        bound, evidence, errors = bind_sections(sections, fallback)
        payload = {"schema_version":2,"sections":bound,"evidence":evidence,"binding_errors":errors,**(extra or {})}
        metadata=Path(__import__("os").environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))/"data/vector_store/index_metadata.json"
        if metadata.exists():
            stat=metadata.stat();payload["source_stamp"]=digest([stat.st_mtime_ns,stat.st_size])
            payload["corpus_doc_ids"]=sorted({str(r.get("doc_id")) for r in json.loads(metadata.read_text(encoding="utf-8"))})
        payload["validation"] = validate_revision(payload)
        inherited = self.repo.reviews(expected) if expected else None
        return self.repo.commit(entity,payload,expected,reason,inherited)

    def review(self, entity, data):
        revision = data.get("expected_revision") or data.get("revision_id")
        if not revision:
            raise ValueError("请重新打开条目，审核必须包含当前版本")
        actor = str(data.get("reviewer") or "").strip()
        if not actor or len(actor)>100:
            raise ValueError("请填写审核人姓名或工号")
        decision = data.get("review_status")
        if decision not in ("approved","modified","rejected"):
            raise ValueError("无效审核状态")
        comment = str(data.get("review_comment") or "").strip()
        if decision != "approved" and not comment:
            raise ValueError("修改或拒绝必须填写审核意见")
        current = self.repo.entry(entity)
        if current["draft_revision"] != revision:
            raise Conflict("内容已改变，请重新审核当前版本")
        p = self.repo.read(entity,revision)
        s = next((s for s in p["sections"] if s["section_id"] == data.get("section_id") or s["section"] == data.get("section")),None)
        if not s:
            raise NotFound("章节不存在")
        if data.get("content_hash") and data["content_hash"] != s["content_hash"]:
            raise Conflict("章节已改变")
        original = s["content"]
        original_hash = s["content_hash"]
        if decision == "modified":
            edited = str(data.get("reviewed_content") or "").strip()
            if not edited:
                raise ValueError("修改后内容不能为空")
            p = copy.deepcopy(p)
            s = next(x for x in p["sections"] if x["section_id"] == s["section_id"])
            s["content"] = edited
            s["knowledge_blocks"] = infer_blocks(edited,p["evidence"],s.get("knowledge_blocks"))
            s["evidence_refs"] = list(dict.fromkeys(e["evidence_id"] for n in CITATION.findall(edited) if 0<int(n)<=len(p["evidence"]) for e in [p["evidence"][int(n)-1]]))
            sources = {b["knowledge_source"] for b in s["knowledge_blocks"]}
            s["knowledge_source"] = next(iter(sources)) if len(sources)==1 else "mixed"
            s["content_hash"] = section_hash(edited,p["evidence"])
            s["_validated"] = True
            s["_errors"] = []
            s["status"] = "draft"
            s.pop("original_content",None);s.pop("original_knowledge_blocks",None)
            p["binding_errors"] = [e for e in p.get("binding_errors",[]) if not e.startswith(s["section"]+":")]
            errors = validate_section(s,p["evidence"],strict=True)
            if errors:
                raise ValueError("修改后校验未通过："+"；".join(errors))
            p["validation"] = validate_revision(p)
            p = self.repo.commit(entity,p,revision,"human_edit",self.repo.reviews(revision))
            revision = p["revision_id"]
        elif decision == "approved":
            errors = validate_section(s,p["evidence"],strict=True)
            if errors:
                raise ValueError("请先修正章节后再通过："+"；".join(errors))
        if decision != "modified" and current["published_revision"] == revision:
            p=self.repo.commit(entity,p,revision,"re_review",self.repo.reviews(revision))
            revision=p["revision_id"]
        record = {
            "entity":entity,"wiki_id":p["wiki_id"],"revision_id":revision,"section":s["section"],"section_id":s["section_id"],
            "content":original,"content_hash":s["content_hash"],"original_content_hash":original_hash,
            "reviewed_content":s["content"] if decision!="rejected" else "", "knowledge_source":s.get("knowledge_source","unknown"),
            "evidence_ids":list(dict.fromkeys(CITATION.findall(s["content"]))),"evidence_refs":s.get("evidence_refs",[]),
            "review_status":decision,"reviewer":actor,"reviewed_at":now(),"review_comment":comment,
            "error_type":str(data.get("error_type") or ("content_review" if decision!="approved" else ""))}
        record = self.repo.add_review(entity,revision,record)
        # Cases are append-only derived data owned by Wiki, not the running KG case store.
        path = self.repo.root/"wiki_cases.jsonl"
        with path.open("a",encoding="utf-8") as f:
            f.write(json.dumps({**record,"case_id":record["review_event_id"],"task_type":"wiki_generation",
                               "case_type":"success" if decision=="approved" else "failure"},ensure_ascii=False)+"\n")
        return record

    def publish(self, entity, data, rollback=False):
        actor = str(data.get("reviewer") or "").strip()
        if not actor:
            raise ValueError("发布或回滚需要操作者")
        entry = self.repo.entry(entity)
        revision = data.get("revision_id") if rollback else data.get("expected_revision")
        if not revision:
            raise ValueError("需要明确的版本")
        p = self.repo.read(entity,revision)
        if rollback:
            with self.repo.connect() as db:
                was_published = db.execute("SELECT 1 FROM audit_events WHERE wiki_id=? AND revision_id=? AND action='publish'",
                                           (entry["wiki_id"],revision)).fetchone()
            if not was_published:
                raise ValueError("只能回滚到已经发布过的版本")
        else:
            metadata=Path(__import__("os").environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))/"data/vector_store/index_metadata.json"
            if metadata.exists():
                self.refresh_sources(metadata,force=True)
            with self.repo.connect() as db:
                freshness=db.execute("SELECT freshness FROM revisions WHERE revision_id=?",(revision,)).fetchone()[0]
            if freshness != "fresh":
                raise ValueError("来源已变化，先刷新并核实证据")
            validation = validate_revision(p,publication=True)
            if not validation["ok"]:
                raise ValueError("发布校验未通过："+"；".join(validation["errors"][:8]))
            reviews = self.repo.reviews(revision)
            if any(reviews.get(s["section"],{}).get("review_status") not in ("approved","modified") or
                   reviews.get(s["section"],{}).get("content_hash") != s["content_hash"] for s in p["sections"]):
                raise ValueError("所有待发布章节必须在当前内容版本完成审核")
        result = self.repo.activate(entity,revision,actor,"rollback" if rollback else "publish",data.get("expected_revision"))
        self.rebuild_projection()
        return result

    def import_legacy(self, extra_root=None):
        report = []
        candidates = []
        for path in sorted(self.repo.root.glob("*/wiki.md")):
            if path.parent.name in ("review","pages","entries","legacy"):
                continue
            root = path.parent
            sections = json.loads((root/"sections.json").read_text(encoding="utf-8")) if (root/"sections.json").exists() else parse_sections(path.read_text(encoding="utf-8"))
            evidence = json.loads((root/"evidence.json").read_text(encoding="utf-8")) if (root/"evidence.json").exists() else []
            if not (root/"sections.json").exists():
                for s in sections:
                    s["status"]="legacy_unverified"
            candidates.append((root.name,sections,evidence,str(root),"chemical"))
        for path in sorted((self.repo.root/"pages").glob("*.json")):
            obj = json.loads(path.read_text(encoding="utf-8"))
            name = safe_entity(obj.get("topic") or path.stem) + "（历史主题页）"
            sections = parse_sections(obj.get("content","")) or [{"section":"历史正文","content":obj.get("content","")}]
            for s in sections:s["status"]="legacy_unverified"
            candidates.append((name,sections,obj.get("evidence",[]),str(path),"legacy"))
        if extra_root and Path(extra_root).resolve()!=self.repo.root:
            for path in sorted(Path(extra_root).glob("*/wiki.md")):
                sections = parse_sections(path.read_text(encoding="utf-8"))
                for s in sections:s["status"]="legacy_unverified"
                evpath=path.parent/"evidence.json"
                evidence=json.loads(evpath.read_text(encoding="utf-8")) if evpath.exists() else []
                candidates.append((path.parent.name+"（旧目录版本）",sections,evidence,str(path.parent),"legacy"))
        for entity,sections,evidence,source,page_type in candidates:
            try:
                self.repo.entry(entity)
                continue
            except NotFound:
                pass
            review_path=self.repo.root/"review"/(entity+".json")
            old=json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
            p=self.create_draft(entity,sections,evidence,reason="legacy_import",extra={"legacy_source":source,"page_type":page_type,"legacy_reviews":old})
            for s in p["sections"]:
                r=old.get(s["section"],{})
                self.repo.add_review(entity,p["revision_id"],{"section":s["section"],"section_id":s["section_id"],
                    "content_hash":s["content_hash"],"review_status":"pending","reviewer":"legacy_unknown",
                    "reviewed_at":now(),"legacy_record":r,"content":s["content"]})
            report.append({"entity":entity,"revision_id":p["revision_id"],"sections":len(p["sections"]),
                           "binding_errors":p["binding_errors"],"validation":p["validation"]})
        return report

    def refresh_sources(self, metadata_path,force=False):
        path=Path(metadata_path)
        if not path.exists():
            return {"checked":0,"error":"来源索引不可用"}
        stat=path.stat()
        extra=self.repo.root/"source_index.json"
        extra_stamp=[extra.stat().st_mtime_ns,extra.stat().st_size] if extra.exists() else None
        stamp=digest([stat.st_mtime_ns,stat.st_size,extra_stamp])
        marker=self.repo.root/"source_stamp.json"
        previous=json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        if not force and previous.get("stamp")==stamp:
            return {"changed":False}
        rows=json.loads(path.read_text(encoding="utf-8"))
        if extra.exists():rows.extend(json.loads(extra.read_text(encoding="utf-8")))
        index={str(r.get("chunk_id")):r for r in rows}
        results=[]
        for entry in self.repo.list():
            states={}
            for revision in set(filter(None,[entry["draft_revision"],entry["published_revision"]])):
                payload=self.repo.read(entry["entity"],revision)
                affected=[]
                for section in payload["sections"]:
                    ids=set(section.get("evidence_refs",[]))
                    for evidence in payload.get("evidence",[]):
                        if evidence["evidence_id"] not in ids:continue
                        meta=evidence["metadata"];current=index.get(str(meta.get("chunk_id")))
                        if current is None or source_signature(current)!=source_signature(meta):
                            affected.append(section["section"]);break
                candidates=[]
                if payload.get("corpus_doc_ids") is not None:
                    old_docs=set(payload["corpus_doc_ids"])
                    candidates=sorted({str(r.get("doc_id")) for r in rows if str(r.get("doc_id")) not in old_docs and
                        entry["entity"] in str(r.get("title",""))+" "+str(r.get("text",""))})
                state="stale" if affected else ("needs_check" if candidates else "fresh")
                states[revision]=state
                with self.repo.connect() as db:
                    db.execute("UPDATE revisions SET freshness=? WHERE revision_id=?",(state,revision))
                results.append({"entity":entry["entity"],"revision_id":revision,"freshness":state,"affected_sections":affected,"new_source_candidates":candidates})
            visible=states.get(entry["published_revision"] or entry["draft_revision"],"fresh")
            with self.repo.connect() as db:
                db.execute("UPDATE entries SET freshness=? WHERE wiki_id=?",(visible,entry["wiki_id"]))
        with self.repo.connect() as db:
            db.execute("INSERT OR IGNORE INTO source_events VALUES(?,?,?)",(stamp,now(),json.dumps(results,ensure_ascii=False)))
        tmp=marker.with_suffix(".tmp")
        tmp.write_text(json.dumps({"stamp":stamp,"checked_at":now()}),encoding="utf-8")
        tmp.replace(marker)
        return {"changed":previous.get("stamp")!=stamp,"entries":results}

    def related(self, entity, payload=None):
        payload=payload or self.repo.read(entity)
        sources={e["metadata"].get("doc_id") for e in payload.get("evidence",[]) if e["metadata"].get("doc_id")}
        result=[]
        for entry in self.repo.list():
            if entry["entity"]==entity:continue
            other=self.repo.read(entry["entity"])
            overlap=sources & {e["metadata"].get("doc_id") for e in other.get("evidence",[])}
            if overlap:
                result.append({"entity":entry["entity"],"reason":f"共享 {len(overlap)} 份文档，仅作为导航关联",
                               "score":len(overlap),"published":bool(entry["published_revision"])})
        return sorted(result,key=lambda x:-x["score"])[:6]

    def lint(self):
        findings=[]
        for entry in self.repo.list():
            p=self.repo.read(entry["entity"])
            for error in validate_revision(p)["errors"]:
                findings.append({"entity":entry["entity"],"type":"validation","message":error})
            if entry["freshness"]!="fresh":
                findings.append({"entity":entry["entity"],"type":"freshness","message":"来源变更，需要核实或局部刷新"})
            reviews=self.repo.reviews(p["revision_id"])
            for s in p["sections"]:
                if reviews.get(s["section"],{}).get("review_status","pending")=="pending":
                    findings.append({"entity":entry["entity"],"type":"review","message":s["section"]+"：待审核"})
        return findings

    def rebuild_projection(self):
        """Deterministic published-only keyword projection; source evidence stays attached."""
        with self.repo.connect() as db:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS wiki_search USING fts5(entity,section,content,revision UNINDEXED, tokenize='unicode61')")
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS wiki_terms USING fts5(entity UNINDEXED,section UNINDEXED,revision UNINDEXED,tokens)")
            db.execute("DELETE FROM wiki_search")
            db.execute("DELETE FROM wiki_terms")
            for entry in self.repo.list():
                if not entry["published_revision"]:continue
                p=self.repo.read(entry["entity"],entry["published_revision"])
                for s in p["sections"]:
                    db.execute("INSERT INTO wiki_search VALUES(?,?,?,?)",(entry["entity"],s["section"],s["content"],p["revision_id"]))
                    from core.knowledge import _terms
                    db.execute("INSERT INTO wiki_terms VALUES(?,?,?,?)",(entry["entity"],s["section"],p["revision_id"],
                               " ".join(_terms(entry["entity"]+" "+s["section"]+" "+s["content"]))))
            db.execute("UPDATE outbox SET done=1 WHERE done=0")

    def search(self,query,limit=10,mode="wiki"):
        from core.knowledge import _terms,KeywordIndex
        if mode=="sources":
            base=Path(__import__("os").environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))
            return [{"knowledge_source":"grounded","source_type":"original_document",**h}
                    for h in KeywordIndex(base/"data/search/keyword.sqlite").search(query,min(int(limit),50))]
        terms=_terms(str(query or ""))[:24]
        if not terms:return []
        with self.repo.connect() as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='wiki_terms'").fetchone()
        if not exists:self.rebuild_projection()
        expression=" OR ".join('"'+t+'"' for t in terms)
        with self.repo.connect() as db:
            rows=db.execute("SELECT entity,section,revision,bm25(wiki_terms) score FROM wiki_terms WHERE wiki_terms MATCH ? ORDER BY score LIMIT ?",
                            (expression,min(max(int(limit)*3,1),150))).fetchall()
        hits=[]
        for row in rows:
            entry=self.repo.entry(row["entity"])
            if entry["freshness"]!="fresh" or entry["published_revision"]!=row["revision"]:continue
            p=self.repo.read(row["entity"],row["revision"]);s=next(x for x in p["sections"] if x["section"]==row["section"])
            hits.append({"entity":row["entity"],"section":row["section"],"revision_id":row["revision"],"content":s["content"],
                "evidence_refs":s["evidence_refs"],"knowledge_source":s.get("knowledge_source"),"score":float(-row["score"]),
                "source_type":"reviewed_wiki"})
        return hits[:min(max(int(limit),1),50)]

    def compare(self,entity,before,after):
        import difflib
        a=self.repo.read(entity,before);b=self.repo.read(entity,after)
        return {"before":before,"after":after,"diff":"".join(difflib.unified_diff(a["markdown"].splitlines(True),
                    b["markdown"].splitlines(True),fromfile=before,tofile=after)),
                "changed_sections":[s["section"] for s in b["sections"] if not any(
                    x["section_id"]==s["section_id"] and x["content_hash"]==s["content_hash"] for x in a["sections"])]}
