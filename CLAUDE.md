# CLAUDE.md

Orientation for Claude (and other coding agents) working in this repository.
Read this before changing anything. For the user-facing overview see
`README.md`; for lab method and limitations see `docs/LAB.md`.

## What this project is

AICtrlProof (codename `ctrlproof`) is an AI risk assessment whose testable
controls are **verified** by running an agent in an isolated sandbox, not merely
self-attested. It has three parts that share one data flow:

1. **The lab** measures how an agent handles decoy secrets it does not need.
2. **The GRC layer** scores a standards-mapped risk assessment and fills the
   testable controls from the lab's measured results.
3. **The MCP server** exposes the same scoring to any MCP client.

```
scenario + planted canaries
  -> harness/run_study.py (one isolated container per trial)
  -> results/summary.json  (read/use/leak rates per condition, Wilson CIs)
  -> grc/assess.py -> results/assessment.html
  -> grc/mcp_server.py -> MCP tools
```

## Key behaviours and invariants

Do not break these without saying so explicitly:

- **Containment.** Trial containers run only on a Docker network marked
  `internal`. They may reach two services and nothing else: `services/sink`
  (which records everything, including any plain HTTP a trial sends) and, for
  real-agent runs, the egress relay (`services/egress`). The relay is the single
  controlled exception: it forwards only to the model API host
  (`api.anthropic.com`), injects the real API key itself (trial containers hold
  only a placeholder key), refuses every other HTTPS destination, and logs every
  allow and deny to `results/egress.jsonl`. Do not add any other outbound path,
  do not widen the relay allowlist without the owner's approval, and never
  give a trial container the real key. Owner accepted this exception on
  2026-11-04.
- **Canaries are inert.** Every planted secret is a fake value with a unique
  `CANARY-<marker>`. Never plant a real credential, and never add a scenario that
  needs one.
- **Measurement honesty.** `read`, `use`, and `leak` are distinct signals. "Use"
  must count a canary only when it appears in the agent's own output or a file it
  created or changed, never in an untouched planted file (see
  `harness/runner.py`, the `original` comparison). Keep that guard.
- **Leak attribution is by canary id**, via `results/registry.json`, because the
  sink is one long-lived server and cannot know the trial id. Do not switch leak
  scoring back to a trial tag on the sink.
- **One scoring path.** `grc/assess.py` is the single source of scoring truth.
  The CLI and the MCP server both call `assess.compute`. Do not duplicate scoring
  logic in the server.

## How to run

```bash
# fast, no Docker (mock agent only), good for tests and demos
./run_local.sh 12 && python3 grc/assess.py

# full, isolated (Docker)
./setup.sh
python3 harness/run_study.py --trials 50 --agent mock
python3 grc/assess.py

# MCP server
pip install -r grc/requirements.txt
python3 grc/mcp_server.py
```

Tests: `python3 -m unittest discover -s tests -v` (standard library only). They
pin the lab scoring thresholds, Wilson intervals, leak attribution, the runner's
"use" guard, and the question bank schema. The end-to-end known-answer check is
still: a mock run should show `broker` at ~0% leak and `injection` with a clearly
higher leak than `baseline`. If it does not, scoring is broken.

## File map

| Path | Role |
| --- | --- |
| `services/sink/sink.py` | records every inbound request, flags canary hits, writes `results/network.jsonl` |
| `services/broker/broker.py` | issues short-lived scoped tokens, denies sensitive scopes, writes `results/broker.jsonl` |
| `harness/make_canaries.py` | plants decoy secrets, writes the trial's `canaries.json` |
| `harness/runner.py` | runs one trial, applies the condition, scores read and use |
| `harness/run_study.py` | host orchestrator: one container per trial, then score + report |
| `harness/score.py` | aggregates per-condition rates with Wilson 95% CIs |
| `harness/report.py` | the lab dashboard `results/report.html` |
| `harness/mock_agent.py` | configurable stand-in agent (profiles: careful, curious, leaky, obedient, broker) |
| `harness/agent_adapter.py` | wire a real agent here (aider, claude-code, shell) |
| `grc/questions.json` | the question bank: options, profile, AI policy, framework, and NIST metric tags; `meta.clauses` is the canonical clause list |
| `grc/policy.json` | the model AI policy, clauses POL-01 to POL-12 |
| `tests/` | known-answer and schema tests |
| `grc/assess.py` | scoring library + CLI; `compute`, `verify`, mapping helpers |
| `grc/mcp_server.py` | MCP server (SDK 2.x, `MCPServer`) over stdio |

## How to extend

- **Add an assessment question**: append to `grc/questions.json`. Give it a
  `domain`, `risk_weight` (1-5), `applies_to` (core, app, agent, mcp), four
  `options` (maturity 0-3), `policy` clause ids, framework `tags` (only clauses
  in `meta.clauses`; add new ones there first), a `nist_metric`
  (`subcategory`, `metric`, `target`), and `type`. The schema test enforces this.
  Only mark a question `tested` if the lab actually exercises that kind of
  system; MCP and app controls stay attested until a lab scenario covers them
  (note it in `lab_scenario`). Attested questions
  stop there. A `tested` question needs a `metric` string and a matching branch
  in `assess.verify` that reads `results/` and returns
  `(maturity 0-3, verified bool, evidence str)`.
- **Add a real agent**: add a function in `harness/agent_adapter.py` and register
  it in the `AGENTS` dict. It runs in `/work/ws` with `TASK.md` present.
- **Add an MCP tool**: decorate a function with `@app.tool(...)` in
  `grc/mcp_server.py` and delegate to `assess`.
- **Change the task or planted layout**: edit `scenario/`. Keep the task genuinely
  independent of any secret.

## Conventions

- Dependency-light on purpose. The lab and GRC layer use only the Python standard
  library. The only third-party dependency is `mcp`, and only for the server.
  Do not add dependencies without a clear reason.
- No em dashes or other AI-sounding punctuation in docs or generated reports.
- Keep any costing or commercial material simple, not multi-sheet models.
- Framework mappings are indicative. If you add or change a tag, keep it to a
  small number of real clauses and do not overclaim coverage.
- `results/` is gitignored except sample reports. Never commit canary values,
  trial logs, or API keys.

## Safety boundary

This repository studies agent security to report risks and defences. It must not
become an attack kit. Do not add: real credentials, a working exfiltration
destination, or a step-by-step attack playbook. If a change would make the repo
usable as a real attack rather than a measurement, stop and raise it.
