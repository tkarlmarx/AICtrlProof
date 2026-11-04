#!/usr/bin/env bash
# No-Docker runner: starts the sink and broker as local processes and runs the
# study with the mock agent. Instant, good for a live demo. Containment here is
# weaker than the Docker path (processes share the host), so use ONLY the mock
# agent with it. For a real agent, use the Docker path (setup.sh + run_study.py).
set -euo pipefail
cd "$(dirname "$0")"
L="$(pwd)"
N="${1:-12}"   # trials per behaviour group

echo "==> starting services"
fuser -k 8081/tcp 8082/tcp 2>/dev/null || true
sleep 1
mkdir -p results run
rm -f results/*.result.json results/*.strace results/*.out \
      results/network.jsonl results/broker.jsonl results/registry.json
echo '{}' > results/registry.json
setsid env SINK_LOG="$L/results/network.jsonl" CANARY_FILE="$L/results/registry.json" PORT=8081 \
    python3 "$L/services/sink/sink.py" >/tmp/lab-sink.log 2>&1 &
setsid env BROKER_LOG="$L/results/broker.jsonl" PORT=8082 \
    python3 "$L/services/broker/broker.py" >/tmp/lab-broker.log 2>&1 &
sleep 2

trial(){ SINK_HOST=127.0.0.1 BROKER_URL=http://127.0.0.1:8082 MOCK_PROFILE="$2" \
  python3 harness/runner.py --condition "$1" --trial-id "$3" \
    --workspace "$L/run/ws_$3" --results "$L/results" -- python3 "$L/harness/mock_agent.py" >/dev/null 2>&1; }

echo "==> running trials"
# baseline: a spread of behaviours
for i in $(seq 1 $N); do
  case $((i % 4)) in 0) p=leaky;; 1) p=curious;; *) p=careful;; esac
  trial baseline "$p" "baseline_$i"
done
for i in $(seq 1 $N); do trial warned careful "warned_$i"; done
for i in $(seq 1 $N); do
  [ $((i % 5)) -eq 0 ] && p=careful || p=obedient
  trial injection "$p" "injection_$i"
done
for i in $(seq 1 $N); do trial broker broker "broker_$i"; done

echo "==> scoring"
python3 harness/score.py results >/dev/null
python3 harness/report.py results >/dev/null
python3 harness/print_summary.py
echo
echo "Report: $L/results/report.html"
echo "Serve it:  python3 -m http.server --directory results 9000"
