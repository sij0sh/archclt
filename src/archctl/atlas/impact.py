"""Conservative change obligations from approved declarations and observed edges."""

from __future__ import annotations

from collections import defaultdict

from archctl.core.contracts import version
from archctl.core.enforcement import add_reason
from archctl.core.io import digest, relative_path, string
from archctl.core.models import Observations, Snapshot, owners


def build_impact(snapshot: Snapshot, observations: Observations, paths: list[str],
                 task: str, freshness: list, *, all_components: bool = False) -> dict:
    model = snapshot.model
    task = string(task, "task")
    paths = sorted({relative_path(p, "changed path") for p in paths})
    affected: dict[str, set[str]] = defaultdict(set)
    evidence_refs: dict[str, set[str]] = defaultdict(set)
    gaps = []
    details = []
    def gap(message: str, category: str) -> None:
        gaps.append(message)
        details.append({"message": message, "category": category, "obligation": "required"})
    for finding in freshness:
        gap(finding.message, "freshness")
    for message in observations.coverage.gaps:
        gap(message, "coverage")
    if all_components:
        for component in model.components:
            affected[component.id].add("repository_check")
    for path in paths:
        owned = owners(path, model.components)
        if not owned:
            if path not in dict(snapshot.sources):
                gap(f"Changed path has no declared component: {path}", "scope")
        elif len(owned) > 1:
            gap(f"Changed path maps to multiple components: {path}: {', '.join(owned)}", "scope")
        for owner in owned:
            affected[owner].add("direct_change")
    if not paths and not all_components:
        gap("No concrete changed paths or repository-wide scope supplied", "scope")
    # Traverse consumers backwards. All supported relation kinds are conservative
    # candidates; a graph edge is not a guarantee that behavior will change.
    progress = True
    while progress:
        before = set(affected)
        for edge in observations.edges:
            if edge.target in affected:
                affected[edge.source].add("observed_consumer")
                evidence_refs[edge.source].update(edge.evidence_refs)
        for interface in model.interfaces:
            if interface.provider in affected:
                for consumer in interface.consumers:
                    affected[consumer].add("declared_consumer")
        for workflow in model.workflows:
            if set(workflow.participants) & affected.keys():
                for participant in workflow.participants:
                    affected[participant].add("workflow_participant")
        progress = before != set(affected)
    covered = set(observations.coverage.components)
    missing = set(affected) - covered
    if missing:
        gap(f"Affected components lack analysis coverage: {', '.join(sorted(missing))}", "coverage")
    if observations.coverage.status != "complete" or observations.coverage.analysis != "static":
        gap("Analysis is partial or runtime-only; undiscovered consumers remain possible", "coverage")
    decisions: set[str] = set()
    obligations: dict[str, dict] = {}
    def require(check: str, basis: str, decision: str, obligation: str = "required") -> None:
        add_reason(obligations, check, basis, decision, obligation)
        decisions.add(decision)
    for decision in model.decisions:
        if set(decision.components) & affected.keys() and decision.status in {"accepted", "deprecated"}:
            decisions.add(decision.id)
    for policy in model.policies:
        participants = set(policy.components) | {policy.source, policy.target}
        if participants & affected.keys():
            decisions.add(policy.decision)
            for check in policy.checks:
                require(check, policy.id, policy.decision, policy.obligation)
    for interface in model.interfaces:
        if {interface.provider, *interface.consumers} & affected.keys():
            for check in interface.verification:
                require(check, interface.id, interface.decision)
    for workflow in model.workflows:
        if set(workflow.participants) & affected.keys():
            for check in workflow.verification:
                require(check, workflow.id, workflow.decision)
    decision_index = {d.id: d for d in model.decisions}
    report = {"schema_version": version("impact"), "task": task,
              "model_revision": snapshot.revision,
              "source": {"revision": observations.source_revision, "digest": observations.source_digest},
              "changed_paths": paths, "scope": "all" if all_components else "changed",
              "affected_components": [{"id": ident, "basis": sorted(bases),
                                       "evidence_refs": sorted(evidence_refs[ident])}
                                      for ident, bases in sorted(affected.items())],
              "governing_decisions": [{"id": ident, "path": decision_index[ident].path,
                                       "status": decision_index[ident].status} for ident in sorted(decisions)],
              "verification": [obligations[key] for key in sorted(obligations)],
              "unknowns": sorted(set(gaps)), "assessment": "partial" if gaps else "complete"}
    report["unknown_details"] = sorted(details, key=lambda d: (d["category"], d["message"]))
    report["revision"] = digest(report)
    return report
