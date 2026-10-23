from __future__ import annotations

from archctl.core.contracts import version
from archctl.core.models import Finding, Observations, Snapshot

INTRA_COMPONENT_REASON = "Intra-component import is not an inter-component architectural relationship"


def reconcile(snapshot: Snapshot, observations: Observations, freshness: list[Finding]) -> dict:
    model = snapshot.model
    declared = {(r.source, r.target, r.kind): r for r in model.relationships}
    observed = {(e.source, e.target, e.kind) for e in observations.edges}
    findings = list(freshness)
    ignored: list[dict] = []
    for edge in observations.edges:
        key = edge.source, edge.target, edge.kind
        if edge.source == edge.target:
            # An import inside one component is not a relationship between
            # components. It is reported, never silently dropped.
            ignored.append({"source": edge.source, "target": edge.target, "kind": edge.kind,
                            "reason": INTRA_COMPONENT_REASON,
                            "evidence_refs": sorted(edge.evidence_refs)})
            continue
        matching = declared.get(key)
        findings.append(Finding(f"observed:{edge.id}", "passed" if matching and not freshness else "unknown",
            f"{edge.source} -> {edge.target} ({edge.kind}): " + ("declared relationship" if matching else "undeclared relationship requires review"),
            "info" if matching else "warning", matching.decision if matching else "", edge.evidence_refs,
            "required" if (matching and matching.required) or (not matching and model.enforcement == "strict") else "advisory"))
    for relation in model.relationships:
        if (relation.source, relation.target, relation.kind) not in observed:
            complete = not freshness and observations.covers(relation.source, relation.target, (relation.kind,))
            status = "failed" if relation.required and complete else "unknown"
            findings.append(Finding(f"missing:{relation.id}", status,
                f"Declared relationship {relation.id} has no current supporting observation",
                "error" if relation.required else "warning", relation.decision,
                obligation="required" if relation.required else "advisory"))
    for policy in model.policies:
        if policy.kind != "forbidden_dependency":
            continue
        violations = [e for e in observations.edges if e.source == policy.source and e.target == policy.target and e.kind in policy.kinds]
        if violations:
            findings.append(Finding(f"violation:{policy.id}", "unknown" if freshness else "failed",
                f"Observed relationship contradicts {policy.id}", policy.severity, policy.decision,
                tuple(sorted({ref for e in violations for ref in e.evidence_refs})),
                policy.obligation))
    return {"schema_version": version("reconciliation"), "model_revision": snapshot.revision,
            "source_revision": observations.source_revision, "source_digest": observations.source_digest,
            "findings": [f.to_dict() for f in sorted(findings, key=lambda f: f.id)],
            "ignored": sorted(ignored, key=lambda item: (item["source"], item["target"], item["kind"])),
            "authority_updated": False}
