#!/usr/bin/env bash
# One-command setup on an Ubuntu server with Docker installed.
# Builds the images, starts the two measurement services, and prints next steps.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Building images (sink, broker, agent)"
docker compose build
docker build -t agent-secrets-lab-agent -f agent/Dockerfile .

echo "==> Starting isolated services (sink + broker)"
docker compose up -d

echo "==> Detecting network name"
NET=$(docker network ls --format '{{.Name}}' | grep -E 'agent-secrets-lab.*lab' | head -1 || true)
echo "    network: ${NET:-not found}"

cat <<EOF

Ready.

Quick demo (mock agent, fast, no API key):
    LAB_NETWORK=${NET:-agent-secrets-lab_lab} python3 harness/run_study.py --trials 12 --agent mock

Full study (mock):
    LAB_NETWORK=${NET:-agent-secrets-lab_lab} python3 harness/run_study.py --trials 50 --agent mock

Real agent (example: claude-code), keys in keys.env (never committed):
    LAB_NETWORK=${NET:-agent-secrets-lab_lab} python3 harness/run_study.py --trials 50 --agent claude-code --env-file keys.env

Then open results/report.html in a browser, or serve it:
    python3 -m http.server --directory results 9000   # http://SERVER_IP:9000/report.html
EOF
