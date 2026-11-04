"""Demo vendor seeding, offline vendor review, and the HTML report. No network."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ("app", "grc", "scripts"):
    sys.path.insert(0, os.path.join(ROOT, p))

import assess  # noqa: E402
import ai_review  # noqa: E402
import report  # noqa: E402
import seed_demo  # noqa: E402

TOP_KEYS = {"mode", "model", "generated_at", "summary", "rating", "top_risks",
            "red_flags", "follow_up_questions", "policy_gaps"}


def score(a):
    lab = a["kind"] == "internal"
    return assess.compute(answers=a["answers"], profiles=a["profiles"] or None,
                          use_lab_evidence=lab, attest_tested=not lab)


class VendorReviewTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        net = mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used"))
        net.start()
        self.addCleanup(net.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)
        seed_demo.seed(self.dir)
        self.items = []
        for fn in sorted(os.listdir(self.dir)):
            with open(os.path.join(self.dir, fn)) as f:
                self.items.append(json.load(f))

    def test_seed_shape_and_statuses(self):
        self.assertEqual(len(self.items), 5)
        statuses = sorted(a["status"] for a in self.items)
        self.assertEqual(statuses, ["in progress", "sent", "submitted", "submitted", "submitted"])
        for a in self.items:
            self.assertTrue(a["demo"])
            self.assertEqual(a["kind"], "third-party")
            self.assertRegex(a["id"], r"^[a-z0-9]{12}$")
            self.assertTrue(a["share_token"])
            for v in a["answers"].values():
                self.assertLessEqual(len(v["note"]), 500)
                if v.get("na"):
                    self.assertTrue(v["note"].strip())
                else:
                    self.assertIn(v["maturity"], range(4))
            if a["status"] == "sent":
                self.assertEqual(a["answers"], {})

    def test_submitted_fully_answered(self):
        qs = assess.load_questions()["questions"]
        for a in self.items:
            if a["status"] != "submitted":
                continue
            ids = {q["id"] for q in assess.select_questions(qs, a["profiles"])}
            self.assertEqual(ids, set(a["answers"]), a["name"])
            self.assertTrue(a["submitted_at"])

    def test_risk_spread(self):
        sevs = {score(a)["overall_sev"] for a in self.items if a["status"] == "submitted"}
        self.assertEqual(sevs, {"low", "medium", "high"})

    def test_idempotent_and_reset_only_demo(self):
        other = os.path.join(self.dir, "aaaaaaaaaaaa.json")
        with open(other, "w") as f:
            json.dump({"id": "aaaaaaaaaaaa", "name": "real"}, f)
        tokens = {a["id"]: a["share_token"] for a in self.items}
        again = seed_demo.seed(self.dir)
        self.assertEqual({a["id"]: a["share_token"] for a in again}, tokens)
        seed_demo.seed(self.dir, do_reset=True)
        self.assertTrue(os.path.exists(other))
        self.assertEqual(len(os.listdir(self.dir)), 6)

    def test_offline_review_and_report(self):
        for a in self.items:
            with self.subTest(a=a["name"]):
                s = score(a)
                r = ai_review.review(a, s)
                self.assertEqual(set(r), TOP_KEYS)
                self.assertEqual(r["mode"], "offline")
                self.assertIsNone(r["model"])
                self.assertIn(r["rating"], ("low", "medium", "high"))
                self.assertIn("rule-based", r["summary"])
                self.assertLessEqual(len(r["top_risks"]), 5)
                self.assertLessEqual(len(r["follow_up_questions"]), 5)
                for t in r["top_risks"]:
                    self.assertEqual(set(t), {"id", "title", "why", "fix"})
                for f in r["red_flags"]:
                    self.assertEqual(set(f), {"id", "issue"})
                self.assertTrue(all(p.startswith("POL-") for p in r["policy_gaps"]))
                out = report.render_report(a, s, r)
                self.assertTrue(out.startswith("<!DOCTYPE html>"))
                self.assertNotIn("\u2014", out)
                self.assertNotIn("\u2014", json.dumps(r, ensure_ascii=False))
                self.assertNotIn("<script", out)

    def test_red_flags_found(self):
        forge = next(a for a in self.items if a["name"].startswith("Forgepoint"))
        flagged = {f["id"] for f in ai_review.review(forge, score(forge))["red_flags"]}
        self.assertTrue({"ACCESS-1", "ROBUST-1", "DATA-2", "EU-4"} <= flagged)

    def test_report_escapes_vendor_text(self):
        a = next(a for a in self.items if a["status"] == "submitted")
        qid = next(k for k, v in a["answers"].items() if not v.get("na"))
        a["answers"][qid]["note"] = "<script>x</script>"
        a["name"] = "<img src=x onerror=alert(1)>"
        s = score(a)
        out = report.render_report(a, s, ai_review.review(a, s))
        self.assertNotIn("<script>x</script>", out)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", out)
        self.assertNotIn("<img", out)

    def test_claude_failure_falls_back(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-not-a-key"
        a = self.items[0]
        r = ai_review.review(a, score(a))
        self.assertEqual(r["mode"], "offline")
        self.assertNotIn("test-not-a-key", json.dumps(r))

    def test_claude_reply_is_validated(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-not-a-key"
        a = next(a for a in self.items if a["name"].startswith("Forgepoint"))
        s = score(a)
        reply = {"summary": "Weak controls \u2014 needs work.", "rating": "low",
                 "top_risks": [{"id": "MCP-2", "title": "t", "why": "w", "fix": "f"},
                               {"id": "NOT-REAL", "title": "x", "why": "x", "fix": "x"}],
                 "red_flags": [{"id": "ACCESS-1", "issue": "no evidence"}],
                 "follow_up_questions": ["q%d" % i for i in range(9)]}
        body = {"model": "claude-test", "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "```json\n" + json.dumps(reply) + "\n```"}]}
        with mock.patch.object(ai_review, "_call_claude", return_value=body) as call:
            r = ai_review.review(a, s)
        sent = json.dumps(call.call_args[0][0])
        self.assertNotIn("test-not-a-key", sent)
        self.assertEqual(r["mode"], "claude")
        self.assertEqual(r["rating"], s["overall_sev"])
        self.assertEqual([t["id"] for t in r["top_risks"]], ["MCP-2"])
        self.assertEqual(len(r["follow_up_questions"]), 5)
        self.assertNotIn("\u2014", r["summary"])


if __name__ == "__main__":
    unittest.main()
