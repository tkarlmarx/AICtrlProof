#!/usr/bin/env python3
"""Pretty-print results/summary.json as a terminal table for the live demo."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(ROOT, "results", "summary.json")))
order = ["baseline", "warned", "injection", "broker"]


def cell(v, m):
    p, lo, hi = v[m]
    return f"{int(p*100):3d}% [{int(lo*100)}-{int(hi*100)}]"


print(f"\n  {d['total_trials']} trials total\n")
print(f"  {'condition':12}{'n':>4}   {'READ':>12}{'USE':>12}{'LEAK':>12}")
print("  " + "-" * 54)
for k in order:
    if k not in d["conditions"]:
        continue
    v = d["conditions"][k]
    print(f"  {k:12}{v['n']:>4}   {cell(v,'read_rate'):>12}{cell(v,'use_rate'):>12}{cell(v,'leak_rate'):>12}")
print("\n  READ=opened a decoy file  USE=value in agent output  LEAK=value reached sink")
print("  brackets = Wilson 95% CI\n")
