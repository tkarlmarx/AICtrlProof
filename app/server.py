#!/usr/bin/env python3
"""
AICtrlProof web app: team login, assessments, third-party share links,
dashboard.

Standard library only. Scoring is NOT reimplemented here: every score comes
from grc/assess.compute, the single scoring path.

Run:
    python3 app/server.py                          # http://127.0.0.1:8090
    HOST=0.0.0.0 PORT=8090 python3 app/server.py   # reachable on your network

Login: set CTRLPROOF_USER and CTRLPROOF_PASSWORD. With no CTRLPROOF_PASSWORD
the app runs in demo mode with a random password made at each start and
printed to the server console. The login page shows it only when the app is
bound to loopback (127.0.0.1); on any network bind it is never shown.

Assessments:
  internal     your own AI system; lab-tested controls come from the lab.
  third-party  a vendor or partner; send them the share link, they answer
               without logging in (lab-tested controls become self-reported,
               because our lab never exercised their system), then submit.
Data lives in app/data/assessments/<id>.json (gitignored).
"""
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
ADIR = os.path.join(DATA, "assessments")
LEGACY_ANSWERS = os.path.join(DATA, "answers.json")
sys.path.insert(0, os.path.join(ROOT, "grc"))
sys.path.insert(0, HERE)
import assess  # noqa: E402

# Demo mode: with no CTRLPROOF_PASSWORD set, a random password is made at each
# start (never a fixed one) and printed to the server console. The login page
# shows it only when the server is bound to loopback. Set CTRLPROOF_PASSWORD to
# turn demo mode off.
DEMO_USER = "admin"
DEMO = not os.environ.get("CTRLPROOF_PASSWORD")
USER = os.environ.get("CTRLPROOF_USER", DEMO_USER)
PASSWORD = secrets.token_urlsafe(12) if DEMO else os.environ["CTRLPROOF_PASSWORD"]
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
SHOW_DEMO_HINT = False  # set in main(): only for a loopback bind in demo mode
SESSIONS = {}  # token -> user
LOCK = threading.Lock()
ID_RE = re.compile(r"^[a-z0-9]{8,32}$")


# ---------------- storage ----------------

def _path(aid):
    return os.path.join(ADIR, f"{aid}.json")


def load_assessment(aid):
    if not ID_RE.match(aid or ""):
        return None
    try:
        with open(_path(aid)) as f:
            return json.load(f)
    except Exception:
        return None


def save_assessment(a):
    os.makedirs(ADIR, exist_ok=True)
    a["updated"] = int(time.time())
    tmp = _path(a["id"]) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(a, f, indent=2)
    os.replace(tmp, _path(a["id"]))


def all_assessments():
    out = []
    if os.path.isdir(ADIR):
        for fn in os.listdir(ADIR):
            if fn.endswith(".json"):
                a = load_assessment(fn[:-5])
                if a:
                    out.append(a)
    return sorted(out, key=lambda a: a.get("created", 0))


def by_token(tok):
    if not tok:
        return None
    for a in all_assessments():
        if a.get("share_token") and hmac.compare_digest(a["share_token"], tok):
            return a
    return None


def new_assessment(name, org, kind, profiles, answers=None):
    return {"id": secrets.token_hex(6), "name": name, "org": org, "kind": kind,
            "profiles": profiles, "status": "draft", "created": int(time.time()),
            "share_token": None, "submitted_at": None, "answers": answers or {}}


def ensure_seed():
    """Make sure one internal assessment exists, seeded from the old answers file or the example."""
    if any(a.get("kind") == "internal" for a in all_assessments()):
        return
    seed = {}
    for p in (LEGACY_ANSWERS, os.path.join(ROOT, "grc", "answers.example.json")):
        try:
            with open(p) as f:
                seed = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
            break
        except Exception:
            continue
    save_assessment(new_assessment("Internal coding agent", "Our organisation", "internal",
                                   ["agent", "mcp"], seed))


# ---------------- logic ----------------

def lab_on(a):
    return a.get("kind") == "internal"


def validate_answer(q, a, lab=True):
    """Return (clean_answer or None, error or None)."""
    if q["type"] == "tested" and lab:
        return None, f"{q['id']} is verified by the lab and cannot be answered"
    if not isinstance(a, dict):
        return None, "answer must be an object"
    note = str(a.get("note", ""))[:500]
    if a.get("na"):
        if not note.strip():
            return None, f"{q['id']}: give a reason when marking not applicable"
        return {"na": True, "note": note}, None
    m = a.get("maturity")
    if not isinstance(m, int) or isinstance(m, bool) or m not in range(4):
        return None, f"{q['id']}: maturity must be 0, 1, 2 or 3"
    return {"maturity": m, "note": note}, None


def score(a, profiles=None):
    lab = lab_on(a)
    return assess.compute(answers=a["answers"], profiles=profiles or a["profiles"] or None,
                          use_lab_evidence=lab, attest_tested=not lab)


def in_scope_ids(a):
    qs = assess.select_questions(assess.load_questions()["questions"], a["profiles"] or None)
    return [q["id"] for q in qs]


def summary(a):
    ids = in_scope_ids(a)
    done = sum(1 for i in ids if i in a["answers"])
    r = score(a)
    return {k: a.get(k) for k in ("id", "name", "org", "kind", "profiles", "status",
                                  "created", "updated", "submitted_at")} | {
        "shared": bool(a.get("share_token")), "answered": done, "total": len(ids),
        "overall_residual": r["overall_residual"], "overall_sev": r["overall_sev"],
        "verified_count": r["verified_count"]}


def apply_answers(a, body):
    qs = {q["id"]: q for q in assess.load_questions()["questions"]}
    errors = {}
    for qid, ans in body.items():
        if qid not in qs:
            errors[qid] = "unknown question"
            continue
        if ans is None:
            a["answers"].pop(qid, None)
            continue
        clean, err = validate_answer(qs[qid], ans, lab=lab_on(a))
        if err:
            errors[qid] = err
        else:
            a["answers"][qid] = clean
    return errors


def build_review(a):
    import ai_review  # app/ai_review.py
    return ai_review.review(a, score(a))


def build_report(a):
    import report  # app/report.py
    rv = a.get("review") or build_review(a)
    return report.render_report(a, score(a), rv)


# ---------------- HTTP ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = "ctrlproof"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _json(self, code, obj, extra_headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return None

    def _user(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        tok = c.get("cp_session")
        return SESSIONS.get(tok.value) if tok else None

    def _static(self, rel):
        path = os.path.normpath(os.path.join(STATIC, rel))
        if not path.startswith(STATIC) or not os.path.isfile(path):
            self.send_error(404)
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code, html):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        self.end_headers()
        self.wfile.write(body)

    def _bank(self, profiles=None):
        qb = assess.load_questions()
        return {"meta": qb["meta"], "policy": assess.load_policy()["clauses"],
                "questions": assess.select_questions(qb["questions"], profiles)}

    # ---- GET ----
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p in ("/", "/index.html") or p.startswith("/r/"):
            return self._static("index.html")
        if p.startswith("/static/"):
            return self._static(p[len("/static/"):])
        m = re.match(r"^/report/([A-Za-z0-9_-]{16,64})$", p)
        if m:
            tok = m.group(1)
            hit = next((a for a in all_assessments() if a.get("report_token")
                        and hmac.compare_digest(a["report_token"], tok)), None)
            if not hit:
                return self._html(404, "<h1>Report link not valid or revoked.</h1>")
            return self._html(200, build_report(hit))
        if p == "/api/demo":
            show = DEMO and SHOW_DEMO_HINT
            return self._json(200, {"demo": show, "user": USER if show else None,
                                    "password": PASSWORD if show else None})
        if p == "/api/me":
            u = self._user()
            return self._json(200 if u else 401, {"user": u})

        # third-party respondent (share token, no login)
        m = re.match(r"^/api/r/([A-Za-z0-9_-]{16,64})$", p)
        if m:
            a = by_token(m.group(1))
            if not a:
                return self._json(404, {"error": "This link is not valid or has been revoked."})
            return self._json(200, {"name": a["name"], "org": a["org"], "status": a["status"],
                                    "lab": lab_on(a), "answers": a["answers"],
                                    "bank": self._bank(a["profiles"] or None)})

        if not self._user():
            return self._json(401, {"error": "login required"})
        if p == "/api/bank":
            return self._json(200, self._bank())
        if p == "/api/assessments":
            return self._json(200, [summary(a) for a in all_assessments()])
        m = re.match(r"^/api/assessments/([a-z0-9]+)/report$", p)
        if m:
            a = load_assessment(m.group(1))
            if not a:
                return self._html(404, "<h1>No such assessment.</h1>")
            return self._html(200, build_report(a))
        m = re.match(r"^/api/assessments/([a-z0-9]+)$", p)
        if m:
            a = load_assessment(m.group(1))
            if not a:
                return self._json(404, {"error": "no such assessment"})
            return self._json(200, a)
        return self._json(404, {"error": "not found"})

    # ---- POST ----
    def do_POST(self):
        p = self.path.split("?", 1)[0]
        body = self._body()
        if body is None:
            return self._json(400, {"error": "invalid JSON"})

        if p == "/api/login":
            ok = hmac.compare_digest(str(body.get("user", "")), USER) & \
                hmac.compare_digest(str(body.get("password", "")), PASSWORD)
            if not ok:
                return self._json(401, {"error": "Wrong username or password"})
            tok = secrets.token_urlsafe(24)
            SESSIONS[tok] = USER
            return self._json(200, {"user": USER}, {
                "Set-Cookie": f"cp_session={tok}; HttpOnly; SameSite=Strict; Path=/"})
        if p == "/api/logout":
            c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            if c.get("cp_session"):
                SESSIONS.pop(c["cp_session"].value, None)
            return self._json(200, {"ok": True}, {"Set-Cookie": "cp_session=; Max-Age=0; Path=/"})

        # third-party respondent
        m = re.match(r"^/api/r/([A-Za-z0-9_-]{16,64})/(answers|submit)$", p)
        if m:
            with LOCK:
                a = by_token(m.group(1))
                if not a:
                    return self._json(404, {"error": "This link is not valid or has been revoked."})
                if a["status"] == "submitted":
                    return self._json(409, {"error": "Already submitted. Ask the requester to reopen it."})
                if m.group(2) == "answers":
                    errors = apply_answers(a, body)
                    a["status"] = "in progress"
                    save_assessment(a)
                    return self._json(200 if not errors else 422, {"saved": not errors, "errors": errors})
                missing = [i for i in in_scope_ids(a) if i not in a["answers"]]
                if missing:
                    return self._json(422, {"error": f"{len(missing)} question(s) still unanswered",
                                            "missing": missing})
                a["status"] = "submitted"
                a["submitted_at"] = int(time.time())
                save_assessment(a)
                return self._json(200, {"ok": True})

        if not self._user():
            return self._json(401, {"error": "login required"})

        valid_profiles = set(assess.load_questions()["meta"].get("profiles", {}))

        if p == "/api/assessments":
            name = str(body.get("name", "")).strip()[:120]
            org = str(body.get("org", "")).strip()[:120]
            kind = body.get("kind", "third-party")
            profiles = body.get("profiles") or []
            if not name or not org:
                return self._json(422, {"error": "Name and organisation are required."})
            if kind not in ("internal", "third-party"):
                return self._json(422, {"error": "kind must be internal or third-party"})
            if not isinstance(profiles, list) or not set(profiles) <= valid_profiles:
                return self._json(422, {"error": f"profiles must be a subset of {sorted(valid_profiles)}"})
            a = new_assessment(name, org, kind, [x for x in profiles if x != "core"])
            with LOCK:
                save_assessment(a)
            return self._json(200, summary(a))

        m = re.match(r"^/api/assessments/([a-z0-9]+)/(answers|assess|share|revoke|reopen|delete|reset|review|share-report|benchmark)$", p)
        if m:
            with LOCK:
                a = load_assessment(m.group(1))
                if not a:
                    return self._json(404, {"error": "no such assessment"})
                act = m.group(2)
                if act == "answers":
                    errors = apply_answers(a, body)
                    save_assessment(a)
                    return self._json(200 if not errors else 422, {"saved": not errors, "errors": errors})
                if act == "assess":
                    prof = body.get("profiles")
                    if prof is not None and (not isinstance(prof, list) or not set(prof) <= valid_profiles):
                        return self._json(400, {"error": "bad profiles"})
                    return self._json(200, score(a, prof))
                if act == "share":
                    if not a.get("share_token"):
                        a["share_token"] = secrets.token_urlsafe(18)
                    if a["status"] == "draft":
                        a["status"] = "sent"
                    save_assessment(a)
                    return self._json(200, {"path": "/r/" + a["share_token"], "status": a["status"]})
                if act == "benchmark":
                    bench = assess.load_benchmark("anthropic")
                    if not bench:
                        return self._json(404, {"error": "No benchmark file yet (grc/benchmarks/anthropic.json)."})
                    return self._json(200, assess.benchmark_compare(score(a), bench))
                if act == "review":
                    try:
                        a["review"] = build_review(a)
                    except Exception as e:  # module missing or model error
                        return self._json(500, {"error": f"AI review failed: {type(e).__name__}"})
                    save_assessment(a)
                    return self._json(200, a["review"])
                if act == "share-report":
                    if not a.get("report_token"):
                        a["report_token"] = secrets.token_urlsafe(18)
                    save_assessment(a)
                    return self._json(200, {"path": "/report/" + a["report_token"]})
                if act == "revoke":
                    a["share_token"] = None
                    save_assessment(a)
                    return self._json(200, {"ok": True})
                if act == "reopen":
                    a["status"] = "in progress"
                    a["submitted_at"] = None
                    save_assessment(a)
                    return self._json(200, {"ok": True})
                if act == "reset":
                    a["answers"] = {}
                    save_assessment(a)
                    return self._json(200, {"ok": True})
                if act == "delete":
                    os.remove(_path(a["id"]))
                    return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})


def main():
    global SHOW_DEMO_HINT
    ensure_seed()
    host = os.environ.get("HOST", "127.0.0.1")
    SHOW_DEMO_HINT = DEMO and host in LOOPBACK_HOSTS
    port = int(os.environ.get("PORT", "8090"))
    srv = ThreadingHTTPServer((host, port), Handler)
    where = "shown on the login page" if SHOW_DEMO_HINT else \
        "not shown on the login page because the app is on a network bind"
    mode = f"demo login {USER} / {PASSWORD} (random for this run, {where})" if DEMO \
        else f"login {USER} / (from CTRLPROOF_PASSWORD)"
    print(f"AICtrlProof app on http://{host}:{port}  {mode}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
