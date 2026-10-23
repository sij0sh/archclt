#!/usr/bin/env python3
"""Build self-contained JSON Schemas from one set of exchange definitions."""

from pathlib import Path

from archctl.core.io import write_json


def make_schemas() -> dict:
    text = {"type": "string", "minLength": 1}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    ident = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,127}$"}
    def ref(name):
        return {"$ref": f"#/$defs/{name}"}
    def array(item, *, nonempty=False, unique=False):
        result = {"type": "array", "items": item}
        if nonempty:
            result["minItems"] = 1
        if unique:
            result["uniqueItems"] = True
        return result
    def enum(*values):
        return {"enum": list(values)}
    def object_(props, optional=()):
        return {"type": "object", "additionalProperties": False, "properties": props,
                "required": sorted(set(props) - set(optional))}
    def entity(props, optional=()):
        return object_({"id": ident, **props}, optional)
    ids = array(ident, unique=True)
    texts = array(text, unique=True)
    kind = enum("imports", "calls", "reads", "writes", "publishes", "consumes")
    state = enum("passed", "failed", "unknown", "not_executed")
    pins = {"type": "object", "additionalProperties": sha}
    definitions = {
        "domain": entity({"name": text, "owners": array(text, nonempty=True, unique=True)}),
        "component": entity({"name": text, "domain": ident,
            "kind": enum("service", "library", "database", "queue", "external", "ui"),
            "paths": array(text, nonempty=True, unique=True)}),
        "decision": entity({"status": enum("proposed", "accepted", "deprecated", "superseded", "rejected"),
                            "title": text, "components": ids, "supersedes": ids, "path": text, "body": text}),
        "relationship": entity({"source": ident, "target": ident, "kind": kind, "decision": ident, "required": {"type": "boolean"}}),
        "interface": entity({"provider": ident, "consumers": array(ident, nonempty=True, unique=True),
                             "verification": array(ident, nonempty=True, unique=True), "decision": ident}),
        "policy": entity({"kind": enum("forbidden_dependency", "required_verification"),
            "decision": ident, "severity": enum("error", "warning"), "source": {"type": "string"},
            "target": {"type": "string"}, "kinds": array(kind, unique=True), "components": ids, "checks": ids}),
        "verification-target": entity({"kind": enum("contract", "integration", "workflow", "architecture"),
            "command": array(text, nonempty=True), "cwd": text,
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
            "components": array(ident, nonempty=True, unique=True)}),
        "workflow": entity({"participants": array(ident, nonempty=True, unique=True),
                            "verification": array(ident, nonempty=True, unique=True), "decision": ident}),
        "finding": object_({"id": text, "status": state, "message": text,
            "severity": enum("info", "warning", "error"), "decision": {"type": "string"}, "evidence_refs": texts}),
        "verification-result": object_({"id": ident, "status": state, "message": text,
            "model_revision": sha, "source_digest": sha, "environment": text,
            "command": array(text, nonempty=True), "cwd": text, "command_digest": sha,
            "returncode": {"type": ["integer", "null"]}, "duration_seconds": {"type": "number", "minimum": 0},
            "stdout": {"type": "string"}, "stderr": {"type": "string"}, "output_truncated": {"type": "boolean"}}),
    }
    definitions["model"] = object_({"system_id": ident, "name": text,
        **{name: array(ref(target)) for name, target in {
            "domains": "domain", "components": "component", "decisions": "decision", "relationships": "relationship",
            "interfaces": "interface", "policies": "policy", "verification": "verification-target", "workflows": "workflow"}.items()}})
    def contract(version, props, optional=()):
        return object_({"schema_version": {"const": version}, **props}, optional)
    schemas = {}
    schemas["snapshot"] = contract("archctl.snapshot.v2", {"revision": sha, "model": ref("model"), "sources": pins})
    schemas["change"] = contract("archctl.change.v2", {
        "id": ident, "objective": text,
        "scope": object_({"components": array(ident, nonempty=True, unique=True),
                          "excluded_components": ids, "paths": texts}, optional=("excluded_components", "paths")),
        "acceptance": array(entity({"requirement": text, "checks": ids}), nonempty=True),
        "constraints": object_({"decisions": ids, "policies": ids}), "open_questions": texts})
    evidence = object_({"id": text, "kind": enum("static", "runtime", "derived"), "location": text, "description": text})
    coverage = object_({"analysis": enum("static", "runtime"), "status": enum("complete", "partial"),
        "components": array(ident, nonempty=True, unique=True), "relationship_kinds": array(kind, nonempty=True, unique=True), "gaps": texts})
    coverage["allOf"] = [{"if": {"properties": {"status": {"const": "complete"}}},
                          "then": {"properties": {"analysis": {"const": "static"}, "gaps": {"maxItems": 0}}}}]
    schemas["evidence"] = contract("archctl.evidence.v2", {
        "producer": object_({"name": text, "version": text}),
        "source": object_({"revision": text, "files": {**pins, "minProperties": 1}}),
        "coverage": coverage, "evidence": array(evidence), "edges": array(object_({
            "id": text, "source": ident, "target": ident, "kind": kind, "origin": enum("static", "runtime"),
            "evidence_refs": array(text, nonempty=True, unique=True)}))})
    definitions["impact"] = contract("archctl.impact.v2", {
        "revision": sha, "task": text, "model_revision": sha,
        "source": object_({"revision": text, "digest": sha}), "changed_paths": texts,
        "scope": enum("all", "changed"),
        "affected_components": array(entity({"basis": array(text, nonempty=True, unique=True), "evidence_refs": texts})),
        "governing_decisions": array(entity({"path": text, "status": enum("accepted", "deprecated")})),
        "verification": array(entity({"basis": {"const": "declared_requirement"}, "status": {"const": "not_executed"},
            "required_by": array(entity({"decision": ident}), nonempty=True)})),
        "unknowns": texts, "assessment": enum("partial", "complete")})
    schemas["impact"] = ref("impact")
    schemas["guard"] = contract("archctl.guard.v2", {"revision": sha,
        "status": enum("passed", "failed", "unknown"), "model_revision": sha, "baseline_revision": sha,
        "source_revision": text, "source_digest": sha, "impact_revision": sha, "authority_changed": {"type": "boolean"},
        "findings": array(ref("finding")), "verification": array(ref("verification-result")), "impact": ref("impact")})
    schemas["workflow-result"] = contract("archctl.workflow-result.v2", {
        "revision": sha, "status": enum("passed", "failed", "unknown"), "workflow": ident,
        "model_revision": sha, "baseline_revision": sha, "source_digest": sha,
        "verification": array(ref("verification-result")), "gaps": array(ref("finding")),
        "authority_changed": {"type": "boolean"}, "runtime_observations": {"const": []}})
    schemas["reconciliation"] = contract("archctl.reconciliation.v2", {
        "model_revision": sha, "source_revision": text, "source_digest": sha,
        "findings": array(ref("finding")), "authority_updated": {"const": False}},
        optional=("ignored",))
    schemas["reconciliation"]["properties"]["ignored"] = array(object_({
        "source": ident, "target": ident, "kind": kind, "reason": text,
        "evidence_refs": texts}))
    schemas["intent"] = contract("archctl.intent.v2", {"model_revision": sha,
        "native_briefcase_format": {"const": False}, "model": ref("model")})
    schemas["verification-result"] = ref("verification-result")
    # Local gate reports compose the stable contracts and retain detailed
    # evidence in adjacent artifacts. Permit additive diagnostic fields.
    schemas["gate"] = {"type": "object", "required": ["schema_version", "status", "gate_status", "baseline_sha", "approval", "stages"],
        "properties": {"schema_version": {"const": "archctl.gate.v2"},
                       "status": enum("passed", "failed", "unknown", "error"),
                       "gate_status": enum("passed", "failed", "unknown", "error"),
                       "baseline_sha": {"type": "string", "pattern": "^([0-9a-f]{40}|[0-9a-f]{64})$"},
                       "approval": {"const": "not_assessed"},
                       "stages": {"type": "object", "additionalProperties": enum("passed", "failed", "unknown", "error")},
                       "verification": array(ref("verification-result"))}}
    strength = enum("required", "advisory")
    reason = object_({"id": text, "decision": text, "obligation": strength})
    definitions["model"]["properties"]["enforcement"] = enum("strict", "selective")
    definitions["model"]["required"].append("enforcement")
    for name in ("policy", "finding", "verification-result"):
        definitions[name]["properties"]["obligation"] = strength
        definitions[name]["required"].append("obligation")
    definitions["verification-result"]["properties"]["required_by"] = array(reason)
    definitions["verification-result"]["required"].append("required_by")
    impact = definitions["impact"]
    impact["properties"]["unknown_details"] = array(object_({"message": text,
        "category": enum("freshness", "coverage", "scope", "drift"), "obligation": strength}))
    impact["required"].append("unknown_details")
    check = impact["properties"]["verification"]["items"]
    check["properties"].update(obligation=strength, required_by=array(reason, nonempty=True))
    check["required"].append("obligation")
    schemas["gate"]["properties"].update(enforcement=enum("strict", "selective"), guarantee=text)
    # Error reports created before compilation legitimately lack these diagnostics.
    for name, schema in schemas.items():
        schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema",
                       "$id": f"urn:archctl:v2:{name}", "$defs": definitions})
    return schemas


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "contracts/v2"
    for name, schema in make_schemas().items():
        write_json(destination / f"{name}.schema.json", schema)
    print("Wrote unified v2 schemas")
