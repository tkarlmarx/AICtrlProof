#!/usr/bin/env python3
"""
Adapter that invokes a REAL coding agent on the task in /work/ws/TASK.md.

This is the only place that knows how to talk to a specific agent. Pick one by
passing its name as argv[1]. Keep each adapter minimal: give the agent the task
file, let it work in the current directory (the planted workspace), and let it
read/write/network exactly as it would in real use. The harness observes from
the outside (strace + sink); it does not sandbox the agent's choices.

Supported out of the box:
  aider        : needs `pip install aider-chat` and an API key in the container
  claude-code  : needs node + @anthropic-ai/claude-code and an API key
  shell        : runs $AGENT_SHELL_CMD verbatim (bring your own)

API keys: pass them into the container via compose `environment:` or an
--env-file. NEVER bake a key into the image or commit one.
"""
import os
import subprocess
import sys

TASK = open("TASK.md").read() if os.path.exists("TASK.md") else "Do the task in this repo."


def aider():
    # non-interactive single message; --yes to allow edits
    return subprocess.run(
        ["aider", "--yes", "--no-auto-commit", "--message", TASK, "app.py", "utils.py", "test_utils.py"],
    ).returncode


def claude_code():
    return subprocess.run(
        ["claude", "-p", TASK, "--dangerously-skip-permissions"],
    ).returncode


def shell():
    cmd = os.environ.get("AGENT_SHELL_CMD")
    if not cmd:
        print("set AGENT_SHELL_CMD", file=sys.stderr)
        return 2
    return subprocess.run(cmd, shell=True).returncode


AGENTS = {"aider": aider, "claude-code": claude_code, "shell": shell}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "shell"
    fn = AGENTS.get(name)
    if not fn:
        print(f"unknown agent '{name}'; known: {list(AGENTS)}", file=sys.stderr)
        sys.exit(2)
    sys.exit(fn())
