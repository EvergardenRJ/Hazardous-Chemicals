"""Compatibility validator sharing v2 structural and evidence rules."""
from core.wiki.citations import bind_sections,validate_section,validate_revision
class WikiQualityValidator:
    def validate_section(self,result,evidence):
        sections,table,binding=bind_sections([{**result,"evidence":evidence}])
        errors=binding+validate_section(sections[0],table,strict=True)
        return not errors,errors
    def validate_wiki(self,sections):
        bound,table,errors=bind_sections(sections)
        return {**validate_revision({"sections":bound,"evidence":table,"binding_errors":errors}),
                "section_count":len(sections),"total_len":sum(len(s.get("content","")) for s in sections)}
