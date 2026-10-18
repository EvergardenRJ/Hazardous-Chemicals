"""Compatibility adapter for legacy Wiki callers; no KG extraction/review writes."""
from pathlib import Path
from core.wiki.service import WikiService
from core.wiki.citations import CITATION,parse_sections as _parse_sections
from core.wiki.repository import NotFound,now

class WikiReviewManager:
    def __init__(self,review_dir=None,wiki_dir=None):
        root=wiki_dir or (Path(review_dir).parent if review_dir is not None else None)
        self.service=WikiService(root)
        self.review_dir=self.service.repo.root/"review"
    @staticmethod
    def parse_sections(markdown):
        # Parsing identifies numeric markers, not whether the claims are true.
        return [{**s,"knowledge_source":"unknown","evidence_ids":CITATION.findall(s["content"])} for s in _parse_sections(markdown)]
    def load_structured_sections(self,entity):
        try:return self.service.repo.read(entity)["sections"]
        except NotFound:return None
    def get_sections(self,entity,markdown=None):
        return self.load_structured_sections(entity) or self.parse_sections(markdown or "")
    def get_reviews(self,entity):
        try:
            p=self.service.repo.read(entity);records=self.service.repo.reviews(p["revision_id"])
            return {s["section"]:records.get(s["section"],{"section":s["section"],"section_id":s["section_id"],
                "revision_id":p["revision_id"],"content_hash":s["content_hash"],"review_status":"pending",
                "content":s["content"],"knowledge_source":s["knowledge_source"]}) for s in p["sections"]}
        except NotFound:return {}
    def init_review(self,entity,markdown,force=False):
        if force:raise ValueError("不能覆盖审核历史；请生成或修改新版本")
        self.service.repo.entry(entity) # Migration/store must create the evidence-bound revision first.
        return {"total":len(self.get_sections(entity)),"created":0}
    def submit_review(self,entity,record):
        if not (record.get("expected_revision") or record.get("revision_id")):
            raise ValueError("旧审核调用需要升级：请提交明确的版本与审核人")
        return self.service.review(entity,record)
    def get_statistics(self):
        stats={"pending":0,"approved":0,"rejected":0,"modified":0,"total":0}
        for e in self.service.list():
            for status,count in e.get("review_counts",{}).items():
                stats[status]=stats.get(status,0)+count;stats["total"]+=count
        return stats
