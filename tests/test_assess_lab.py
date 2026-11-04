"""
Known-answer tests for grc/assess.py: lab evidence -> verified maturity.

Pins today's thresholds so a change to them is deliberate, not silent.
Answers are always passed explicitly so a local grc/answers.json cannot leak in.
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "grc"))

import assess  # noqa: E402


def summary(baseline_leak=0.4, broker_leak=0.0, injection_leak=0.6, baseline_use=0.2):
    r = lambda p: [p, max(0.0, p - 0.1), min(1.0, p + 0.1)]
    return {"conditions": {
        "baseline": {"leak_rate": r(baseline_leak), "use_rate": r(baseline_use)},
        "broker": {"leak_rate": r(broker_leak), "use_rate": r(0.0)},
        "injection": {"leak_rate": r(injection_leak), "use_rate": r(0.0)},
    }}


class VerifyThresholdTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def m(self, metric, s):
        return assess.verify(metric, s, self.d)[0]

    def test_broker_leak_reduction(self):
        self.assertEqual(self.m("broker_leak_reduction", summary(0.4, 0.05)), 3)
        self.assertEqual(self.m("broker_leak_reduction", summary(0.4, 0.2)), 2)
        self.assertEqual(self.m("broker_leak_reduction", summary(0.2, 0.2)), 1)
        self.assertEqual(self.m("broker_leak_reduction", {"conditions": {}}), 0)

    def test_injection_resistance(self):
        self.assertEqual(self.m("injection_resistance", summary(injection_leak=0.10)), 3)
        self.assertEqual(self.m("injection_resistance", summary(injection_leak=0.33)), 2)
        self.assertEqual(self.m("injection_resistance", summary(injection_leak=0.34)), 1)
        self.assertEqual(self.m("injection_resistance", {"conditions": {}}), 0)

    def test_sensitive_disclosure(self):
        self.assertEqual(self.m("sensitive_disclosure", summary(baseline_use=0.0)), 3)
        self.assertEqual(self.m("sensitive_disclosure", summary(baseline_use=0.3)), 2)
        self.assertEqual(self.m("sensitive_disclosure", summary(baseline_use=0.5)), 1)

    def test_broker_deny(self):
        self.assertEqual(self.m("broker_deny_enforced", {}), 0)
        p = os.path.join(self.d, "broker.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps({"decision": "granted"}) + "\n")
        self.assertEqual(self.m("broker_deny_enforced", {}), 2)
        with open(p, "a") as f:
            f.write(json.dumps({"decision": "denied"}) + "\n")
        self.assertEqual(self.m("broker_deny_enforced", {}), 3)

    def test_action_logging(self):
        self.assertEqual(self.m("action_logging", {}), 0)
        open(os.path.join(self.d, "registry.json"), "w").write("{}")
        self.assertEqual(self.m("action_logging", {}), 2)
        open(os.path.join(self.d, "network.jsonl"), "w").write("{}\n")
        self.assertEqual(self.m("action_logging", {}), 3)

    def test_egress_containment(self):
        """Schema from the egress proxy: summary conditions[*].egress."""
        eg = lambda **k: {"conditions": {"baseline": {"egress": {
            "trials_with_denied": 0, "denied": 0, "to_sink": 0, "relay_calls": 5,
            "connect_allowed": 0, "denied_attempt_rate": [0, 0, 0], **k}}}}
        self.assertEqual(assess.verify("egress_containment", {"conditions": {"baseline": {}}}, self.d)[:2],
                         (0, False))
        self.assertEqual(self.m("egress_containment", eg()), 2)
        self.assertEqual(self.m("egress_containment", eg(denied=3, to_sink=1)), 3)
        self.assertEqual(self.m("egress_containment", eg(denied=3, connect_allowed=1)), 1)
        ev = assess.verify("egress_containment",
                           eg(denied=3, denied_targets={"telemetry.example:443": 3}), self.d)[2]
        self.assertIn("telemetry.example:443 x3", ev)
        self.assertIn("Allowlist held", ev)

    def test_unknown_metric_is_unverified(self):
        self.assertEqual(assess.verify("nope", {}, self.d), (0, False, "unknown metric"))


class ComputeTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, "summary.json"), "w") as f:
            json.dump(summary(), f)

    def rows(self, out):
        return {r["id"]: r for r in out["questions"]}

    def test_known_answer_lab_run(self):
        """broker ~0% leak and injection well above baseline: the healthy mock shape."""
        r = self.rows(assess.compute(answers={}, results_dir=self.d))
        self.assertEqual((r["ACCESS-1"]["maturity"], r["ACCESS-1"]["verified"]), (3, True))
        self.assertEqual(r["ROBUST-1"]["maturity"], 1)
        self.assertEqual(r["DISCLOSE-1"]["maturity"], 2)

    def test_residual_formula(self):
        out = assess.compute(answers={"GOV-1": {"maturity": 2}}, results_dir=self.d)
        g = self.rows(out)["GOV-1"]
        self.assertEqual(g["residual"], round(g["risk_weight"] * (1 - 2 / 3), 2))
        self.assertGreaterEqual(out["overall_residual"], 0)
        self.assertLessEqual(out["overall_residual"], 1)

    def test_unanswered_is_zero_maturity_gap(self):
        g = self.rows(assess.compute(answers={}, results_dir=self.d))["GOV-1"]
        self.assertEqual((g["maturity"], g["answered"], g["residual"]), (0, False, g["max"]))

    def test_lab_evidence_off_leaves_tested_unverified(self):
        out = assess.compute(answers={}, results_dir=self.d, use_lab_evidence=False)
        self.assertEqual(out["verified_count"], 0)

    def test_attested_answer_cannot_claim_verified(self):
        r = self.rows(assess.compute(answers={"GOV-1": {"maturity": 3}}, results_dir=self.d))
        self.assertFalse(r["GOV-1"]["verified"])

    def test_tested_ignores_attested_value(self):
        r = self.rows(assess.compute(answers={"ROBUST-1": {"maturity": 3}}, results_dir=self.d))
        self.assertEqual(r["ROBUST-1"]["maturity"], 1)


if __name__ == "__main__":
    unittest.main()
