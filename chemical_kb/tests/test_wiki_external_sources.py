import copy,tempfile,unittest
from core.wiki.citations import bind_sections,validate_revision
from core.wiki.service import WikiService

def section(title="基本概述",url="https://en.wikipedia.org/wiki/Acetic_acid",name="Wikipedia"):
    text="**来源："+name+"**\n\n百科基础介绍。[阅读词条]("+url+")"
    return {"section":title,"content":text,"knowledge_blocks":[{"text":text,"knowledge_source":"external",
        "source_name":name,"source_url":url,"external_source_id":"ext-test","retrieved_at":"2026-10-02","evidence_ids":[]}],"_validated":True}
class ExternalSourceTests(unittest.TestCase):
    def payload(self,s):
        sections,evidence,errors=bind_sections([s])
        return {"sections":sections,"evidence":evidence,"binding_errors":errors}
    def test_external_attribution_is_readable_without_local_evidence(self):
        p=self.payload(section());self.assertTrue(validate_revision(p)["ok"]);self.assertEqual(p["evidence"],[])
    def test_external_high_risk_cannot_be_published(self):
        p=self.payload(section("急救"))
        self.assertTrue(validate_revision(p)["ok"]);self.assertFalse(validate_revision(p,publication=True)["ok"])
    def test_external_missing_origin_is_rejected(self):
        s=section();s["knowledge_blocks"][0].pop("retrieved_at")
        self.assertFalse(validate_revision(self.payload(s))["ok"])
    def test_external_origin_domains_cannot_be_spoofed(self):
        for url in ("javascript:alert(1)","https://en.wikipedia.org.attacker.example/wiki/Acetic","https://baike.baidu.com/item/乙酸"):
            self.assertFalse(validate_revision(self.payload(section(url=url)))["ok"])
    def test_baidu_correct_origin_is_valid(self):
        self.assertTrue(validate_revision(self.payload(section(url="https://baike.baidu.com/item/乙酸",name="百度百科")))["ok"])
    def test_model_label_change_updates_blocks_and_keeps_provenance(self):
        text="**来源：模型背景知识（Codex 当前会话生成，待核实）**\n\n内容。"
        s={"section":"基本概述","content":text,"knowledge_blocks":[{"text":text,"knowledge_source":"model_prior","evidence_ids":[],"model_source":{"provider":"Codex"}}]}
        p=self.payload(s)
        self.assertTrue(validate_revision(p)["ok"])
        self.assertIn("来源：大模型知识库",p["sections"][0]["content"])
        self.assertEqual(p["sections"][0]["knowledge_blocks"][0]["model_source"]["provider"],"Codex")
    def test_review_does_not_bypass_high_risk_external_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc=WikiService(tmp);p=svc.create_draft("测试",[section("急救")])
            svc.review("测试",{"expected_revision":p["revision_id"],"section":"急救","reviewer":"测试审核人","review_status":"approved"})
            with self.assertRaises(ValueError):svc.publish("测试",{"expected_revision":p["revision_id"],"reviewer":"测试审核人"})
if __name__=="__main__":unittest.main()
