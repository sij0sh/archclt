"""Connect task scope and acceptance criteria to existing verification IDs."""

from __future__ import annotations

from archctl.core.enforcement import add_reason, policy_obligation
from archctl.core.change import Change
from archctl.core.io import digest, matches
from archctl.core.models import Snapshot, owners


def apply_change(change: Change, snapshot: Snapshot, baseline: Snapshot, impact: dict) -> dict:
    """Return a new impact contract; no task can authorize an architecture edit."""
    gaps = list(impact["unknowns"])
    allowed = set(change.components)
    affected = {c["id"] for c in impact["affected_components"]}
    for component in sorted(affected - allowed):
        gaps.append(f"Affected component is outside reviewed change scope: {component}")
    for path in impact["changed_paths"]:
        bound = set(owners(path, (*snapshot.model.components, *baseline.model.components)))
        if bound - allowed:
            gaps.append(f"Changed path is outside reviewed component scope: {path}: {', '.join(sorted(bound - allowed))}")
        if not bound and any(matches(path, pattern) for pattern in change.paths):
            # Explicitly reviewed non-component files (e.g. tests/docs). They
            # cannot excuse a source edit in an excluded component.
            message = f"Changed path has no declared component: {path}"
            gaps = [gap for gap in gaps if gap != message]
        elif not bound and path not in dict(snapshot.sources):
            gaps.append(f"Changed path is outside reviewed file scope: {path}")
    gaps += [f"Open question: {q}" for q in change.open_questions]
    obligations = {v["id"]: {**v, "required_by": list(v["required_by"])} for v in impact["verification"]}
    decisions = {d["id"]: dict(d) for d in impact["governing_decisions"]}
    required_decisions = set(change.decisions)
    for policy in snapshot.model.policies:
        if policy.id not in change.policies:
            continue
        required_decisions.add(policy.decision)
        for check in policy.checks:
            add_reason(snapshot.model, obligations, check, policy.id, policy.decision,
                       policy_obligation(snapshot.model, policy, verification=True))
    for decision in snapshot.model.decisions:
        if decision.id in required_decisions:
            decisions[decision.id] = {"id": decision.id, "path": decision.path, "status": decision.status}
    for criterion in change.acceptance:
        if not criterion.checks:
            gaps.append(f"Acceptance criterion has no verification: {criterion.id}")
        for check in criterion.checks:
            add_reason(snapshot.model, obligations, check, criterion.id, "change-contract")
    result = {**impact, "task": change.objective, "verification": [obligations[k] for k in sorted(obligations)],
              "governing_decisions": [decisions[k] for k in sorted(decisions)],
              "unknowns": sorted(set(gaps)), "assessment": "partial" if gaps else "complete"}
    details = {d["message"]: d for d in impact["unknown_details"]}
    result["unknown_details"] = [details.get(message, {"message": message, "category": "scope",
                                                      "obligation": "required"})
                                 for message in result["unknowns"]]
    result.pop("revision", None)
    result["revision"] = digest(result)
    return result


def acceptance_results(change: Change, verification: list[dict]) -> list[dict]:
    checks = {v["id"]: v["status"] for v in verification}
    results = []
    for criterion in change.acceptance:
        states = [checks.get(c, "not_executed") for c in criterion.checks]
        status = "failed" if "failed" in states else (
            "passed" if states and all(s == "passed" for s in states) else "unknown")
        results.append({"id": criterion.id, "requirement": criterion.requirement,
                        "checks": list(criterion.checks), "status": status})
    return results
