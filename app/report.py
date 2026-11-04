"""
Standalone HTML report for one scored assessment plus its review.

  render_report(assessment, scored, review) -> str

Self-contained: inline CSS, no scripts, no external assets, print-friendly.
Every string that comes from the vendor or from the review is escaped.
"""
import html
import time

SEV_COLOR = {"low": "#1f7a4d", "medium": "#a86500", "high": "#b3261e"}


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def _date(ts):
    try:
        return time.strftime("%d %b %Y", time.localtime(int(ts))) if ts else ""
    except Exception:
        return ""


def _pct(f):
    return f"{round((f or 0) * 100)}%"


def _badge(sev):
    sev = sev if sev in SEV_COLOR else "high"
    return f'<span class="badge {sev}">{e(sev)}</span>'


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f6f7f9;color:#1d2330;font:14px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1040px;margin:0 auto;padding:32px 24px 48px;background:#fff}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:17px;margin:32px 0 10px;padding-bottom:6px;border-bottom:1px solid #e3e6eb}
h3{font-size:14px;margin:18px 0 6px}
p{margin:6px 0}
.muted{color:#5b6475}
.small{font-size:12px}
.head{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;align-items:flex-start}
.meta{display:grid;grid-template-columns:auto auto;gap:2px 14px;font-size:13px}
.meta dt{color:#5b6475}.meta dd{margin:0}
.score{display:flex;gap:16px;margin-top:20px;flex-wrap:wrap}
.tile{border:1px solid #e3e6eb;border-radius:8px;padding:12px 16px;min-width:150px}
.tile .v{font-size:26px;font-weight:600}
.tile .l{font-size:12px;color:#5b6475}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;color:#fff;text-transform:uppercase;letter-spacing:.03em}
.badge.low{background:#1f7a4d}.badge.medium{background:#a86500}.badge.high{background:#b3261e}
.ok{color:#1f7a4d;font-weight:600}.no{color:#b3261e;font-weight:600}
table{width:100%;border-collapse:collapse;margin:6px 0 4px;font-size:13px}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid #eceef2}
th{background:#f3f5f8;font-weight:600;font-size:12px;color:#3a4252}
td.num,th.num{text-align:right;white-space:nowrap}
.review{background:#f8f9fb;border:1px solid #e3e6eb;border-radius:8px;padding:14px 18px}
.label{font-size:12px;color:#5b6475;margin-bottom:6px}
ol,ul{margin:6px 0;padding-left:22px}
li{margin:4px 0}
.tags{font-size:12px;color:#3a4252}
.tags b{font-weight:600}
.note{white-space:pre-wrap;word-break:break-word}
.id{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;white-space:nowrap}
footer{margin-top:36px;padding-top:10px;border-top:1px solid #e3e6eb;font-size:12px;color:#5b6475}
@media print{
  body{background:#fff;font-size:11px}
  main{max-width:none;padding:0}
  h2{break-after:avoid;page-break-after:avoid}
  tr,.tile,.review li{break-inside:avoid;page-break-inside:avoid}
  thead{display:table-header-group}
  .review{background:#fff}
  .badge{border:1px solid #000;color:#000 !important;background:#fff !important}
  @page{margin:14mm}
}
"""


def _review_html(review):
    if not review:
        return "<p class=muted>No review available.</p>"
    if review.get("mode") == "claude":
        label = f"AI review by Claude ({e(review.get('model') or 'model unknown')})"
    else:
        label = "Rule-based review (offline, not produced by an AI model)"
    gen = _date(review.get("generated_at"))
    out = [f'<div class="review"><div class="label">{label}{", " + e(gen) if gen else ""}</div>',
           f"<p>{e(review.get('summary'))}</p>"]
    risks = review.get("top_risks") or []
    if risks:
        out.append("<h3>Top risks</h3><ol>")
        for t in risks:
            out.append(f"<li><span class=id>{e(t.get('id'))}</span> <b>{e(t.get('title'))}</b>"
                       f"<br><span class=muted>{e(t.get('why'))}</span>"
                       f"<br>Fix: {e(t.get('fix'))}</li>")
        out.append("</ol>")
    flags = review.get("red_flags") or []
    out.append("<h3>Red flags</h3>")
    if flags:
        out.append("<ul>" + "".join(f"<li><span class=id>{e(f.get('id'))}</span> {e(f.get('issue'))}</li>"
                                    for f in flags) + "</ul>")
    else:
        out.append("<p class=muted>None found.</p>")
    fu = review.get("follow_up_questions") or []
    if fu:
        out.append("<h3>Follow-up questions for the vendor</h3><ol>"
                   + "".join(f"<li>{e(q)}</li>" for q in fu) + "</ol>")
    out.append("</div>")
    return "".join(out)


def _tags_html(r):
    bits = []
    if r.get("policy"):
        bits.append(f"<b>AI policy:</b> {e(', '.join(r['policy']))}")
    for fw, cls in (r.get("tags") or {}).items():
        bits.append(f"<b>{e(fw)}:</b> {e(', '.join(cls))}")
    m = r.get("nist_metric")
    if m:
        bits.append(f"<b>NIST metric ({e(m.get('subcategory'))}):</b> {e(m.get('metric'))}, "
                    f"target {e(m.get('target'))}")
    return "<br>".join(bits)


def render_report(assessment, scored, review):
    a, s = assessment or {}, scored or {}
    rows = s.get("questions", [])
    answered = sum(1 for r in rows if r.get("answered"))
    sev = s.get("overall_sev", "high")
    rating = (review or {}).get("rating") or sev
    date = _date(a.get("submitted_at")) or _date(a.get("updated")) or _date(a.get("created"))
    profiles = ", ".join(a.get("profiles") or []) or "all"

    h = ["<!DOCTYPE html><html lang=en><head><meta charset=utf-8>",
         '<meta name=viewport content="width=device-width,initial-scale=1">',
         f"<title>{e(a.get('org'))}: {e(a.get('name'))} AI risk report</title>",
         f"<style>{CSS}</style></head><body><main>"]

    # header
    h.append('<div class="head"><div>'
             f'<div class="muted small">AI risk assessment report</div>'
             f"<h1>{e(a.get('org'))}</h1>"
             f"<div>{e(a.get('name'))}</div></div>"
             '<dl class="meta">'
             f"<dt>Status</dt><dd>{e(a.get('status'))}</dd>"
             f"<dt>Type</dt><dd>{e(a.get('kind'))}</dd>"
             f"<dt>Profiles</dt><dd>{e(profiles)}</dd>"
             f"<dt>Date</dt><dd>{e(date)}</dd>"
             f"<dt>Report generated</dt><dd>{e(_date(time.time()))}</dd>"
             "</dl></div>")
    h.append('<div class="score">'
             f'<div class="tile"><div class="v">{_pct(s.get("overall_residual"))}</div>'
             f'<div class="l">Overall residual risk</div></div>'
             f'<div class="tile"><div class="v">{_badge(rating)}</div><div class="l">Rating</div></div>'
             f'<div class="tile"><div class="v">{answered}/{len(rows)}</div>'
             f'<div class="l">In-scope questions answered</div></div>'
             f'<div class="tile"><div class="v">{len(s.get("not_applicable", []))}</div>'
             f'<div class="l">Marked not applicable</div></div></div>')

    # review
    h.append("<h2>Review</h2>" + _review_html(review))

    # domains
    h.append("<h2>Domains</h2><table><thead><tr><th>Domain</th><th class=num>Questions</th>"
             "<th class=num>Below maturity 2</th><th class=num>Residual</th><th>Severity</th>"
             "</tr></thead><tbody>")
    for name, d in sorted(s.get("domains", {}).items(), key=lambda kv: -kv[1].get("frac", 0)):
        h.append(f"<tr><td>{e(name)}</td><td class=num>{d.get('n', 0)}</td>"
                 f"<td class=num>{d.get('gaps', 0)}</td><td class=num>{_pct(d.get('frac'))}</td>"
                 f"<td>{_badge(d.get('sev'))}</td></tr>")
    h.append("</tbody></table>")

    # frameworks
    h.append("<h2>Framework coverage</h2><table><thead><tr><th>Framework</th>"
             "<th class=num>Clauses mapped</th><th class=num>Addressed</th>"
             "<th class=num>Verified</th><th class=num>Gaps</th></tr></thead><tbody>")
    for fw, f in sorted(s.get("frameworks", {}).items()):
        h.append(f"<tr><td>{e(fw)}</td><td class=num>{f.get('total', 0)}</td>"
                 f"<td class=num>{f.get('addressed', 0)}</td><td class=num>{f.get('verified', 0)}</td>"
                 f"<td class=num>{f.get('gaps', 0)}</td></tr>")
    h.append("</tbody></table><p class='muted small'>A clause counts as addressed when at least "
             "one question tagged with it reaches maturity 2 or more.</p>")

    # policy
    h.append("<h2>AI policy compliance</h2><table><thead><tr><th>Clause</th><th>Title</th>"
             "<th class=num>Questions met</th><th class=num>Residual</th><th>Status</th>"
             "</tr></thead><tbody>")
    for pid, p in s.get("policy", {}).items():
        status = '<span class=ok>Met</span>' if p.get("compliant") else '<span class=no>Not met</span>'
        h.append(f"<tr><td class=id>{e(pid)}</td><td>{e(p.get('title'))}</td>"
                 f"<td class=num>{p.get('met', 0)}/{len(p.get('questions', []))}</td>"
                 f"<td class=num>{_pct(p.get('frac'))}</td><td>{status}</td></tr>")
    h.append("</tbody></table>")

    # findings
    h.append("<h2>Findings</h2><p class='muted small'>Sorted by residual risk, highest first.</p>"
             "<table><thead><tr><th>ID</th><th>Question and mappings</th><th>Vendor answer</th>"
             "<th class=num>Maturity</th><th class=num>Residual</th></tr></thead><tbody>")
    for r in sorted(rows, key=lambda r: (-r.get("residual", 0), r["id"])):
        opts = r.get("options") or []
        m = r.get("maturity", 0)
        if r.get("answered"):
            ans = e(opts[m]) if 0 <= m < len(opts) else ""
            note = r.get("evidence") or ""
            ans += f'<div class="note muted">Note: {e(note)}</div>' if note else \
                '<div class="muted small">No note given.</div>'
            mat = f"{m}/3"
        else:
            ans, mat = '<span class=no>Unanswered</span>', "-"
        if r.get("verified"):
            ans += '<div class="small ok">Verified by lab test</div>'
        h.append(f"<tr><td class=id>{e(r['id'])}</td>"
                 f"<td>{e(r.get('question'))}<div class=tags>{_tags_html(r)}</div></td>"
                 f"<td>{ans}</td><td class=num>{mat}</td>"
                 f"<td class=num>{r.get('residual', 0):g} / {r.get('max', 0):g}</td></tr>")
    h.append("</tbody></table>")

    na = s.get("not_applicable", [])
    if na:
        h.append("<h2>Marked not applicable</h2><table><thead><tr><th>ID</th><th>Question</th>"
                 "<th>Reason given</th></tr></thead><tbody>")
        for n in na:
            h.append(f"<tr><td class=id>{e(n['id'])}</td><td>{e(n.get('question'))}</td>"
                     f"<td class=note>{e(n.get('note'))}</td></tr>")
        h.append("</tbody></table>")

    h.append("<footer>Framework, AI policy and NIST metric mappings are indicative, not a "
             "certification or legal opinion. Third-party answers are attested by the vendor "
             "and are not verified by the AICtrlProof lab unless marked. Residual risk is "
             "computed by grc/assess.py.</footer></main></body></html>")
    # Final guard: no em dashes in generated output, whatever the source text.
    return "".join(h).replace("\u2014", ", ")
