"""MCP server tools (grc/mcp_server.py), run without the real `mcp` package.

A fake `mcp.server.mcpserver.MCPServer` records each decorated tool and returns
the function unchanged, so every tool can be called directly. The fake modules
are removed from sys.modules afterwards so other tests are unaffected.
"""
import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRC = os.path.join(ROOT, "grc")
FAKE_MODULES = ("mcp", "mcp.server", "mcp.server.mcpserver")

TOOLS = {"list_profiles", "list_questions", "get_question", "run_assessment",
         "control_coverage", "policy_coverage", "nist_metrics",
         "verified_controls", "explain_mapping"}


class FakeMCPServer:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.tools = {}

    def tool(self, description=None, **kwargs):
        def register(fn):
            self.tools[fn.__name__] = {"fn": fn, "description": description}
            return fn
        return register

    def run(self, *args, **kwargs):
        raise AssertionError("tests must not start the server")


def load_server():
    saved = {name: sys.modules.get(name) for name in FAKE_MODULES}
    pkg = types.ModuleType("mcp")
    srv = types.ModuleType("mcp.server")
    mod = types.ModuleType("mcp.server.mcpserver")
    mod.MCPServer = FakeMCPServer
    pkg.server = srv
    srv.mcpserver = mod
    sys.modules.update({"mcp": pkg, "mcp.server": srv, "mcp.server.mcpserver": mod})
    try:
        spec = importlib.util.spec_from_file_location("ctrlproof_mcp_server_under_test",
                                                      os.path.join(GRC, "mcp_server.py"))
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        return server
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class MCPServerToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server()

    def test_fake_modules_removed(self):
        mod = sys.modules.get("mcp.server.mcpserver")
        self.assertIsNot(getattr(mod, "MCPServer", None), FakeMCPServer)

    def test_all_tools_registered(self):
        self.assertIsInstance(self.server.app, FakeMCPServer)
        self.assertEqual(set(self.server.app.tools), TOOLS)
        for name, t in self.server.app.tools.items():
            self.assertTrue(t["description"], name)

    def test_list_profiles(self):
        profiles = self.server.list_profiles()
        self.assertTrue({"core", "app", "agent", "mcp"} <= set(profiles))

    def test_list_questions_mcp_profile(self):
        qs = self.server.list_questions(profile="mcp")
        self.assertTrue(qs)
        ids = {q["id"] for q in qs}
        self.assertIn("MCP-1", ids)
        for q in qs:
            with self.subTest(id=q["id"]):
                applies = set(q["applies_to"])
                self.assertTrue(applies & {"core", "mcp"}, applies)
                self.assertIn("policy", q)
                self.assertIn("tags", q)
                self.assertIn("nist_metric", q)
                self.assertTrue(q["policy"])
                self.assertTrue(q["tags"])
                self.assertTrue(q["nist_metric"])
        # an agent-only or app-only question must not leak into the mcp profile
        everything = self.server.list_questions()
        others = [q["id"] for q in everything
                  if not set(q["applies_to"]) & {"core", "mcp"}]
        self.assertTrue(others)
        self.assertFalse(ids & set(others))

    def test_get_question(self):
        q = self.server.get_question("MCP-1")
        self.assertEqual(q["id"], "MCP-1")
        self.assertEqual(len(q["options"]), 4)
        self.assertIn("error", self.server.get_question("NOPE-99"))

    def test_run_assessment_mcp_attested(self):
        out = self.server.run_assessment(answers={}, profiles=["mcp"], use_lab_evidence=False)
        self.assertEqual(out["profiles"], ["core", "mcp"])
        self.assertIn("overall_residual", out)
        self.assertIn("frameworks", out)
        self.assertTrue(out["questions"])
        for r in out["questions"]:
            with self.subTest(id=r["id"]):
                self.assertEqual(set(r), {"id", "domain", "maturity", "verified", "residual", "evidence"})
                self.assertFalse(r["verified"])

    def test_control_coverage(self):
        cov = self.server.control_coverage("EU AI Act")
        self.assertEqual(set(cov), {"EU AI Act"})
        eu = cov["EU AI Act"]
        self.assertGreater(eu["total"], 0)
        self.assertLessEqual(eu["addressed"], eu["total"])
        self.assertLessEqual(eu["verified"], eu["addressed"])

    def test_policy_coverage(self):
        pol = self.server.policy_coverage()
        self.assertIn("POL-01", pol)
        self.assertTrue(all(k.startswith("POL-") for k in pol))

    def test_nist_metrics(self):
        nm = self.server.nist_metrics()
        self.assertTrue(nm)
        for sub, rows in nm.items():
            for row in rows:
                with self.subTest(sub=sub, id=row["id"]):
                    self.assertIn("metric", row)
                    self.assertIn("target", row)
                    self.assertIn("measured", row)

    def test_verified_controls(self):
        vc = self.server.verified_controls()
        self.assertIsInstance(vc, list)
        for row in vc:
            self.assertIn("id", row)
            self.assertIn("evidence", row)

    def test_explain_mapping(self):
        rows = self.server.explain_mapping("OWASP MCP")
        self.assertTrue(rows)
        self.assertIn("MCP-1", {r["id"] for r in rows})
        for r in rows:
            self.assertTrue(r["clauses"])


if __name__ == "__main__":
    unittest.main()
