"""Legacy synchronous adapter; all persisted results use the v2 quality/version gates."""
from core.wiki.citations import SECTIONS as WIKI_SECTIONS,bind_sections,render,validate_revision
from core.wiki.generation import Generator
from core.wiki.service import WikiService
from core.wiki.jobs import kg_busy
from core.wiki.repository import NotFound

class WikiGenerator:
    def __init__(self,rag_system=None,case_retriever=None):
        if rag_system is None:raise ValueError("WikiGenerator 需要已初始化的 RAGSystem")
        self.rag=rag_system;self.generator=Generator(rag_system);self.service=WikiService()
    def build_outline(self,entity):return list(WIKI_SECTIONS)
    def generate(self,entity,save=True):
        if kg_busy():raise ValueError("关系抽取正在使用 GPU；请在知识 Wiki 页面提交持久任务")
        sections=[self.generator.generate_section(entity,s) for s in WIKI_SECTIONS]
        bound,evidence,errors=bind_sections(sections)
        validation=validate_revision({"sections":bound,"evidence":evidence,"binding_errors":errors})
        if save:
            if not validation["ok"]:raise ValueError("生成校验失败，未覆盖已有 Wiki："+str(validation["errors"][:5]))
            try:base=self.service.repo.entry(entity)["draft_revision"]
            except NotFound:base=None
            p=self.service.create_draft(entity,sections,expected=base)
            return {**p,"wiki":p["markdown"],"validation":validation}
        return {"entity":entity,"wiki":render(entity,bound),"sections":bound,"evidence":evidence,"validation":validation}
