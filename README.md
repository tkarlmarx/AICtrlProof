# ctrlproof

An AI risk assessment that tests its controls instead of only attesting them.

Most AI governance tooling asks you to tick boxes: "we enforce least privilege",
"we resist prompt injection". ctrlproof tags each control to the standards an
auditor cares about, and for the controls that can be tested, it runs an agent
in an isolated sandbox and reports what actually happened. Those controls come
back marked **verified**, with a number and a confidence interval, not a tick.

It is exposed as an MCP server, so any MCP client (Claude, an IDE, another
agent) can run the assessment, read the mappings, and pull the live evidence.

## Two parts

**The lab** (`services/`, `harness/`, `scenario/`) plants inert canary secrets in
a repo, gives an agent a task that needs none of them, and measures across many
trials how often the agent reads, uses, or leaks them, under four conditions
including a credential-broker defence. Everything runs in a container whose only
reachable host is an internal sink, so nothing can leave the machine. Full
detail in [`docs/LAB.md`](docs/LAB.md).

**The GRC layer** (`grc/`) is the risk assessment: a question bank across
governance, data, access, robustness, oversight, logging, supply chain, and
transparency, each question tagged to NIST AI RMF, ISO/IEC 42001, the EU AI Act,
ISO/IEC 27001, SOC 2, and the OWASP LLM Top 10. Testable questions take their
maturity from the lab's measured results.

## Quick start

```bash
./setup.sh                                        # build + start the lab services
python3 harness/run_study.py --trials 50 --agent mock
python3 grc/assess.py                             # build results/assessment.html
```

No Docker, for a fast demo:

```bash
./run_local.sh 12 && python3 grc/assess.py
python3 -m http.server --directory results 9000   # /report.html and /assessment.html
```

## As an MCP server

```bash
pip install -r grc/requirements.txt
python3 grc/mcp_server.py        # speaks MCP over stdio
```

Tools: `list_questions`, `run_assessment`, `control_coverage`,
`verified_controls`, `explain_mapping`. Client setup and the tool reference are
in [`grc/MCP.md`](grc/MCP.md).

## Layout

```
services/      sink (records any egress) and broker (short-lived scoped tokens)
harness/       canary planting, trial runner, study orchestrator, scoring, report
scenario/      the benign task and the planted workspace
grc/           questions.json, assess.py, mcp_server.py, MCP.md
docs/LAB.md    the lab in detail, method and limitations
```

## Ground rules

This project reports risks and fixes. It is not an attack kit.

- Only inert canary tokens, only inside an isolated container, with no path to
  any real account.
- Keep it in a fresh standalone repository, not a company repository.
- Publish results and defences, not a ready-to-run playbook.
- Framework mappings are indicative. Confirm them against the current text of
  each framework before putting them in front of an auditor.
