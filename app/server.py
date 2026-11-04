#!/usr/bin/env python3
"""
AICtrlProof web app: login, fill the assessment, see the dashboard.

Standard library only. Scoring is NOT reimplemented here: every score comes
from grc/assess.compute, the single scoring path.

Run:
    python3 app/server.py                      # http://127.0.0.1:8090
    HOST=0.0.0.0 PORT=8090 python3 app/server.py   # reachable on your network

Login: set CTRLPROOF_USER and CTRLPROOF_PASSWORD. If the password is not set,
a random one is generated and printed at startup.

Answers are saved to app/data/answers.json (gitignored).
"""
import hmac
import json
import mimetypes
import os
import secrets
import sys
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATIC = os.path.join(HERE, "static")
DATA = os.path.join(HERE, "data")
ANSWERS = os.path.join(DATA, "answers.json")
sys.path.insert(0, os.path.join(ROOT, "grc"))
import assess  # noqa: E402

USER = os.environ.get("CTRLPROOF_USER", "admin")
PASSWORD = os.environ.get("CTRLPROOF_PASSWORD") or secrets.token_urlsafe(9)
SESSIONS = {}  # token -> user
LOCK = threading.Lock()


def load_answers():
    try:
        with open(ANSWERS) as f:
            return json.load(f)
    except Exception:
        return {}


def save_answers(ans):
    os.makedirs(DATA, exist_ok=True)
    tmp = ANSWERS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ans, f, indent=2)
    os.replace(tmp, ANSWERS)


def validate_answer(q, a):
    """Return (clean_answer or None, error or None)."""
    if q["type"] == "tested":
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


class Handler(BaseHTTPRequestHandler):
    server_version = "ctrlproof"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # ---- helpers ----
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
        self.end_headers()
        self.wfile.write(body)

    # ---- routes ----
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p in ("/", "/index.html"):
            return self._static("index.html")
        if p.startswith("/static/"):
            return self._static(p[len("/static/"):])
        if p == "/api/me":
            u = self._user()
            return self._json(200 if u else 401, {"user": u})
        if not self._user():
            return self._json(401, {"error": "login required"})
        if p == "/api/bank":
            qb = assess.load_questions()
            return self._json(200, {"meta": qb["meta"], "questions": qb["questions"],
                                    "policy": assess.load_policy()["clauses"]})
        if p == "/api/answers":
            return self._json(200, load_answers())
        return self._json(404, {"error": "not found"})

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
            return self._json(200, {"ok": True}, {
                "Set-Cookie": "cp_session=; Max-Age=0; Path=/"})

        if not self._user():
            return self._json(401, {"error": "login required"})

        if p == "/api/answers":
            # body: {"<id>": {...answer...} | null}   null clears the answer
            qs = {q["id"]: q for q in assess.load_questions()["questions"]}
            errors = {}
            with LOCK:
                ans = load_answers()
                for qid, a in body.items():
                    if qid not in qs:
                        errors[qid] = "unknown question"
                        continue
                    if a is None:
                        ans.pop(qid, None)
                        continue
                    clean, err = validate_answer(qs[qid], a)
                    if err:
                        errors[qid] = err
                    else:
                        ans[qid] = clean
                save_answers(ans)
            return self._json(200 if not errors else 422, {"saved": not errors, "errors": errors})

        if p == "/api/assess":
            profiles = body.get("profiles") or None
            valid = set(assess.load_questions()["meta"].get("profiles", {}))
            if profiles and (not isinstance(profiles, list) or not set(profiles) <= valid):
                return self._json(400, {"error": f"profiles must be a subset of {sorted(valid)}"})
            out = assess.compute(answers=load_answers(), profiles=profiles)
            return self._json(200, out)

        if p == "/api/reset":
            with LOCK:
                save_answers({})
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8090"))
    srv = ThreadingHTTPServer((host, port), Handler)
    shown = "(from CTRLPROOF_PASSWORD)" if os.environ.get("CTRLPROOF_PASSWORD") else PASSWORD
    print(f"AICtrlProof app on http://{host}:{port}  login: {USER} / {shown}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
