from pathlib import Path
import json
import tempfile
import unittest
from flask import Flask
from core.dashboard import DashboardRepository, StaleSnapshot
from core.data_catalog import FileCatalog, profile, bins
from app.dashboard_api import register


class ColumnProfileTests(unittest.TestCase):
    def test_quality_partitions_full_denominator(self):
        p=profile([{"page_start":0},{"page_start":2},{"page_start":"3"},{"page_start":True},{},{"page_start":None}],"page_start")
        self.assertEqual((p["valid"],p["mismatched"],p["missing"]),(2,2,2))
        self.assertEqual(sum(b["count"] for b in p["histogram"]),2)
        self.assertEqual(p["statistics"]["mean"],1)

    def test_numeric_identifier_has_no_mean(self):
        p=profile([{"id":1},{"id":1},{"id":2},{"id":None}],"id")
        self.assertEqual(p["type"],"identifier")
        self.assertIsNone(p["statistics"])
        self.assertEqual(p["unique"],2)

    def test_dates_and_json_are_checked(self):
        p=profile([{"event_at":"2024-01-01"},{"event_at":"2024-99-01"},{"event_at":None},{"event_at":10}],"event_at")
        self.assertEqual((p["valid"],p["mismatched"],p["missing"]),(1,2,1))
        self.assertEqual(p["most_common"][0]["value"],"2024-01")
        p=profile([{"payload":"{}"},{"payload":"not-json"},{"payload":None}],"payload")
        self.assertEqual((p["valid"],p["mismatched"],p["missing"]),(1,1,1))

    def test_nested_objects_canonical_and_empty_missing(self):
        p=profile([{"assertion":{"a":1,"b":2}},{"assertion":{"b":2,"a":1}},{"assertion":{}}],"assertion")
        self.assertEqual(p["unique"],1)
        self.assertEqual(p["missing"],1)
        self.assertEqual(sum(b["count"] for b in p["histogram"]),2)

    def test_full_text_not_truncated_for_uniqueness(self):
        p=profile([{"text":"a"*300+"X"},{"text":"a"*300+"Y"}],"text")
        self.assertEqual(p["unique"],2)
        self.assertEqual(p["length_range"],[301,301])

    def test_category_percent_denominator_and_path_placeholders(self):
        p=profile([{"source":"A"},{"source":"A"},{"source":"B"},{}],"source")
        self.assertEqual(p["most_common"][0],{"value":"A","count":2})
        self.assertEqual(p["total"],4)
        p=profile([{"pdf_path":"nan"},{"pdf_path":"file.pdf"},{"pdf_path":"  "}],"pdf_path")
        self.assertEqual((p["valid"],p["missing"]),(1,2))

    def test_histogram_counts_all_values_and_equal_values(self):
        self.assertEqual(sum(b["count"] for b in bins(list(range(450)))),450)
        self.assertEqual(bins([3,3]),[{"start":3,"end":3,"count":2}])


class FileCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"data/vector_store").mkdir(parents=True)
        self.path=self.root/"data/vector_store/index_metadata.json"
        self.raw=[
            {"chunk_id":"A1","doc_id":"A","title":"标准A","document_type":"标准","text":"氨","page_start":1},
            {"chunk_id":"A2","doc_id":"A","title":"标准A","document_type":"标准","text":"段落二","page_start":2},
            {"chunk_id":"B1","doc_id":"B","title":"法规B","document_type":"法规","text":"甲醇","extra":"真实的额外字段"},
        ]
        self.path.write_text(json.dumps(self.raw),encoding="utf-8")
        self.app=Flask(__name__)
        register(self.app,self.root,None,lambda:[])
        self.client=self.app.test_client()
        self.files=self.app.extensions["dashboard_file_catalog"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_raw_full_profiles_and_paged_real_rows(self):
        r=self.files.detail("main_chunks",offset=1,size=1)
        self.assertEqual(r["total"],3)
        self.assertEqual(r["rows"],[self.raw[1]])
        p={c["name"]:c for c in r["columns"]}
        self.assertEqual((p["extra"]["valid"],p["extra"]["missing"]),(1,2))
        self.assertEqual(p["doc_id"]["unique"],2)
        self.assertIsNone(p["doc_id"]["statistics"])

    def test_doc_class_is_distinct_document_with_original_fragment(self):
        r=self.files.detail("standard_pdf")
        self.assertEqual(r["total"],1)
        self.assertEqual(r["rows"][0]["chunks"],2)
        self.assertEqual(r["rows"][0]["sample_text"],"氨")
        self.assertIsNone(r["file"]["bytes"])

    def test_full_sort_and_validation_allowlist(self):
        r=self.files.detail("main_chunks",offset=0,size=1,sort="chunk_id",descending=True)
        self.assertEqual(r["rows"][0]["chunk_id"],"B1")
        for kw in [{"size":101},{"offset":-1},{"sort":"made_up"}]:
            with self.assertRaises(ValueError):self.files.detail("main_chunks",**kw)
        with self.assertRaises(ValueError):self.files.detail("../../passwords")

    def test_stale_snapshot_and_api_errors(self):
        listing=self.files.list()
        self.path.write_text(json.dumps(self.raw+[{"chunk_id":"C1","doc_id":"C","text":"new"}]),encoding="utf-8")
        with self.assertRaises(StaleSnapshot):self.files.detail("main_chunks",listing["catalog_revision"])
        r=self.client.get("/api/dashboard/files/main_chunks",query_string={"catalog_revision":listing["catalog_revision"]})
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.client.get("/api/dashboard/files/main_chunks?offset=-1").status_code,400)
        self.assertEqual(self.client.get("/api/dashboard/files/not_known").status_code,400)
        self.assertEqual(self.client.get("/api/dashboard/files").status_code,200)
        self.assertEqual(self.client.get("/api/dashboard/files/main_chunks").status_code,200)


if __name__=="__main__":
    unittest.main()
