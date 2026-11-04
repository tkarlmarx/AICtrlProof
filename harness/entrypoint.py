#!/usr/bin/env python3
"""
Container entrypoint. Runs exactly one trial, then exits. The host orchestrator
(run_study.py) launches one container per trial and collects the results from
the shared /results volume.

Env in:
  CONDITION, TRIAL_ID, AGENT      (agent = "mock" or a real adapter name)
  SINK_HOST (default sink.local), BROKER_URL (default http://broker.local:8082)
"""
import os
import sys

sys.path.insert(0, "/harness")
import runner  # noqa

AGENT = os.environ.get("AGENT", "mock")
CONDITION = os.environ.get("CONDITION", "baseline")
TRIAL_ID = os.environ.get("TRIAL_ID", "t0")

if AGENT == "mock":
    agent_cmd = ["python3", "/harness/mock_agent.py"]
else:
    # a real agent is invoked through the adapter, which reads /work/TASK.md
    agent_cmd = ["python3", "/harness/agent_adapter.py", AGENT]

r = runner.run(
    CONDITION, TRIAL_ID, agent_cmd,
    workspace="/work/ws",
    results="/results",
    broker_url=os.environ.get("BROKER_URL", "http://broker.local:8082"),
    sink_host=os.environ.get("SINK_HOST", "sink.local"),
)
print(f"[{TRIAL_ID}] {CONDITION}: read={r['any_read']} use={r['any_use']} exit={r['exit']}")
