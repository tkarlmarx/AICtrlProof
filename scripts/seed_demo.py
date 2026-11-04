#!/usr/bin/env python3
"""
Seed demo third-party vendor assessments for the AICtrlProof web app.

Writes five invented vendor assessments to app/data/assessments/<id>.json
(the same shape app/server.py stores), each marked "demo": true. All company
and product names are invented for the demo and do not refer to real firms.

  python3 scripts/seed_demo.py            # create or refresh the demo files
  python3 scripts/seed_demo.py --reset    # delete demo files first, then seed
  python3 scripts/seed_demo.py --dir DIR  # write somewhere else (tests)

Idempotent: ids are derived from a fixed slug, so a rerun rewrites the same
files and keeps each file's share_token and created time. --reset deletes only
files whose JSON has "demo": true; any other assessment is left alone.
"""
import argparse
import hashlib
import json
import os
import random
import secrets
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_DIR = os.path.join(ROOT, "app", "data", "assessments")
sys.path.insert(0, os.path.join(ROOT, "grc"))
import assess  # noqa: E402

DAY = 86400

# Generic note banks by maturity. {doc} is the vendor's own evidence document.
NOTES = {
    0: ["Not in place today.",
        "We have not looked at this yet.",
        "No formal process. On the roadmap for next year.",
        "Not something we currently do."],
    1: ["Handled informally by the engineering lead.",
        "Partly in place, not documented.",
        "Ad hoc. We plan to formalise this after our next funding round.",
        "Some coverage on the main service only.",
        "Done when someone remembers, no schedule."],
    2: ["Documented in {doc}; not yet applied to every product line.",
        "In place for production, staging still catching up. See {doc}.",
        "Process exists and is followed, last reviewed eight months ago.",
        "Covered by {doc}. Annual review not yet completed this year.",
        "Implemented; gaps tracked as open items in our risk register."],
    3: ["Covered by {doc}, section {sec}. Evidence available under NDA.",
        "Tested quarterly; latest results in {doc}, section {sec}.",
        "In scope of our {audit}; auditor tested this control with no exceptions.",
        "Policy and test evidence attached ({doc}, section {sec}). Reviewed every year by the CISO.",
        "Automated check in CI blocks release on failure; see {doc}, section {sec}."],
}
VAGUE_3 = ["Yes.", "Fully compliant.", "Industry best practice.", "Yes, of course.",
           "We take security very seriously."]

VENDORS = [
    {
        "slug": "brightline-support",
        "name": "Brightline Assist customer support chatbot",
        "org": "Brightline Helpdesk Labs Ltd",
        "profiles": ["app"],
        "status": "submitted",
        "mu": 2.6, "spread": 0.5, "vague": 0.0,
        "doc": "the Brightline Trust Pack v4.2", "audit": "SOC 2 Type II audit (period ending June 2026)",
        "age_days": 41, "submitted_days": 9,
        "answers": {
            "GOV-1": (3, "Accountable owner: VP Product Safety, named in our AI inventory and signs the risk acceptance each release. Inventory extract attached."),
            "APP-1": (3, "All model output is HTML-encoded before rendering in the widget; outbound webhooks pass a JSON schema validator. Covered by 212 automated XSS and injection test cases in CI."),
            "APP-3": (2, "Retrieval filters by tenant id and the source article's visibility flag. Per-agent permissions on private macros are not yet enforced in the vector index."),
            "APP-4": (2, "Answers are grounded on the customer's help centre with citations shown to the end user. Accuracy is sampled weekly (300 conversations), not yet tied to a release gate."),
            "APP-6": (3, "Widget shows 'AI assistant' on every message and the hand-off to a human is labelled. Screenshot set in Trust Pack section 7."),
            "EU-2": ("na", "Classified as not high-risk: customer support for consumer software is outside Annex III. Classification recorded in our AI inventory (ref INV-0042) and reviewed by counsel in March 2026."),
            "EU-5": ("na", "We do not provide or modify a general-purpose AI model. We call a third-party model API under a commercial agreement and do no fine-tuning."),
        },
    },
    {
        "slug": "forgepoint-agent",
        "name": "Forgepoint Pilot agentic coding assistant",
        "org": "Forgepoint Dev Systems Inc.",
        "profiles": ["agent", "mcp"],
        "status": "submitted",
        "mu": 0.35, "spread": 0.7, "vague": 0.6,
        "doc": "our security overview deck", "audit": "SOC 2 readiness assessment",
        "age_days": 33, "submitted_days": 4,
        "answers": {
            "ACCESS-1": (3, "Yes."),
            "AGENT-2": (1, "Developers can turn on auto-approve for all actions. Most enterprise customers keep the default prompt for shell commands."),
            "AGENT-4": (1, "Code runs on the developer's machine by default. A cloud sandbox option is in beta."),
            "ROBUST-1": (3, "Industry best practice."),
            "MCP-2": (0, "MCP servers run locally with the developer's own credentials; no per-tool authorisation."),
            "MCP-3": (1, "Tokens are kept in the MCP config file in the user's home directory. We recommend customers rotate them."),
            "MCP-8": (1, "The system prompt tells the model to ignore instructions in tool output."),
            "DATA-2": (3, "We take security very seriously."),
            "EU-4": ("na", "Not relevant."),
            "EU-5": ("na", "N/A"),
        },
    },
    {
        "slug": "toolhaven-marketplace",
        "name": "Toolhaven MCP tool marketplace",
        "org": "Toolhaven Integrations GmbH",
        "profiles": ["mcp"],
        "status": "in progress",
        "mu": 1.7, "spread": 0.8, "vague": 0.2,
        "doc": "the Toolhaven publisher policy", "audit": "ISO/IEC 27001 surveillance audit",
        "age_days": 12, "answer_share": 0.55,
        "answers": {
            "MCP-1": (2, "Only listed servers can be installed through our client; listing requires a publisher review. We cannot see servers customers add by hand."),
            "MCP-5": (1, "Tool descriptions are reviewed at first listing. Changes in later versions are not diffed yet."),
            "MCP-6": (2, "Packages are built from the publisher's tagged source and scanned with an SCA tool. Pinning is up to the customer."),
        },
    },
    {
        "slug": "candora-screening",
        "name": "Candora Match CV screening and ranking",
        "org": "Candora Talent Technologies B.V.",
        "profiles": ["app"],
        "status": "submitted",
        "mu": 1.6, "spread": 0.6, "vague": 0.25,
        "doc": "the Candora compliance dossier", "audit": "ISO/IEC 27001 certification audit",
        "age_days": 58, "submitted_days": 16,
        "answers": {
            "EU-1": (3, "Screened against Article 5 practices in January 2026; no emotion recognition or social scoring features. Screening record CMP-2026-01, signed by our DPO."),
            "EU-2": (2, "We accept the system is high-risk (Annex III, point 4: employment). Conformity assessment under internal control started in Q2 2026 with an external advisor; EU database registration not yet done."),
            "EU-3": (2, "Deployer instructions published in the admin guide. We do not track which customers have named human overseers."),
            "EU-4": (1, "We checked applicability for our public-sector customers. No fundamental rights impact assessment template is provided to them yet."),
            "APP-4": (1, "Ranking explanations are shown to recruiters. Accuracy and adverse impact are measured once a year on a historical sample, not per model release."),
            "APP-6": (2, "Candidates are told in the application form that AI assists screening. Generated summaries are not labelled as AI-produced in the exported PDF."),
            "RISK-2": (2, "Bias and over-reliance risks are in the register with owners. Hallucination in candidate summaries is not yet listed."),
            "EU-5": ("na", "We fine-tune nothing ourselves and do not place a general-purpose model on the market; the underlying model is licensed from a provider who holds the GPAI documentation."),
        },
    },
    {
        "slug": "lumenquery-rag",
        "name": "Lumenquery Insights RAG analytics agent",
        "org": "Lumenquery Analytics Ltd",
        "profiles": ["app", "agent"],
        "status": "sent",
        "mu": 0, "spread": 0, "vague": 0,
        "doc": "", "audit": "",
        "age_days": 3, "answer_share": 0.0,
    },
]


def _id(slug):
    return hashlib.sha256(("ctrlproof-demo:" + slug).encode()).hexdigest()[:12]


def _note(rng, v, m):
    if m == 3 and rng.random() < v["vague"]:
        return rng.choice(VAGUE_3)
    text = rng.choice(NOTES[m])
    return text.format(doc=v["doc"] or "our policy", sec=rng.randint(2, 9),
                       audit=v["audit"] or "annual audit")


def build_answers(v, questions):
    rng = random.Random("ctrlproof-demo:" + v["slug"])
    in_scope = assess.select_questions(questions, v["profiles"])
    fixed = v.get("answers", {})
    share = v.get("answer_share", 1.0)
    out = {}
    for q in in_scope:
        qid = q["id"]
        if v["status"] != "submitted" and qid not in fixed and rng.random() >= share:
            continue
        if qid in fixed:
            m, note = fixed[qid]
            out[qid] = {"na": True, "note": note} if m == "na" else {"maturity": m, "note": note}
            continue
        m = int(round(rng.gauss(v["mu"], v["spread"])))
        m = max(0, min(3, m))
        out[qid] = {"maturity": m, "note": _note(rng, v, m)}
    return out


def score(a):
    lab = a.get("kind") == "internal"
    return assess.compute(answers=a["answers"], profiles=a["profiles"] or None,
                          use_lab_evidence=lab, attest_tested=not lab)


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def reset(adir):
    removed = 0
    if not os.path.isdir(adir):
        return 0
    for fn in os.listdir(adir):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(adir, fn)
        d = _load(p)
        if isinstance(d, dict) and d.get("demo") is True:
            os.remove(p)
            removed += 1
    return removed


def seed(adir=DEFAULT_DIR, do_reset=False, now=None):
    """Write the demo assessments. Returns the list of assessment dicts."""
    now = int(now or time.time())
    if do_reset:
        reset(adir)
    os.makedirs(adir, exist_ok=True)
    questions = assess.load_questions()["questions"]
    out = []
    for v in VENDORS:
        aid = _id(v["slug"])
        path = os.path.join(adir, aid + ".json")
        prev = _load(path) or {}
        created = prev.get("created") or now - v["age_days"] * DAY
        a = {
            "id": aid, "name": v["name"], "org": v["org"], "kind": "third-party",
            "profiles": list(v["profiles"]), "status": v["status"],
            "created": created, "updated": now,
            "share_token": prev.get("share_token") or secrets.token_urlsafe(18),
            "submitted_at": (now - v["submitted_days"] * DAY) if v["status"] == "submitted" else None,
            "answers": build_answers(v, questions),
            "demo": True,
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(a, f, indent=2)
        os.replace(tmp, path)
        out.append(a)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Seed demo vendor assessments.")
    ap.add_argument("--reset", action="store_true", help="delete existing demo files first")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="assessments directory")
    args = ap.parse_args(argv)
    rows = seed(args.dir, args.reset)
    qs = assess.load_questions()["questions"]
    print(f"Seeded {len(rows)} demo assessments into {args.dir}")
    print(f"{'Name':<46} {'Status':<12} {'Answered':>9} {'Residual':>9}  Rating")
    for a in rows:
        s = score(a)
        n = len(assess.select_questions(qs, a["profiles"]))
        print(f"{a['name']:<46} {a['status']:<12} {len(a['answers']):>4}/{n:<4} "
              f"{s['overall_residual'] * 100:>8.0f}%  {s['overall_sev']}")


if __name__ == "__main__":
    main()
