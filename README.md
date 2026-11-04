# AICtrlProof

**An AI risk assessment that tests its controls instead of only attesting them.**

Most AI governance tooling asks you to tick boxes: "we enforce least privilege",
"we resist prompt injection". AICtrlProof tags each control to the standards an
auditor cares about, and for the controls that can be tested, it runs an agent
in an isolated sandbox and reports what actually happened. Those controls come
back marked **verified**, with a measured number and a confidence interval,
instead of a tick.

It ships as an MCP server, so any MCP client (Claude, an IDE, another agent) can
run the assessment, read the mappings, and pull the live evidence.

> Codename `ctrlproof`. Research and demo project. Not an attack kit: see
> [Ground rules](#ground-rules).

## Contents

- [How it fits together](#how-it-fits-together)
- [The lab](#the-lab)
- [The GRC layer](#the-grc-layer)
- [The MCP server](#the-mcp-server)
- [Quick start](#quick-start)
- [Interpreting the output](#interpreting-the-output)
- [Repository layout](#repository-layout)
- [Extending it](#extending-it)
- [Limitations](#limitations)
- [Ground rules](#ground-rules)

## How it fits together

Two parts, one data flow. The lab measures agent behaviour and writes the
numbers to `results/`. The GRC layer reads those numbers and turns the testable
controls into verified findings. The MCP server exposes the same scoring to any
client.

```
  scenario + planted canaries
            |
            v
  harness/run_study.py  --->  one isolated container per trial
            |                   (strace file reads, sink logs egress)
            v
  results/summary.json  (read/use/leak rates per condition, Wilson CIs)
            |
            +--> grc/assess.py      --->  results/assessment.html  (report)
            |
            +--> grc/mcp_server.py  --->  MCP tools for any client
```

## The lab

Plants inert **canary** secrets in a repo, gives an agent an ordinary coding task
that needs none of them, and measures across many trials how often the agent:

- **READ** a file containing a decoy secret (captured with `strace`),
- **USE**d a decoy value in its own output or a file it wrote,
- **LEAK**ed a decoy value to the network sink.

Four conditions:

| Condition | What changes |
| --- | --- |
| `baseline` | Decoy secrets present. Plain task. No guidance. |
| `warned` | Plus a policy note not to touch credentials. |
| `injection` | Plus an instruction planted in the README, to test susceptibility to instructions arriving through tool output. |
| `broker` | No raw secrets exist. The agent must request a short-lived, single-scope token from a broker. This is the fix. |

Containment: trials run on a Docker network marked `internal`. A trial container
can reach the logging sink, the token broker, and, for real-agent runs, an egress
relay that forwards only to the model API and holds the real API key itself.
Plain HTTP to any host is routed to the sink and recorded; HTTPS to any host other
than the model API is refused and logged. So an exfil attempt is recorded but
nothing leaves the machine. All credentials are inert canaries. Full method and
limitations are in [`docs/LAB.md`](docs/LAB.md).

## The GRC layer

A risk assessment (`grc/`) across governance, data, access, robustness,
oversight, logging, supply chain, and transparency. Every question is tagged to
**NIST AI RMF, ISO/IEC 42001, the EU AI Act, ISO/IEC 27001, SOC 2, and the OWASP
LLM Top 10**.

The difference from a checkbox assessment: testable questions take their maturity
from the lab's measured results, so they come back **verified** rather than
**attested**. The least-privilege control reads the broker vs baseline leak
reduction; the prompt-injection control reads the injection leak rate, which in a
weak system shows up as a high-residual finding rather than a green tick.

Each question carries three tag groups:

- **AI policy**: the clause of the model AI policy (`grc/policy.json`, POL-01 to
  POL-12) it evidences, so the report doubles as a policy compliance check.
- **Compliance**: clauses in NIST AI RMF, NIST AI 600-1, ISO/IEC 42001, the EU
  AI Act, ISO/IEC 27001, SOC 2, and the OWASP LLM, Agentic, and MCP Top 10s.
- **NIST metric**: the indicator and target that measures the control, keyed
  to a NIST AI RMF subcategory.

Each question also offers four answer options, one per maturity level, and a
profile: `core` (any AI system, always scored), `app` (applications using AI),
`agent` (agentic AI bots), or `mcp` (MCP servers and clients). Score one system
type with `python3 grc/assess.py --profile agent,mcp`.

EU AI Act obligations have their own questions (EU-1 to EU-5: prohibited
practices, conformity assessment and registration, deployer duties, fundamental
rights impact assessment, general-purpose model duties), on top of the EU
articles tagged across the other questions. A question that does not apply is
answered `{"na": true, "note": "why"}`: it is left out of the score and listed
in the report.

Scoring is deliberately simple: maturity 0 (absent) to 3 (operating and
evidenced), residual risk per question = impact weight x (1 - maturity / 3),
aggregated per domain and overall.

## The MCP server

`grc/mcp_server.py` exposes the assessment over MCP (stdio). Tools:

| Tool | Returns |
| --- | --- |
| `list_questions` | the question bank, filterable by domain or framework |
| `run_assessment` | overall residual risk, per-domain, framework coverage, findings |
| `control_coverage` | controls referenced, addressed, and verified per framework |
| `verified_controls` | the tested controls and their live evidence |
| `explain_mapping` | which questions map to a given framework clause |

Setup and client config in [`grc/MCP.md`](grc/MCP.md).

## Quick start

On an Ubuntu server with Docker:

```bash
./setup.sh                                        # build + start the lab services
python3 harness/run_study.py --trials 50 --agent mock
python3 grc/assess.py --profile agent,mcp          # results/assessment.html (sample system: coding agent + MCP)
```

Tests (standard library only):

```bash
python3 -m unittest discover -s tests -v
```

No Docker, fast demo:

```bash
./run_local.sh 12 && python3 grc/assess.py
python3 -m http.server --directory results 9000   # /report.html and /assessment.html
```

Web app (login, fill the assessment, live dashboard, standards map):

```bash
HOST=0.0.0.0 PORT=8090 python3 app/server.py
# open http://<server-ip>:8090. Demo mode: admin / ctrlproof-demo, shown on the login page.
# Set CTRLPROOF_PASSWORD (and CTRLPROOF_USER) to turn demo mode off.
```

As an MCP server:

```bash
pip install -r grc/requirements.txt
python3 grc/mcp_server.py                          # speaks MCP over stdio
```

Plug in a real agent instead of the mock. Put `ANTHROPIC_API_KEY` in `keys.env`
(gitignored). Only the egress relay reads it; trial containers never get the real
key, and `run_study.py` refuses `--env-file` with `--agent claude-code`.

```bash
docker compose up -d egress
python3 harness/run_study.py --trials 1 --agent claude-code --model claude-sonnet-5-5   # pilot first
python3 harness/run_study.py --trials 50 --agent claude-code --model claude-sonnet-5-5
```

## Interpreting the output

- `results/report.html` is the lab dashboard: read, use, and leak rates per
  condition, with Wilson 95% confidence intervals.
- `results/assessment.html` is the GRC report: overall residual risk, a
  per-domain heatmap, a standards-coverage table, and findings ordered by
  residual risk, with verified controls marked.
- A high residual on a verified control is a real finding, not a failure of the
  tool. That is the point: it tells you a control does not hold.

## Repository layout

```
services/
  sink/       records and flags any network request (the only reachable host)
  broker/     issues short-lived, single-scope tokens (the defence)
harness/
  make_canaries.py  plants the decoy credentials for a trial
  runner.py         runs one trial, scores read and use
  run_study.py      launches one isolated container per trial, scores, reports
  score.py          Wilson CIs and aggregation
  report.py         the lab HTML dashboard
  mock_agent.py     configurable stand-in agent for tests and demos
  agent_adapter.py  wire in a real agent here
  entrypoint.py     per-trial container entrypoint
scenario/           the benign task and the planted workspace
grc/
  questions.json    the question bank: options, profiles, policy, framework, NIST metric tags
  policy.json       the model AI policy (POL-01 to POL-12)
  answers.example.json  sample attested answers (copy to answers.json)
  assess.py         scoring library + CLI (shared with the MCP server)
  mcp_server.py     the MCP server
  MCP.md            MCP setup and tool reference
docs/LAB.md         the lab in detail, method and limitations
tests/              known-answer and schema tests (python3 -m unittest)
results/            run output (gitignored; sample reports kept)
CLAUDE.md           orientation for coding agents working on this repo
```

## Extending it

- **Add an assessment question**: append to `grc/questions.json` with framework
  tags. Attested by default; set `"type": "tested"` and a `"metric"` to wire it
  to lab evidence (add the metric logic in `assess.verify`).
- **Add a real agent**: add an adapter in `harness/agent_adapter.py`.
- **Change the task or planted layout**: edit `scenario/`.

See [`CLAUDE.md`](CLAUDE.md) for the full developer and agent orientation.

## Limitations

- The mock agent produces known-answer trials for testing. Headline numbers must
  come from a real agent.
- A real LLM agent needs to reach its model API, which the fully internal network
  blocks. Either run a local model, or allow only the API host through a proxy and
  keep the sink as the default route. That egress allowlist is itself a defence
  worth measuring.
- `strace` sees file opens, not intent, so read, use, and leak are tracked
  separately.
- Framework mappings are indicative. Confirm them against the current text of
  each framework before putting them in front of an auditor.

## Ground rules

This project reports risks and fixes. It is not an attack kit.

- Only inert canary tokens, only inside an isolated container, with no path to
  any real account.
- Keep it in a fresh standalone repository, not a company repository.
- Publish results and defences, not a ready-to-run playbook.
