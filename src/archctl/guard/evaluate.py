from __future__ import annotations

from pathlib import Path
from typing import Callable

from archctl.core.enforcement import version
from archctl.core.io import digest
from archctl.core.models import Finding, Observations, Snapshot
from archctl.integrations.process import (authoring_freshness, authority_matches,
                                         run_checks)


def gate_status(findings: list[Finding], verification: list[dict]) -> str:
    states = [f.status for f in findings if (f.obligation == "required" if f.obligation else f.severity == "error")] + [
        v["status"] for v in verification if v.get("obligation", "required") == "required"]
    if "failed" in states:
        return "failed"
    if any(state in {"unknown", "not_executed"} for state in states):
        return "unknown"
    return "passed"


def check(root: Path, snapshot: Snapshot, baseline: Snapshot, observations: Observations,
          impact: dict, *, execute: bool, environment: str,
          freshness: Callable[[], list[Finding]], scope_components: set[str] | None = None,
          required_policies: set[str] | None = None) -> dict:
    stale = freshness()
    findings = list(stale)
    approved = authority_matches(snapshot, baseline)
    findings.append(Finding("authority", "passed" if approved else "unknown",
        "Candidate intent matches the trusted baseline" if approved else
        "Architecture authority changed; obtain operator review and establish a reviewed baseline outside this gate"))
    for i, gap in enumerate(impact["unknowns"]):
        findings.append(Finding(f"impact-gap:{i}", "unknown", gap))
    for policy in snapshot.model.policies:
        if policy.kind != "forbidden_dependency":
            continue
        if (scope_components is not None and policy.id not in (required_policies or set())
                and not {policy.source, policy.target} & scope_components):
            continue
        edges = [e for e in observations.edges if e.source == policy.source
                 and e.target == policy.target and e.kind in policy.kinds]
        if stale:
            status, message = "unknown", "Current evidence is stale"
        elif edges:
            status, message = "failed", f"Forbidden dependency: {policy.source} -> {policy.target}"
        elif observations.covers(policy.source, policy.target, policy.kinds):
            status, message = "passed", "No prohibited relationship found within complete declared static scope"
        else:
            status, message = "unknown", "Insufficient static coverage to establish absence of the prohibited relationship"
        findings.append(Finding(policy.id, status, message, policy.severity, policy.decision,
                                tuple(sorted({ref for e in edges for ref in e.evidence_refs})),
                                policy.obligation))
    for relation in snapshot.model.relationships:
        if not relation.required:
            continue
        if scope_components is not None and not {relation.source, relation.target} & scope_components:
            continue
        edges = [e for e in observations.edges if (e.source, e.target, e.kind) ==
                 (relation.source, relation.target, relation.kind)]
        status = "unknown" if stale else ("passed" if edges else
                 "failed" if observations.covers(relation.source, relation.target, (relation.kind,)) else "unknown")
        findings.append(Finding(f"required:{relation.id}", status,
                                f"Required relationship: {relation.source} -> {relation.target}",
                                decision=relation.decision,
                                evidence_refs=tuple(sorted({ref for e in edges for ref in e.evidence_refs}))))
    # Do not run reviewed commands against already invalid/uncertain evidence.
    runnable = execute and gate_status(findings, []) == "passed"
    verification = run_checks(root, snapshot, baseline, observations,
        [v["id"] for v in impact["verification"]], execute=runnable,
        environment=environment, freshness=freshness)
    if execute and not runnable:
        for result in verification:
            if result["status"] == "not_executed":
                result["message"] = "Structural, impact, or authority gate blocks execution"
    obligations = {v["id"]: v for v in impact["verification"]}
    for result in verification:
        result["obligation"] = obligations[result["id"]]["obligation"]
        result["required_by"] = obligations[result["id"]]["required_by"]
    final_freshness = freshness() + authoring_freshness(root, snapshot)
    seen = {f.id for f in findings}
    findings.extend(f for f in final_freshness if f.id not in seen)
    report = {"schema_version": version("guard"), "status": gate_status(findings, verification),
              "model_revision": snapshot.revision, "baseline_revision": baseline.revision,
              "source_revision": observations.source_revision, "source_digest": observations.source_digest,
              "impact_revision": impact["revision"], "authority_changed": not approved,
              "findings": [f.to_dict() for f in findings], "verification": verification,
              "impact": impact}
    report["revision"] = digest(report)
    return report
