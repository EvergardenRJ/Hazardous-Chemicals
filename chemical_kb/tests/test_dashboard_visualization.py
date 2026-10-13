from contextlib import closing
import csv
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask
from core.dashboard import DashboardRepository, StaleSnapshot, aggregate, day, quantile
from app.dashboard_api import register


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for p in ["data/vector_store", "data/legacy", "data/knowledge", "data/news"]:
            (self.root / p).mkdir(parents=True, exist_ok=True)
        self.rows = [
            {"doc_id": "A", "chunk_id": "a1", "title": "标准A", "text": "氨与甲醇", "document_type": "标准", "source": "原始"},
            {"doc_id": "A", "chunk_id": "a2", "title": "标准A", "text": "氨", "document_type": "标准", "source": "原始"},
            {"doc_id": "B", "chunk_id": "b1", "title": "报告B", "text": "甲醇", "document_type": "事故", "source": "原始"},
            {"doc_id": "LEGACY:C", "chunk_id": "c1", "title": "=危险公式", "text": "其他文本", "document_type": "docx", "source": "旧资料"},
        ]
        self.write(self.rows + [self.rows[0], {"text": "无ID"}])
        registry = [{"doc_id": "A", "published_at": "2024-01-01"},
                    {"doc_id": "B", "published_at": "2024-02-01"}]
        (self.root / "data/knowledge/documents.json").write_text(json.dumps(registry), encoding="utf-8")
        with closing(sqlite3.connect(self.root / "data/news/mirror.sqlite3")) as db:
            db.execute("CREATE TABLE articles(id INTEGER,url TEXT,title TEXT,source_id TEXT,published_at TEXT,event_at TEXT,article_type TEXT,review_status TEXT,payload TEXT,removed INTEGER)")
            for i, date in enumerate(["2024-01-05", "2024-02-05", None], 1):
                db.execute("INSERT INTO articles VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (i, "https://example.org/" + str(i), "新闻" + str(i), "official",
                            date, None, "news", "candidate",
                            json.dumps({"country": "CN", "source_org": "公开机构", "summary": "氨"}), 0))
            db.commit()
        self.app = Flask(__name__)
        register(self.app, self.root, None, lambda: [])
        self.client = self.app.test_client()
        self.repo = self.app.extensions["dashboard_repository"]

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        (self.root / "data/vector_store/index_metadata.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def query(self, **kwargs):
        return self.repo.query({"dataset": "documents", "dimensions": ["type"], **kwargs})

    def test_multi_label_total_is_not_group_sum(self):
        r = self.query(dimensions=["chemical"])
        groups = {g["key"][0]: g["value"] for g in r["groups"]}
        self.assertEqual(groups["氨"], 1)
        self.assertEqual(groups["甲醇"], 2)
        self.assertEqual(groups["未标注"], 1)
        self.assertEqual(r["value"], 3)
        self.assertEqual(sum(groups.values()), 4)

    def test_duplicate_fragments_and_invalid_ids(self):
        b = self.repo.bootstrap()
        self.assertEqual(b["totals"]["documents"], 3)
        self.assertEqual(b["totals"]["chunks"], 4)
        self.assertEqual(b["quality"], {"duplicate_chunk_ids": 1, "rows_without_document_id": 1})
        self.assertEqual(self.query(metric="chunks")["value"], 4)

    def test_and_filters_and_or_values(self):
        r = self.query(filters=[{"field": "chemical", "values": ["氨", "甲醇"]},
                                {"field": "type", "values": ["标准"]}])
        self.assertEqual([x["id"] for x in r["details"]], ["A"])

    def test_dates_unknown_are_explicit(self):
        included = self.query(**{"from": "2024-02-01", "to": "2024-02-28"})
        self.assertEqual(included["total"], 2)
        excluded = self.query(unknown="exclude", **{"from": "2024-02-01", "to": "2024-02-28"})
        self.assertEqual(excluded["total"], 1)
        self.assertEqual(self.query(unknown="only")["total"], 1)

    def test_news_event_date_never_falls_back_to_publication(self):
        r = self.repo.query({"dataset": "news", "dimensions": ["month"], "time_axis": "event"})
        self.assertEqual(r["groups"][0]["key"], ["未标注"])
        self.assertEqual(r["passport"]["unknown_dates"], 3)
        self.assertEqual(r["timeline"], [])

    def test_exact_marginals_recalculate_distinct(self):
        r = self.query(dimensions=["type", "chemical"])
        standard = next(x for x in r["marginals"][0] if x["key"] == ["标准"])
        self.assertEqual(standard["value"], 1)
        self.assertEqual(sum(x["value"] for x in r["groups"] if x["key"][0] == "标准"), 2)

    def test_detail_scope_and_fragments(self):
        d = self.repo.detail("documents", "A")
        self.assertEqual(d["fragment_total"], 2)
        self.assertEqual(d["fragments"][0]["text"], "氨与甲醇")
        self.assertIsNone(d["fragments"][0]["page_start"])

    def test_snapshot_change_returns_conflict(self):
        token = self.repo.bootstrap()["snapshot_id"]
        self.write(self.rows + [{"doc_id": "D", "chunk_id": "d1", "text": "新的资料", "document_type": "标准"}])
        response = self.client.post("/api/dashboard/query", json={"snapshot_id": token, "dataset": "documents", "dimensions": ["type"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error_code"], "snapshot_changed")

    def test_invalid_dimension_metric_and_date(self):
        for body in [{"dimensions": ["region"]}, {"metric": "risk"}, {"from": "2024-13-01"},
                     {"from": "2024-03-01", "to": "2024-01-01"},
                     {"filters": [{"field": "chemical", "values": []}]},
                     {"dimensions": ["type", "type"]}]:
            response = self.client.post("/api/dashboard/query", json={"dataset": "documents", **body})
            self.assertEqual(response.status_code, 400, body)

    def test_query_endpoint_pagination_and_counts(self):
        response = self.client.post("/api/dashboard/query", json={"dataset": "documents", "dimensions": ["type"], "size": 1, "offset": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total"], 3)
        self.assertEqual(len(response.json["details"]), 1)

    def test_export_all_rows_and_formula_escaping(self):
        response = self.client.post("/api/dashboard/export", json={"dataset": "documents", "dimensions": ["type"], "size": 1})
        self.assertEqual(response.status_code, 200)
        records = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
        self.assertEqual(len(records), 7)
        self.assertTrue(any("'=危险公式" in row for row in records))

    def test_histogram_uses_all_records_not_scatter_limit(self):
        self.write([{"doc_id": "D" + str(i), "chunk_id": "c" + str(i), "text": "x" * (i + 1), "document_type": "标准"} for i in range(400)])
        r = self.query()
        self.assertEqual(len(r["scatter"]), 300)
        self.assertEqual(sum(x["value"] for x in r["histogram"]), 400)
        self.assertEqual(sum(x["n"] for x in r["distribution"]), 400)

    def test_tree_and_flow_use_selected_metric(self):
        r = self.query(metric="characters")
        self.assertEqual(sum(x["value"] for x in r["tree"]), r["value"])
        left = [x for x in r["sankey"] if x["source"].startswith("collection|")]
        self.assertEqual(sum(x["value"] for x in left), r["value"])
        self.assertEqual(sum(x["value"] for x in r["marginals_by_field"]["source"]), r["value"])

    def test_units_and_missing_dates(self):
        r = self.query(metric="characters")
        self.assertEqual(r["passport"]["unit"], "字符")
        self.assertEqual(r["passport"]["unknown_dates"], 1)
        self.assertEqual(r["value"], sum(len(x["text"]) for x in self.rows))

    def test_timezone_date_precision(self):
        self.assertEqual(day("2024-01-01T23:00:00Z"), "2024-01-02")
        self.assertEqual(day("2024-01-01"), "2024-01-01")
        self.assertIsNone(day("不明"))

    def test_quantile_and_box(self):
        self.assertEqual(quantile([1, 2, 3, 4], .25), 1.75)
        r = self.query()
        self.assertEqual(sum(x["n"] for x in r["distribution"]), 3)

    def test_missing_optional_dataset_is_not_fake_zero_analysis(self):
        self.assertFalse(self.repo.bootstrap()["datasets"]["wiki"]["available"])
        with self.assertRaises(ValueError):
            self.repo.query({"dataset": "wiki", "dimensions": ["page_type"]})



    def test_sqlite_wal_housekeeping_does_not_expire_snapshot(self):
        before = self.repo.bootstrap()["snapshot_id"]
        with closing(sqlite3.connect(self.root / "data/news/mirror.sqlite3")) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE housekeeping(value TEXT)")
            db.execute("INSERT INTO housekeeping VALUES('touch')")
            db.commit()
            self.assertEqual(self.repo.bootstrap()["snapshot_id"], before)
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.assertEqual(self.repo.bootstrap()["snapshot_id"], before)
            db.execute("UPDATE articles SET title='真实更新' WHERE id=1")
            db.commit()
            self.assertNotEqual(self.repo.bootstrap()["snapshot_id"], before)


if __name__ == "__main__":
    unittest.main()
