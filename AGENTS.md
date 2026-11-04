# AGENTS.md

This repository's agent and developer orientation lives in
[`CLAUDE.md`](CLAUDE.md). It applies to any coding agent, not only Claude.

Read it before changing anything. In short:

- This is AICtrlProof, an AI risk assessment whose testable controls are verified
  by running an agent in an isolated sandbox, exposed over MCP.
- Invariants you must not break: trial containers stay network-isolated to the
  sink, planted secrets are always inert canaries, scoring lives only in
  `grc/assess.py`, and the repo must not become a usable attack kit.
- Run a fast check with `./run_local.sh 12 && python3 grc/assess.py`. A healthy
  run shows the `broker` condition near 0% leak and `injection` clearly above
  `baseline`.
