"""Read evidence-only exchanges; never turn observations into approved intent."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from archctl.core.io import (InputError, choice, contained, file_digest, items,
                             load_document, obj, relative_path, source_files,
                             string, strings)
from archctl.core.models import (KINDS, Coverage, Edge, Evidence, Finding,
                                 Observations, Snapshot)


def parse_evidence(value: Any, snapshot: Snapshot) -> Observations:
    data = obj(value, "evidence bundle", {"schema_version", "producer", "source", "coverage", "evidence", "edges"},
               {"schema_version", "producer", "source", "coverage", "evidence", "edges"})
    if data["schema_version"] != "archctl.evidence.v2":
        raise InputError("Expected normalized archctl.evidence.v2; native Briefcase exports need an explicit mapping")
    producer = obj(data["producer"], "producer", {"name", "version"}, {"name", "version"})
    source = obj(data["source"], "source", {"revision", "files"}, {"revision", "files"})
    if not isinstance(source["files"], dict) or not source["files"]:
        raise InputError("source.files must be a nonempty path-to-SHA256 object")
    for key, val in source["files"].items():
        relative_path(key, "source.files")
        if not isinstance(val, str) or not re.fullmatch("[0-9a-f]{64}", val):
            raise InputError(f"source.files[{key}] must be a lowercase SHA256")
    c = obj(data["coverage"], "coverage", {"analysis", "status", "components", "relationship_kinds", "gaps"},
            {"analysis", "status", "components", "relationship_kinds", "gaps"})
    coverage = Coverage(choice(c["analysis"], {"static", "runtime"}, "coverage.analysis"),
                        choice(c["status"], {"complete", "partial"}, "coverage.status"),
                        strings(c["components"], "coverage.components", nonempty=True),
                        strings(c["relationship_kinds"], "coverage.relationship_kinds", nonempty=True),
                        strings(c["gaps"], "coverage.gaps"))
    components = {c.id for c in snapshot.model.components}
    if not set(coverage.components) <= components or not set(coverage.relationship_kinds) <= KINDS:
        raise InputError("Coverage references an unknown component or relationship kind")
    if coverage.status == "complete" and (coverage.gaps or coverage.analysis == "runtime"):
        raise InputError("Runtime sampling or known gaps cannot certify complete static coverage")
    evidence = []
    for item in items(data["evidence"], "evidence"):
        e = obj(item, "evidence item", {"id", "kind", "location", "description"},
                {"id", "kind", "location", "description"})
        evidence.append(Evidence(string(e["id"], "evidence.id"),
                        choice(e["kind"], {"static", "runtime", "derived"}, "evidence.kind"),
                        string(e["location"], "evidence.location"), string(e["description"], "evidence.description")))
    index = {e.id: e for e in evidence}
    if len(index) != len(evidence):
        raise InputError("Duplicate evidence ID")
    edges = []
    for item in items(data["edges"], "edges"):
        e = obj(item, "edge", {"id", "source", "target", "kind", "origin", "evidence_refs"},
                {"id", "source", "target", "kind", "origin", "evidence_refs"})
        edge = Edge(string(e["id"], "edge.id"), string(e["source"], "edge.source"),
                    string(e["target"], "edge.target"), choice(e["kind"], KINDS, "edge.kind"),
                    choice(e["origin"], {"static", "runtime"}, "edge.origin"),
                    strings(e["evidence_refs"], "edge.evidence_refs", nonempty=True))
        if {edge.source, edge.target} - components:
            raise InputError(f"{edge.id} references an unknown component")
        if set(edge.evidence_refs) - index.keys():
            raise InputError(f"{edge.id} has dangling evidence references")
        if not any(index[ref].kind == edge.origin for ref in edge.evidence_refs):
            raise InputError(f"{edge.id} needs {edge.origin} evidence, not only a derived assertion")
        if edge.origin != coverage.analysis:
            raise InputError("One bundle must use one analysis scope; import static and runtime evidence separately")
        if not {edge.source, edge.target} <= set(coverage.components) or edge.kind not in coverage.relationship_kinds:
            raise InputError(f"{edge.id} falls outside its declared analysis scope")
        edges.append(edge)
    if len({e.id for e in edges}) != len(edges):
        raise InputError("Duplicate edge ID")
    return Observations(string(producer["name"], "producer.name"), string(producer["version"], "producer.version"),
                        string(source["revision"], "source.revision"), tuple(sorted(source["files"].items())),
                        coverage, tuple(sorted(evidence, key=lambda e: e.id)), tuple(sorted(edges, key=lambda e: e.id)))


def read_evidence(path: Path, snapshot: Snapshot) -> Observations:
    return parse_evidence(load_document(path), snapshot)


def check_freshness(root: Path, snapshot: Snapshot, observations: Observations) -> list[Finding]:
    """Check all pins, including new/deleted files in declared component scopes."""
    findings = []
    pins = dict(observations.files)
    owners: dict[str, list[str]] = {}
    for rel, expected in pins.items():
        path = contained(root, rel)
        if not path.is_file() or file_digest(path) != expected:
            findings.append(Finding(f"stale:{rel}", "unknown", f"Evidence pin is stale or missing: {rel}"))
    for component in snapshot.model.components:
        if component.id not in observations.coverage.components:
            continue
        actual = source_files(root, component.paths)
        for rel in actual:
            owners.setdefault(rel, []).append(component.id)
        if not actual:
            findings.append(Finding(f"empty-scope:{component.id}", "unknown",
                                    f"No source files found for covered component {component.id}"))
        for rel in actual.keys() - pins.keys():
            findings.append(Finding(f"unpinned:{rel}", "unknown", f"New or unpinned source file: {rel}"))
    for rel, components in owners.items():
        if len(components) > 1:
            findings.append(Finding(f"ambiguous:{rel}", "unknown",
                                    f"Source file has multiple component bindings: {rel}: {', '.join(sorted(components))}"))
    return sorted(findings, key=lambda f: f.id)
