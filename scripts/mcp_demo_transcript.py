"""Regenerate app/static/mcp-demo-transcript.json for the MCP demo tab.

Drives the real ctrlproof MCP server over stdio for the demo use case (a
third-party assessment of the invented vendor Forgepoint Pilot, answers from
scripts/seed_demo.py) and saves every tool call and its real result. Rerun it
after the question bank or the lab results change:

  python3 scripts/mcp_demo_transcript.py [path/to/python-with-mcp]
"""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "app", "static", "mcp-demo-transcript.json")
PY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".venv", "bin", "python")
sys.path[:0] = [os.path.join(ROOT, "scripts"), os.path.join(ROOT, "grc")]
import assess, seed_demo  # noqa: E402
_v = next(v for v in seed_demo.VENDORS if v["slug"] == "forgepoint-agent")
vendor = {"profiles": list(_v["profiles"]),
          "answers": seed_demo.build_answers(_v, assess.load_questions()["questions"])}
p = subprocess.Popen([PY, f"{ROOT}/grc/mcp_server.py"], cwd=ROOT,
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
n = [0]
def req(method, params):
    n[0] += 1
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n[0], "method": method, "params": params}) + "\n"); p.stdin.flush()
    while True:
        m = json.loads(p.stdout.readline())
        if m.get("id") == n[0]:
            return m
init = req("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "demo", "version": "1"}})
p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); p.stdin.flush()
tools = [t["name"] for t in req("tools/list", {})["result"]["tools"]]
def call(name, args):
    r = req("tools/call", {"name": name, "arguments": args})["result"]
    sc = r.get("structuredContent")
    if sc is None:
        sc = json.loads(r["content"][0]["text"])
    return sc
out = {"server": init["result"]["serverInfo"], "tools": tools, "vendor": _v["name"], "calls": []}
plan = [
  ("run_assessment", {"answers": vendor["answers"], "use_lab_evidence": False, "profiles": vendor["profiles"]}),
  ("control_coverage", {"framework": "EU AI Act", "profiles": vendor["profiles"]}),
  ("verified_controls", {}),
]
for name, args in plan:
    out["calls"].append({"tool": name, "args": {k: (f"<{len(v)} vendor answers>" if k == "answers" else v) for k, v in args.items()},
                         "result": call(name, args)})
json.dump(out, open(OUT, "w"), indent=1, default=str)
p.terminate()
