#!/usr/bin/env python3
"""
ctrlproof MCP server.

Exposes the AI risk assessment as MCP tools so any MCP client (Claude Desktop,
an IDE, another agent) can run it, read the standards mappings, and pull the
controls that were VERIFIED against the agent in the sandbox rather than merely
attested.

Tools:
  list_profiles()                       system types: core, app, agent, mcp
  list_questions(domain?, framework?, profile?)  the question bank, optionally filtered
  get_question(id)                      one question with its answer options and tags
  run_assessment(answers?, use_lab_evidence?, profiles?)  score it; returns residual risk,
                                        per-domain, framework coverage, findings
  control_coverage(framework?)          how many mapped controls are addressed / verified
  verified_controls()                   the tested controls and their live evidence
  explain_mapping(framework, clause?)   which questions map to a framework clause
  policy_coverage(answers?, profiles?)  AI policy clauses met / not met
  nist_metrics(profiles?)               NIST AI RMF metric per control, measured or to define

Built for MCP SDK 2.x (MCPServer). Run over stdio:
  python3 grc/mcp_server.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assess  # shared scoring logic

from mcp.server.mcpserver import MCPServer

app = MCPServer(
    name="ctrlproof",
    version="0.2.0",
    instructions=(
        "AI risk assessment with standards mapping. Some controls are verified "
        "against a real agent in an isolated sandbox, not self-attested. Use "
        "run_assessment to score a system, explain_mapping to trace a framework "
        "clause to questions, and verified_controls to see live test evidence."
    ),
)


@app.tool(description="System types the assessment covers (core always applies; app, agent, mcp are add-ons).")
def list_profiles() -> dict:
    return assess.load_questions()["meta"].get("profiles", {})


@app.tool(description="List the assessment questions, optionally filtered by domain, framework, or profile "
                      "(app, agent, mcp; core questions are always included).")
def list_questions(domain: str | None = None, framework: str | None = None,
                   profile: str | None = None) -> list[dict]:
    qs = assess.select_questions(assess.load_questions()["questions"],
                                 [profile] if profile else None)
    out = []
    for q in qs:
        if domain and q["domain"] != domain:
            continue
        if framework and framework not in q.get("tags", {}):
            continue
        out.append({"id": q["id"], "domain": q["domain"], "question": q["question"],
                    "type": q["type"], "risk_weight": q["risk_weight"],
                    "applies_to": q.get("applies_to", ["core"]), "policy": q.get("policy", []),
                    "tags": q.get("tags", {}), "nist_metric": q.get("nist_metric")})
    return out


@app.tool(description="One question in full: guidance, the four answer options (index = maturity 0-3), "
                      "AI policy clauses, framework tags, and NIST metric.")
def get_question(id: str) -> dict:
    for q in assess.load_questions()["questions"]:
        if q["id"] == id:
            return q
    return {"error": f"no question {id}"}


@app.tool(description="Score the assessment. 'answers' maps question id to {maturity:0-3, note}; "
                      "maturity is the index of the chosen option. Tested controls are filled from lab "
                      "evidence when use_lab_evidence is true. 'profiles' limits scope, e.g. ['agent','mcp'].")
def run_assessment(answers: dict | None = None, use_lab_evidence: bool = True,
                   profiles: list[str] | None = None) -> dict:
    out = assess.compute(answers=answers, use_lab_evidence=use_lab_evidence, profiles=profiles)
    # trim findings for a compact response
    out["questions"] = [
        {"id": r["id"], "domain": r["domain"], "maturity": r["maturity"],
         "verified": r["verified"], "residual": r["residual"], "evidence": r["evidence"]}
        for r in out["questions"]
    ]
    return out


@app.tool(description="Framework coverage: controls referenced, addressed, and verified by test.")
def control_coverage(framework: str | None = None, profiles: list[str] | None = None) -> dict:
    return assess.control_coverage(framework=framework, profiles=profiles)


@app.tool(description="AI policy compliance: per policy clause, how many evidencing controls are at "
                      "maturity 2+, how many are lab-verified, and whether the clause is met.")
def policy_coverage(answers: dict | None = None, profiles: list[str] | None = None) -> dict:
    return assess.policy_coverage(answers=answers, profiles=profiles)


@app.tool(description="NIST AI RMF metrics: the indicator and target for each control, grouped by "
                      "subcategory, marked measured (from lab evidence) or still to define.")
def nist_metrics(profiles: list[str] | None = None) -> dict:
    return assess.nist_metrics(profiles=profiles)


@app.tool(description="The tested controls and the live evidence behind each.")
def verified_controls() -> list[dict]:
    return assess.verified_controls()


@app.tool(description="Which questions map to a given framework (and optional clause, e.g. 'Art 15').")
def explain_mapping(framework: str, clause: str | None = None) -> list[dict]:
    return assess.explain_mapping(framework, clause)


if __name__ == "__main__":
    app.run(transport="stdio")
