"""Deterministic graders for the Epistex protocol-compliance benchmark suite.

Every grader returns (passed: bool, failed_checks: list[str]).
Graders are intentionally structural/rule-based so scoring cannot drift with
an LLM judge: the system under test is the prompt protocol, not the grader.
"""
from __future__ import annotations

import re

SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")


def _norm(text: str) -> str:
    return text.replace("\r", "")


def _field_ok(output: str, field: str) -> bool:
    """Field-label check. 'Project / Task ID' is a compound label: accept the
    literal template label OR both 'Project' and 'Task' rendered separately
    (v1.1 — the template line is ambiguous about how to render the pair)."""
    low = output.lower()
    if field.lower() in low:
        return True
    if field == "Project / Task ID":
        return "project:" in low and "task:" in low
    return False


def grade_lead_brief(output: str, spec: dict) -> tuple[bool, list[str]]:
    failed = []
    for field in spec.get("must_contain_fields", []):
        if not _field_ok(output, field):
            failed.append(f"missing field: {field}")
    if spec.get("first_person_markers"):
        if not any(m.lower() in output.lower() for m in spec["first_person_markers"]):
            failed.append("not written in first person (no 'I need'/'I have decided')")
    for banned in spec.get("must_not_contain", []):
        if banned.lower() in output.lower():
            failed.append(f"contains banned/hint phrase: {banned!r}")
    for quote in spec.get("must_not_quote", []):
        if quote.lower() in _norm(output).lower():
            failed.append("quotes the Human's words verbatim instead of restating")
    if spec.get("third_party_markers"):
        if not any(m.lower() in output.lower() for m in spec["third_party_markers"]):
            failed.append("feedback not framed as third-party")
    return (not failed), failed


def grade_peer_handoff(output: str, spec: dict) -> tuple[bool, list[str]]:
    failed = []
    for label in spec.get("must_contain_labels", []):
        if label.lower() not in output.lower():
            failed.append(f"missing handoff cell: {label}")
    if spec.get("expected_outcome"):
        # Outcome cell must state the expected disposition near the 'Outcome' label
        m = re.search(r"Outcome\s*[:\-]?\s*(\w+)", output, re.I)
        if not m or m.group(1).lower() != spec["expected_outcome"].lower():
            failed.append(
                f"Outcome cell missing or wrong (expected {spec['expected_outcome']})"
            )
    for sha in spec.get("expected_shas", []):
        if sha not in output:
            failed.append(f"missing expected SHA {sha[:8]}...")
    if spec.get("expected_branch") and spec["expected_branch"] not in output:
        failed.append(f"missing branch {spec['expected_branch']}")
    if spec.get("expected_verification_evidence") and spec[
        "expected_verification_evidence"
    ] not in output:
        failed.append("verification cell lacks real command output evidence")
    if spec.get("must_mention_skipped"):
        if not any(m.lower() in output.lower() for m in spec["must_mention_skipped"]):
            failed.append("does not report deliberately skipped checks")
    return (not failed), failed


def grade_peer_report(output: str, spec: dict) -> tuple[bool, list[str]]:
    failed = []
    expected = spec.get("expected_report", "")
    if expected and expected.upper() not in output.upper():
        failed.append(f"missing report type {expected}")
    for label in spec.get("must_contain_labels", []):
        if label.lower() not in output.lower():
            failed.append(f"missing handoff cell: {label}")
    if spec.get("required_layer"):
        layers = ["foundation", "dependency", "lifecycle", "API", "ownership", "verification"]
        if not any(layer.lower() in output.lower() for layer in layers):
            failed.append("REOPEN_REQUEST does not name a layer")
    if spec.get("evidence_markers_any"):
        if not any(m.lower() in output.lower() for m in spec["evidence_markers_any"]):
            failed.append("report lacks evidence reference")
    return (not failed), failed


def grade_keyword_any(output: str, spec: dict) -> tuple[bool, list[str]]:
    failed = []
    if not any(k.lower() in output.lower() for k in spec["any_of"]):
        failed.append(f"decision not recognizably correct (none of: {spec['any_of'][:3]}...)")
    return (not failed), failed


GRADERS = {
    "lead_brief": grade_lead_brief,
    "peer_handoff": grade_peer_handoff,
    "peer_report": grade_peer_report,
    "keyword_any": grade_keyword_any,
}


def grade(task: dict, output: str) -> tuple[bool, list[str]]:
    gtype = task["grader"]["type"]
    return GRADERS[gtype](output, task["grader"])


def feedback_from(failed_checks: list[str], task: dict) -> str:
    """Build the rework prompt the Lead would send on a failed review."""
    return (
        "Your output was reviewed against the handoff/brief contract and rejected. "
        "Fix exactly these findings and return the corrected artifact:\n"
        + "\n".join(f"- {c}" for c in failed_checks)
        + "\nKeep the same task and round; return the full corrected output only."
    )
