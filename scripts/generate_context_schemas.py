"""Generate independent advisory contracts without changing v2 gate semantics."""

from pathlib import Path
from archctl.core.io import write_json


def make_schemas() -> dict:
    text = {"type": "string", "minLength": 1}
    blank = {"type": "string"}
    texts = {"type": "array", "items": text, "uniqueItems": True}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    boolean = {"type": "boolean"}
    number = {"type": "number", "minimum": 0}
    def enum(*values): return {"enum": list(values)}
    def array(item): return {"type": "array", "items": item}
    def obj(props, optional=()):
        return {"type": "object", "properties": props, "additionalProperties": False,
                "required": sorted(set(props) - set(optional))}
    def contract(name, props, optional=()):
        return obj({"schema_version": {"const": f"archctl.{name}.v1"}, **props}, optional)
    pins = {"type": "object", "additionalProperties": sha}
    origin = enum("observed", "user_stated", "agent_inferred", "agent_chosen")
    memory_props = {"id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,127}$"},
        "statement": {**text, "maxLength": 4000}, "rationale": {**text, "maxLength": 12000},
        "origin": origin, "references": {**texts, "minItems": 1, "maxItems": 64}, "components": texts,
        "paths": texts, "topics": texts, "assumptions": texts, "supersedes": texts, "contradicts": texts,
        "source_files": pins, "revision": sha}
    memory = contract("memory", memory_props,
        optional=("components", "paths", "topics", "assumptions", "supersedes", "contradicts", "source_files", "revision"))
    memory_freshness = obj({"status": enum("current", "stale", "unverified"), "changed_paths": texts, "new_paths": texts})
    summary = contract("memory", {**memory_props, "score": number, "freshness": memory_freshness,
        "superseded_by": {"type": ["string", "null"]}, "relevance": enum("lexical_and_scope", "related_record"),
        "excerpt_truncated": boolean})
    result = obj({"status": enum("passed", "failed", "unknown", "not_executed"), "message": blank,
        "returncode": {"type": ["integer", "null"]}, "duration_seconds": number,
        "stdout": blank, "stderr": blank, "output_truncated": boolean})
    execution_props = {"id": text, "origin": enum("archctl", "harness"), "task": text,
        "command": {**array(text), "minItems": 1}, "cwd": text,
        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300}, "environment": text,
        "started_at": text, "source": obj({"paths": texts,
            "files": {"type": "object", "additionalProperties": {"anyOf": [sha, {"type": "null"}]}},
            "gaps": texts, "stable_during_execution": boolean}), "result": result,
        "references": texts, "revision": sha}
    applicability = obj({"status": enum("current", "stale", "unverified"), "changed_paths": texts,
                         "limitations": array(text), "meaning": text})
    execution = contract("execution", execution_props, optional=("revision",))
    execution_view = contract("execution", {**execution_props, "applicability": applicability})
    edge = obj({"id": text, "source": text, "target": text,
        "kind": enum("imports", "calls", "reads", "writes", "publishes", "consumes"),
        "origin": enum("static", "runtime"), "evidence_refs": texts})
    concern = obj({"kind": text, "references": texts, "message": text, "evidence_refs": texts,
                   "freshness": enum("current", "stale")}, optional=("evidence_refs", "freshness"))
    context = contract("context", {"status": {"const": "assembled"}, "task": text, "planned_paths": texts,
        "context_references": array(text), "components": array(obj({"id": text, "paths": texts, "aliases": texts,
            "purpose": blank, "origin": enum("provisional", "declared", "override")})),
        "potential_impact": array(obj({"id": text, "basis": text, "path": array(edge), "edit_required": {"const": False}})),
        "memories": array(summary), "decisions": array(obj({"id": text, "status": text, "path": text,
            "rationale_excerpt": text, "excerpt_truncated": boolean, "origin": {"const": "declared"}, "score": number})),
        "source_candidates": array(obj({"path": text, "start_line": {"type": "integer", "minimum": 1},
            "excerpt": blank, "origin": {"const": "source"}, "sha256": sha, "score": number,
            "components": texts, "file_excerpt_truncated": boolean, "meaning": text})),
        "observed_edges": array(edge), "evidence": array(obj({"id": text,
            "kind": enum("static", "runtime", "derived"), "location": text, "description": text})),
        "proposed_dependencies": array(obj({"source": text, "target": text, "kind": {"const": "imports"},
            "origin": {"const": "hypothetical"}, "cycle": enum("within_component", "possible_from_stale_evidence", "supported_path", "not_observed"),
            "return_path": array(edge), "constraint_refs": texts, "meaning": text})),
        "verification_suggestions": array(obj({"id": text, "command": array(text), "cwd": text,
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
            "basis": {"const": "existing_model_check"}, "status": {"const": "not_executed"}})),
        "concerns": array(concern), "limitations": array(obj({"category": text, "affects": texts, "message": text})),
        "executions": array(execution_view),
        "source": obj({"model_revision": {"anyOf": [sha, {"type": "null"}]},
            "evidence_revision": {"type": ["string", "null"]}, "evidence_freshness": enum("current", "stale", "unavailable")}),
        "retrieval": obj({"files_considered": number, "files_read": number, "search_truncated": boolean,
            "matches": number, "returned": number, "retrieval": text}),
        "totals": obj({name: number for name in ("components", "potential_impact", "memories", "decisions",
            "observed_edges", "verification_suggestions", "executions")}),
        "decision_prompts": array(text), "meaning": text, "revision": sha})
    config = contract("context-config", {"components": array(obj({"id": text,
        "paths": {**texts, "minItems": 1}, "aliases": texts, "purpose": text}, optional=("aliases", "purpose")))})
    schemas = {"memory": memory, "context": context, "execution": execution, "context-config": config}
    for name, schema in schemas.items():
        schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"urn:archctl:context:v1:{name}"})
    return schemas


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "contracts/context/v1"
    for name, schema in make_schemas().items():
        write_json(destination / f"{name}.schema.json", schema)
