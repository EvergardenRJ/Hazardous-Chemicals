"""Legacy WikiStore adapter backed by the common immutable repository."""
from pathlib import Path
from core.wiki.service import WikiService
from core.wiki.citations import parse_sections
from core.wiki.repository import NotFound,safe_entity

class WikiStore:
    def __init__(self,wiki_dir=None):
        self.service=WikiService(wiki_dir);self.wiki_dir=str(self.service.repo.root)
    def _safe_name(self,name):return safe_entity(name)
    def _wiki_path(self,entity):
        e=self.service.repo.entry(entity)
        return str(self.service.repo.root/"entries"/e["wiki_id"]/"revisions"/e["draft_revision"])
    def save(self,entity,wiki_content,evidence=None):
        try:expected=self.service.repo.entry(entity)["draft_revision"]
        except NotFound:expected=None
        sections=parse_sections(wiki_content) or [{"section":"正文","content":wiki_content,"status":"legacy_unverified"}]
        self.service.create_draft(entity,sections,evidence,expected,reason="legacy_api")
        return self._wiki_path(entity)
    def save_sections(self,entity,sections):
        expected=self.service.repo.entry(entity)["draft_revision"]
        self.service.create_draft(entity,sections,expected=expected,reason="legacy_structured_api")
        return self._wiki_path(entity)
    def load(self,entity):
        try:return self.service.repo.read(entity)["markdown"]
        except NotFound:return None
    def load_sections(self,entity):
        try:return self.service.repo.read(entity)["sections"]
        except NotFound:return None
    def list_all(self):return [e["entity"] for e in self.service.repo.list()]
    def delete(self,entity):
        raise ValueError("不可变 Wiki 不支持旧接口直接删除；请保留历史并处理来源撤回")
