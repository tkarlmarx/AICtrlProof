"""Reference benchmark: comparison logic and the shape of grc/benchmarks/*.json."""
import glob
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "grc"))

import assess  # noqa: E402

QIDS = {q["id"] for q in assess.load_questions()["questions"]}
FAKE = {"meta": {"name": "Ref", "sources": [{"id": "s1", "title": "Doc", "url": "https://example.org/doc"}]},
        "controls": {"GOV-1": {"level": 3, "evidence": "named owner", "sources": ["s1"]},
                     "GOV-2": {"level": 2, "evidence": "policy", "sources": ["s1"]},
                     "EU-2": {"level": 2, "evidence": "x", "sources": ["s1", "missing"]},
                     "MCP-1": {"level": 1, "evidence": "y", "sources": []}}}


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def cmp(self, answers, profiles=None):
        scored = assess.compute(answers=answers, results_dir=self.d, profiles=profiles)
        return assess.benchmark_compare(scored, FAKE)

    def test_gaps_and_summary(self):
        out = self.cmp({"GOV-1": {"maturity": 1}, "GOV-2": {"maturity": 3}, "EU-2": {"na": True, "note": "not high-risk"}},
                       profiles=["agent"])
        rows = {r["id"]: r for r in out["rows"]}
        self.assertEqual(rows["GOV-1"]["gap"], -2)
        self.assertEqual(rows["GOV-2"]["gap"], 1)
        self.assertTrue(rows["EU-2"].get("na"))
        self.assertNotIn("MCP-1", rows, "out-of-scope questions are not compared")
        s = out["summary"]
        self.assertEqual((s["compared"], s["behind"], s["ahead"]), (2, 1, 1))
        self.assertEqual(s["vendor_avg"], 2.0)
        self.assertEqual(s["bench_avg"], 2.5)

    def test_unknown_source_keys_dropped(self):
        out = self.cmp({}, profiles=["mcp"])
        eu2 = next(r for r in out["rows"] if r["id"] == "EU-2")
        self.assertEqual([s["id"] for s in eu2["bench_sources"]], ["s1"])

    def test_unanswered_not_compared(self):
        out = self.cmp({})
        self.assertEqual(out["summary"]["compared"], 0)
        self.assertIsNone(out["summary"]["vendor_avg"])


class BenchmarkFileTest(unittest.TestCase):
    def test_benchmark_files_are_well_formed(self):
        files = glob.glob(os.path.join(ROOT, "grc", "benchmarks", "*.json"))
        if not files:
            self.skipTest("no benchmark files yet")
        for fn in files:
            with self.subTest(fn=os.path.basename(fn)):
                raw = open(fn, encoding="utf-8").read()
                self.assertNotIn("—", raw)
                b = json.loads(raw)
                srcs = {s["id"] for s in b["meta"]["sources"]}
                self.assertTrue(b["meta"].get("method"))
                for s in b["meta"]["sources"]:
                    self.assertTrue(s["url"].startswith("https://"))
                for qid, c in b["controls"].items():
                    self.assertIn(qid, QIDS)
                    self.assertIn(c["level"], range(4))
                    self.assertTrue(c["evidence"])
                    self.assertTrue(c["sources"], f"{qid} needs a source")
                    self.assertLessEqual(set(c["sources"]), srcs)


if __name__ == "__main__":
    unittest.main()
