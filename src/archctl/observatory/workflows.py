from __future__ import annotations

from pathlib import Path
from typing import Callable

from archctl.core.io import InputError, digest
from archctl.core.models import Finding, Observations, Snapshot
from archctl.integrations.process import (authoring_freshness, authority_matches,
                                         run_checks)


def run_workflow(root: Path, snapshot: Snapshot, baseline: Snapshot, observations: Observations,
                 workflow_id: str, *, environment: str,
                 freshness: Callable[[], list[Finding]]) -> dict:
    index = {w.id: w for w in snapshot.model.workflows}
    if workflow_id not in index:
        raise InputError(f"Unknown workflow: {workflow_id}")
    workflow = index[workflow_id]
    results = run_checks(root, snapshot, baseline, observations, list(workflow.verification),
                        execute=True, environment=environment, freshness=freshness)
    gaps = freshness() + authoring_freshness(root, snapshot)
    approved = authority_matches(snapshot, baseline)
    status = "failed" if any(r["status"] == "failed" for r in results) else (
        "passed" if approved and not gaps and all(r["status"] == "passed" for r in results) else "unknown")
    report = {"schema_version": "archctl.workflow-result.v2", "workflow": workflow_id,
              "status": status, "model_revision": snapshot.revision, "baseline_revision": baseline.revision,
              "source_digest": observations.source_digest, "verification": results,
              "gaps": [f.to_dict() for f in gaps], "authority_changed": not approved,
              "runtime_observations": []}
    # A passing command is a verification result, never a fabricated runtime trace.
    report["revision"] = digest(report)
    return report
