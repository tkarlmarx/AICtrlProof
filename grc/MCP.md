# ctrlproof MCP server

Exposes the AI risk assessment as MCP tools so any MCP client can run it, read
the standards mappings, and pull the controls that were verified against the
agent in the sandbox.

## Install and run

The server needs the `mcp` package (SDK 2.x, import path
`mcp.server.mcpserver`). Install it into a project venv, not the system Python:

```bash
cd /data/GitHub/AICtrlProof
python3 -m venv .venv
.venv/bin/pip install -r grc/requirements.txt
.venv/bin/python grc/mcp_server.py      # stdio transport; waits for a client
```

The server shares one scoring code path with the CLI (`grc/assess.py`), so the
tool results match `results/assessment.html`. `.venv/` is gitignored.

## Connect from Claude Code

```bash
claude mcp add ctrlproof -- /data/GitHub/AICtrlProof/.venv/bin/python /data/GitHub/AICtrlProof/grc/mcp_server.py
```

Add `--scope user` to make it available in every project, or `--scope project`
to write a shared `.mcp.json` in the current repo. Check it with
`claude mcp list` (it should show `ctrlproof` as connected), or type `/mcp`
inside a Claude Code session. Remove it with `claude mcp remove ctrlproof`.

## Connect from Claude Desktop and other clients

Most clients take a JSON config naming the command to launch. For Claude
Desktop, open Settings, Developer, Edit Config, and add:

```json
{
  "mcpServers": {
    "ctrlproof": {
      "command": "/data/GitHub/AICtrlProof/.venv/bin/python",
      "args": ["/data/GitHub/AICtrlProof/grc/mcp_server.py"]
    }
  }
}
```

Use absolute paths, and point `command` at the venv Python so the client finds
the `mcp` package. Restart the client after editing. Other clients (Cursor,
VS Code, other agents) use the same `command` and `args` shape in their own
config file.

## Smoke test

Proves the server starts and answers over stdio, with no MCP client needed. The
script is standard library only; it spawns the server, sends `initialize`,
`notifications/initialized`, `tools/list`, and one `tools/call` of
`run_assessment`:

```bash
python3 scripts/mcp_smoke.py --python .venv/bin/python
```

Expected output:

```
server: ctrlproof 0.2.0 (protocol 2025-06-18)
tools (9): list_profiles, list_questions, get_question, run_assessment, control_coverage, policy_coverage, nist_metrics, verified_controls, explain_mapping
run_assessment(profiles=['mcp']): overall_residual=1.0 severity=high questions=29 profiles=['core', 'mcp']
OK
```

The unit tests in `tests/test_mcp_server.py` call every tool function directly
with a stand-in for the `mcp` package, so they run without it:
`python3 -m unittest discover -s tests -v`.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_profiles` | none | system types: `core` (always), `app`, `agent`, `mcp` |
| `list_questions` | `domain?`, `framework?`, `profile?` | the question bank, filtered |
| `get_question` | `id` | one question with its 4 answer options, AI policy clauses, framework tags, NIST metric |
| `run_assessment` | `answers?`, `use_lab_evidence?`, `profiles?` | overall residual risk, per-domain, framework coverage, AI policy compliance, NIST metrics, findings |
| `control_coverage` | `framework?`, `profiles?` | controls referenced, addressed, verified per framework |
| `policy_coverage` | `answers?`, `profiles?` | per AI policy clause: controls at maturity 2+, verified, met or not |
| `nist_metrics` | `profiles?` | the NIST AI RMF metric and target for each control, measured or still to define |
| `verified_controls` | none | the tested controls and their live evidence |
| `explain_mapping` | `framework`, `clause?` | which questions map to a framework clause |

`answers` maps a question id to `{"maturity": 0-3, "note": "..."}`, where
maturity is the index of the chosen option from `get_question`, or
`{"na": true, "note": "why"}` for a question that does not apply. `profiles`
limits scope, for example `["agent", "mcp"]`; core questions always apply. Tested
questions ignore it and fill from the lab when `use_lab_evidence` is true.

## Example calls

- "Assess this system" -> `run_assessment`.
- "What does NIST AI RMF MANAGE 2.1 map to here?" ->
  `explain_mapping("NIST AI RMF", "MANAGE 2.1")`.
- "Which controls are actually tested, and what did they show?" ->
  `verified_controls`.
- "How much of the EU AI Act do we touch?" ->
  `control_coverage("EU AI Act")`.
- "Assess our MCP servers" -> `run_assessment(profiles=["mcp"])`.
- "Which AI policy clauses are we failing?" -> `policy_coverage`.
- "What should we measure for NIST?" -> `nist_metrics`.

## Demo prompts

Type these in Claude Code (or any connected client) to show the server off:

1. "Use ctrlproof to assess our MCP servers. Walk me through the questions one
   at a time and then score it."
2. "Which EU AI Act articles are we failing, and which questions would close
   the gaps?"
3. "Which of our controls are verified by a real sandbox test rather than
   self-attested, and what did the tests show?"
4. "Map OWASP MCP Top 10 to our questions and tell me which risks we have no
   control for."
5. "We are an agentic app with MCP tools. Run the assessment for the agent and
   mcp profiles and list the top five findings by residual risk."

## Notes

- The server reads `results/summary.json` for the tested controls, so run a
  study first (`harness/run_study.py` or `run_local.sh`) to get live evidence.
  Without it, tested controls report no evidence rather than a false pass.
- Built for MCP SDK 2.x (`from mcp.server.mcpserver import MCPServer`); tested
  with `mcp` 2.3.0. SDK 1.x used a different import path and is not supported.
