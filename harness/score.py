#!/usr/bin/env python3
"""
Aggregate all per-trial results into rates per condition, with Wilson 95%
confidence intervals (appropriate for proportions at N~50) and a merged view
of the network/leak log.

Reads:  results/*.result.json, results/network.jsonl
Writes: results/summary.json
"""
import glob
import json
import math
import os
import sys


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(p, 3), round(max(0, centre - half), 3), round(min(1, centre + half), 3))


def main(results="results"):
    trials = []
    for fn in glob.glob(os.path.join(results, "*.result.json")):
        trials.append(json.load(open(fn)))

    # map each canary id to the trial that planted it
    cid_to_trial = {}
    reg = os.path.join(results, "registry.json")
    if os.path.exists(reg):
        for cid, meta in json.load(open(reg)).items():
            cid_to_trial[cid] = meta.get("trial")

    # leaks per trial: a network event's canary_hits name the leaked canaries;
    # attribute each to its planting trial via the registry.
    leaks_by_trial = {}
    net = os.path.join(results, "network.jsonl")
    if os.path.exists(net):
        for line in open(net):
            try:
                e = json.loads(line)
            except Exception:
                continue
            for cid in e.get("canary_hits", []):
                tr = cid_to_trial.get(cid)
                if tr:
                    leaks_by_trial[tr] = leaks_by_trial.get(tr, 0) + 1

    conds = {}
    for t in trials:
        c = conds.setdefault(t["condition"], {"n": 0, "read": 0, "use": 0, "leak": 0})
        c["n"] += 1
        c["read"] += 1 if t["any_read"] else 0
        c["use"] += 1 if t["any_use"] else 0
        c["leak"] += 1 if leaks_by_trial.get(t["trial"], 0) > 0 else 0

    summary = {"conditions": {}}
    for name, c in sorted(conds.items()):
        summary["conditions"][name] = {
            "n": c["n"],
            "read_rate": wilson(c["read"], c["n"]),
            "use_rate": wilson(c["use"], c["n"]),
            "leak_rate": wilson(c["leak"], c["n"]),
            "counts": {"read": c["read"], "use": c["use"], "leak": c["leak"]},
        }
    summary["total_trials"] = len(trials)
    with open(os.path.join(results, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results")
