#!/usr/bin/env python3
"""
ctrlproof MCP server.

Exposes the AI risk assessment as MCP tools so any MCP client (Claude Desktop,
an IDE, another agent) can run it, read the standards mappings, and pull the
controls that were VERIFIED against the agent in the sandbox rather than merely
attested.

Tools:
  list_questions(domain?, framework?)   the question bank, optionally filtered
  run_assessment(answers?, use_lab_evidence?)  score it; returns residual risk,
                                        per-domain, framework coverage, findings
  control_coverage(framework?)          how many mapped controls are addressed / verified
  verified_controls()                   the tested controls and their live evidence
  explain_mapping(framework, clause?)   which questions map to a framework clause

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
    version="0.1.0",
    instructions=(
        "AI risk assessment with standards mapping. Some controls are verified "
        "against a real agent in an isolated sandbox, not self-attested. Use "
        "run_assessment to score a system, explain_mapping to trace a framework "
        "clause to questions, and verified_controls to see live test evidence."
    ),
)


@app.tool(description="List the assessment questions, optionally filtered by domain or framework.")
def list_questions(domain: str | None = None, framework: str | None = None) -> list[dict]:
    qs = assess.load_questions()["questions"]
    out = []
    for q in qs:
        if domain and q["domain"] != domain:
            continue
        if framework and framework not in q.get("tags", {}):
            continue
        out.append({"id": q["id"], "domain": q["domain"], "question": q["question"],
                    "type": q["type"], "risk_weight": q["risk_weight"],
                    "tags": q.get("tags", {})})
    return out


@app.tool(description="Score the assessment. 'answers' maps question id to {maturity:0-3, note}. "
                      "Tested controls are filled from lab evidence when use_lab_evidence is true.")
def run_assessment(answers: dict | None = None, use_lab_evidence: bool = True) -> dict:
    out = assess.compute(answers=answers, use_lab_evidence=use_lab_evidence)
    # trim findings for a compact response
    out["questions"] = [
        {"id": r["id"], "domain": r["domain"], "maturity": r["maturity"],
         "verified": r["verified"], "residual": r["residual"], "evidence": r["evidence"]}
        for r in out["questions"]
    ]
    return out


@app.tool(description="Framework coverage: controls referenced, addressed, and verified by test.")
def control_coverage(framework: str | None = None) -> dict:
    return assess.control_coverage(framework=framework)


@app.tool(description="The tested controls and the live evidence behind each.")
def verified_controls() -> list[dict]:
    return assess.verified_controls()


@app.tool(description="Which questions map to a given framework (and optional clause, e.g. 'Art 15').")
def explain_mapping(framework: str, clause: str | None = None) -> list[dict]:
    return assess.explain_mapping(framework, clause)


if __name__ == "__main__":
    app.run(transport="stdio")
