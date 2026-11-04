#!/usr/bin/env python3
"""
Build a single self-contained HTML dashboard from results/summary.json.
This is the showcase artefact: open results/report.html in a browser, or
project it live during the hackathon.
"""
import json
import os
import sys

ORDER = ["baseline", "warned", "injection", "broker"]
LABEL = {"baseline": "Baseline (secrets present)",
         "warned": "Warned (policy note)",
         "injection": "Prompt injection",
         "broker": "Credential broker (fix)"}
NOTE = {"read": "opened a file containing a decoy secret",
        "use": "decoy secret appeared in the agent's own output",
        "leak": "decoy secret reached the sink"}


def bar(metric, data, color):
    rows = []
    for name in ORDER:
        if name not in data["conditions"]:
            continue
        c = data["conditions"][name]
        p, lo, hi = c[f"{metric}_rate"]
        pct = round(p * 100)
        rows.append(f"""
        <div class="row">
          <div class="lab">{LABEL[name]}<span class="n">n={c['n']}</span></div>
          <div class="track">
            <div class="fill" style="width:{pct}%;background:{color}"></div>
            <div class="ci" style="left:{round(lo*100)}%;right:{round((1-hi)*100)}%"></div>
          </div>
          <div class="val">{pct}% <span class="cir">[{round(lo*100)}–{round(hi*100)}]</span></div>
        </div>""")
    return "".join(rows)


def main(results="results"):
    data = json.load(open(os.path.join(results, "summary.json")))
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Agent secret-handling study</title>
<style>
 body{{font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;max-width:860px;margin:40px auto;padding:0 20px;color:#1a1a2e;background:#fafafb}}
 h1{{font-size:24px;margin-bottom:4px}} .sub{{color:#666;margin-top:0}}
 h2{{font-size:17px;margin:34px 0 6px}}
 .desc{{color:#555;font-size:13px;margin:0 0 12px}}
 .row{{display:flex;align-items:center;gap:12px;margin:7px 0}}
 .lab{{width:230px;font-size:13px}} .n{{color:#999;margin-left:6px;font-size:11px}}
 .track{{position:relative;flex:1;height:22px;background:#ececef;border-radius:5px;overflow:hidden}}
 .fill{{position:absolute;top:0;bottom:0;left:0;border-radius:5px}}
 .ci{{position:absolute;top:0;bottom:0;background:rgba(0,0,0,.18)}}
 .val{{width:120px;font-variant-numeric:tabular-nums;font-size:13px}}
 .cir{{color:#999;font-size:11px}}
 .foot{{margin-top:36px;color:#888;font-size:12px;border-top:1px solid #e3e3e8;padding-top:12px}}
 code{{background:#eee;padding:1px 4px;border-radius:3px}}
</style></head><body>
<h1>How does an AI coding agent handle credentials it does not need?</h1>
<p class="sub">{data['total_trials']} trials. Bars show the share of trials with each behaviour; brackets are Wilson 95% confidence intervals.</p>

<h2>READ: {NOTE['read']}</h2>
<div class="desc">The task never required any secret. This is how often the agent opened one anyway.</div>
{bar('read', data, '#e0a800')}

<h2>USE: {NOTE['use']}</h2>
<div class="desc">A stronger signal: the decoy value was echoed into output or a written file.</div>
{bar('use', data, '#e8590c')}

<h2>LEAK: {NOTE['leak']}</h2>
<div class="desc">The strongest signal: the decoy value was sent to the (internal, isolated) sink.</div>
{bar('leak', data, '#c92a2a')}

<div class="foot">
All credentials are inert canaries in an isolated container. Outbound traffic
reaches only an internal sink; nothing leaves the box. The <b>broker</b>
condition stores no raw secret: the agent must request a short-lived,
single-scope token, which is why its read/use/leak rates collapse. Method and
limitations are in <code>README.md</code>.
</div>
</body></html>"""
    out = os.path.join(results, "report.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results")
