"""
Schema and tagging tests for grc/questions.json and grc/policy.json.

Every question must carry all three tag groups: AI policy, compliance
(framework clauses), and a NIST metric. Framework clauses must come from the
canonical list in meta.clauses, so a new spelling cannot silently inflate
"controls referenced" in the coverage table.
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "grc"))

import assess  # noqa: E402

QB = assess.load_questions()
META, QS = QB["meta"], QB["questions"]
POLICY_IDS = {c["id"] for c in assess.load_policy()["clauses"]}
LAB_METRICS = {"broker_leak_reduction", "broker_deny_enforced", "injection_resistance",
               "sensitive_disclosure", "action_logging", "egress_containment"}


class SchemaTest(unittest.TestCase):
    def test_ids_unique(self):
        ids = [q["id"] for q in QS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_question_fully_tagged(self):
        profiles = set(META["profiles"])
        for q in QS:
            with self.subTest(q=q["id"]):
                self.assertTrue(q.get("question") and q.get("domain") and q.get("guidance"))
                self.assertIn(q["risk_weight"], range(1, 6))
                self.assertTrue(q.get("applies_to"))
                self.assertLessEqual(set(q["applies_to"]), profiles)
                self.assertEqual(len(q.get("options", [])), 4, "one option per maturity 0-3")
                self.assertTrue(all(isinstance(o, str) and o for o in q["options"]))
                # AI policy
                self.assertTrue(q.get("policy"))
                self.assertLessEqual(set(q["policy"]), POLICY_IDS)
                # compliance
                self.assertTrue(q.get("tags"))
                # NIST metric
                m = q.get("nist_metric") or {}
                self.assertTrue(m.get("subcategory") and m.get("metric") and m.get("target"))
                self.assertRegex(m["subcategory"], r"^(GOVERN|MAP|MEASURE|MANAGE) \d+\.\d+$")

    def test_tags_are_canonical(self):
        canon = META["clauses"]
        for q in QS:
            for fw, cls in q["tags"].items():
                with self.subTest(q=q["id"], fw=fw):
                    self.assertIn(fw, canon)
                    self.assertTrue(1 <= len(cls) <= 3, "keep to 1-3 clauses per framework")
                    self.assertLessEqual(set(cls), set(canon[fw]))

    def test_no_unused_canonical_clause(self):
        used = {(fw, c) for q in QS for fw, cls in q["tags"].items() for c in cls}
        for fw, cls in META["clauses"].items():
            for c in cls:
                self.assertIn((fw, c), used, f"{fw} {c} listed but never tagged")

    def test_tested_questions_use_known_lab_metric_and_only_agent_scope(self):
        """Lab evidence comes from a coding agent. It must not 'verify' MCP or app controls."""
        for q in QS:
            if q["type"] == "tested":
                with self.subTest(q=q["id"]):
                    self.assertIn(q["metric"], LAB_METRICS)
                    self.assertEqual(q["applies_to"], ["agent"])
            else:
                self.assertEqual(q["type"], "attested")
                self.assertNotIn("metric", q, "'metric' selects a verify branch; use nist_metric")

    def test_policy_clauses_all_evidenced(self):
        used = {p for q in QS for p in q["policy"]}
        self.assertEqual(used, POLICY_IDS)

    def test_no_em_dashes(self):
        for name in ("questions.json", "policy.json"):
            with open(os.path.join(ROOT, "grc", name), encoding="utf-8") as f:
                self.assertNotIn("—", f.read(), name)

    def test_example_answers_reference_real_questions(self):
        with open(os.path.join(ROOT, "grc", "answers.example.json")) as f:
            ans = json.load(f)
        ids = {q["id"] for q in QS}
        for k, v in ans.items():
            if k.startswith("_"):
                continue
            with self.subTest(k=k):
                self.assertIn(k, ids)
                if v.get("na"):
                    self.assertTrue(v.get("note"), "n/a needs a reason")
                else:
                    self.assertIn(v["maturity"], range(4))


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()  # empty results dir: no lab evidence

    def ids(self, profiles):
        return {r["id"] for r in assess.compute(answers={}, results_dir=self.d,
                                                profiles=profiles)["questions"]}

    def test_default_scores_everything(self):
        self.assertEqual(self.ids(None), {q["id"] for q in QS})

    def test_core_always_included(self):
        core = {q["id"] for q in QS if "core" in q["applies_to"]}
        for p in ("app", "agent", "mcp"):
            with self.subTest(p=p):
                got = self.ids([p])
                self.assertLessEqual(core, got)
                self.assertTrue(all(i in core or p in next(q for q in QS if q["id"] == i)["applies_to"]
                                    for i in got))

    def test_profiles_union(self):
        self.assertEqual(self.ids(["agent", "mcp"]), self.ids(["agent"]) | self.ids(["mcp"]))

    def test_policy_and_nist_rollups(self):
        out = assess.compute(answers={"GOV-1": {"maturity": 3}}, results_dir=self.d)
        self.assertEqual(set(out["policy"]), POLICY_IDS)
        p1 = out["policy"]["POL-01"]
        self.assertIn("GOV-1", p1["questions"])
        self.assertFalse(p1["compliant"])  # other POL-01 controls are unanswered
        n = sum(len(v) for v in out["nist_metrics"].values())
        self.assertEqual(n, len(QS))

    def test_not_applicable_excluded_but_listed(self):
        out = assess.compute(answers={"EU-2": {"na": True, "note": "not high-risk"}}, results_dir=self.d)
        self.assertNotIn("EU-2", {r["id"] for r in out["questions"]})
        self.assertEqual([n["id"] for n in out["not_applicable"]], ["EU-2"])

    def test_tested_question_cannot_be_not_applicable(self):
        out = assess.compute(answers={"ROBUST-1": {"na": True}}, results_dir=self.d)
        self.assertIn("ROBUST-1", {r["id"] for r in out["questions"]})

    def test_eu_ai_act_obligations_present(self):
        arts = {c for q in QS for c in q["tags"].get("EU AI Act", [])}
        for art in ("Art 4", "Art 5", "Art 9", "Art 12", "Art 13", "Art 14", "Art 15",
                    "Art 26", "Art 27", "Art 43", "Art 49", "Art 50", "Art 53", "Art 73"):
            self.assertIn(art, arts)

    def test_policy_met_when_all_controls_at_2(self):
        ans = {q["id"]: {"maturity": 2} for q in QS if "POL-12" in q["policy"]}
        out = assess.compute(answers=ans, results_dir=self.d)
        self.assertTrue(out["policy"]["POL-12"]["compliant"])


if __name__ == "__main__":
    unittest.main()
