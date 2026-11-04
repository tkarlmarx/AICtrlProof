#!/usr/bin/env python3
"""
Study orchestrator (host side).

Launches one fresh, isolated container per trial on the lab's internal network,
runs every condition N times, then scores and builds the report.

Usage:
  python3 harness/run_study.py --trials 50 --agent mock
  python3 harness/run_study.py --trials 50 --agent claude-code --env-file keys.env

Prereqs: `docker compose up -d --build` has started sink + broker.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONDITIONS = ["baseline", "warned", "injection", "broker"]
NETWORK = os.environ.get("LAB_NETWORK", "agent-secrets-lab_lab")
IMAGE = os.environ.get("AGENT_IMAGE", "agent-secrets-lab-agent")


def docker_run(condition, trial_id, agent, env_file):
    cmd = [
        "docker", "run", "--rm",
        "--network", NETWORK,
        "--cap-add", "SYS_PTRACE",          # strace needs this
        "--security-opt", "no-new-privileges",
        "--pids-limit", "256",
        "--memory", "1g",
        "-v", f"{ROOT}/results:/results",
        "-e", f"CONDITION={condition}",
        "-e", f"TRIAL_ID={trial_id}",
        "-e", f"AGENT={agent}",
    ]
    if env_file:
        cmd += ["--env-file", env_file]
    cmd += [IMAGE]
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=50, help="trials PER condition")
    ap.add_argument("--agent", default="mock")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--conditions", nargs="+", default=CONDITIONS)
    a = ap.parse_args()

    # fresh run
    for fn in os.listdir(f"{ROOT}/results"):
        if fn.endswith((".result.json", ".strace", ".out")):
            os.remove(f"{ROOT}/results/{fn}")
    for fn in ("network.jsonl", "broker.jsonl", "registry.json"):
        p = f"{ROOT}/results/{fn}"
        if os.path.exists(p):
            os.remove(p)
    json.dump({}, open(f"{ROOT}/results/registry.json", "w"))

    total = len(a.conditions) * a.trials
    done = 0
    t0 = time.time()
    for cond in a.conditions:
        for i in range(1, a.trials + 1):
            tid = f"{cond}_{i:03d}"
            docker_run(cond, tid, a.agent, a.env_file)
            done += 1
            if done % 10 == 0 or done == total:
                el = time.time() - t0
                print(f"  {done}/{total} trials ({el:.0f}s)", flush=True)

    subprocess.run([sys.executable, f"{HERE}/score.py", f"{ROOT}/results"], check=True)
    subprocess.run([sys.executable, f"{HERE}/report.py", f"{ROOT}/results"], check=True)
    print(f"\nDone. Open {ROOT}/results/report.html")


if __name__ == "__main__":
    main()
