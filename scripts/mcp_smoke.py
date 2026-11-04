#!/usr/bin/env python3
"""Smoke test for the ctrlproof MCP server over stdio (standard library only).

Spawns grc/mcp_server.py, sends initialize, notifications/initialized,
tools/list, and one tools/call (run_assessment), and prints what came back.

Usage:
  python3 scripts/mcp_smoke.py                     # server runs with this python
  python3 scripts/mcp_smoke.py --python .venv/bin/python
Exit code 0 means the server answered every request.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "grc", "mcp_server.py")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter that has the mcp package (default: this one)")
    a = ap.parse_args(argv)

    proc = subprocess.Popen([a.python, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, bufsize=1)  # server stderr passes through

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def request(id_, method, params):
        send({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SystemExit(f"server closed stdout during {method} (see its stderr above)")
            msg = json.loads(line)
            if msg.get("id") == id_:
                if "error" in msg:
                    raise SystemExit(f"{method} failed: {msg['error']}")
                return msg["result"]

    try:
        init = request(1, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ctrlproof-smoke", "version": "0.1"},
        })
        info = init.get("serverInfo", {})
        print(f"server: {info.get('name')} {info.get('version')} "
              f"(protocol {init.get('protocolVersion')})")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        tools = request(2, "tools/list", {})["tools"]
        names = [t["name"] for t in tools]
        print(f"tools ({len(names)}): " + ", ".join(names))

        res = request(3, "tools/call", {"name": "run_assessment", "arguments": {
            "answers": {}, "profiles": ["mcp"], "use_lab_evidence": False}})
        if res.get("isError"):
            raise SystemExit(f"run_assessment returned an error: {res}")
        data = res.get("structuredContent")
        if data is None:
            text = next((c["text"] for c in res.get("content", []) if c.get("type") == "text"), "{}")
            data = json.loads(text)
        data = data.get("result", data) if isinstance(data, dict) else data
        print(f"run_assessment(profiles=['mcp']): overall_residual={data.get('overall_residual')} "
              f"severity={data.get('overall_sev')} questions={len(data.get('questions', []))} "
              f"profiles={data.get('profiles')}")
        print("OK")
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
