# ctrlproof MCP server

Exposes the AI risk assessment as MCP tools so any MCP client can run it, read
the standards mappings, and pull the controls that were verified against the
agent in the sandbox.

## Install and run

```bash
pip install -r grc/requirements.txt
python3 grc/mcp_server.py          # stdio transport
```

The server shares one scoring code path with the CLI (`grc/assess.py`), so the
tool results match `results/assessment.html`.

## Add to an MCP client

Most clients take a JSON config naming the command to launch. Point it at this
server. Example shape:

```json
{
  "mcpServers": {
    "ctrlproof": {
      "command": "python3",
      "args": ["/absolute/path/to/ctrlproof/grc/mcp_server.py"]
    }
  }
}
```

Put the real absolute path in. On Claude Desktop this goes in the
developer settings MCP config; other clients have their own file but the shape
is the same. Restart the client after editing.

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_questions` | `domain?`, `framework?` | the question bank, filtered |
| `run_assessment` | `answers?`, `use_lab_evidence?` | overall residual risk, per-domain, framework coverage, findings |
| `control_coverage` | `framework?` | controls referenced, addressed, verified per framework |
| `verified_controls` | none | the tested controls and their live evidence |
| `explain_mapping` | `framework`, `clause?` | which questions map to a framework clause |

`answers` maps a question id to `{"maturity": 0-3, "note": "..."}`. Tested
questions ignore it and fill from the lab when `use_lab_evidence` is true.

## Example calls

- "Assess this system" -> `run_assessment`.
- "What does NIST AI RMF MANAGE 2.1 map to here?" ->
  `explain_mapping("NIST AI RMF", "MANAGE 2.1")`.
- "Which controls are actually tested, and what did they show?" ->
  `verified_controls`.
- "How much of the EU AI Act do we touch?" ->
  `control_coverage("EU AI Act")`.

## Notes

- The server reads `results/summary.json` for the tested controls, so run a
  study first (`harness/run_study.py` or `run_local.sh`) to get live evidence.
  Without it, tested controls report no evidence rather than a false pass.
- Built for MCP SDK 2.x. If your client ships an older SDK, pin accordingly.
