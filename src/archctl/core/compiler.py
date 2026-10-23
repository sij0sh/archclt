"""Compile human intent once; all feature modules consume this snapshot."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import re
from typing import Any

import yaml

from archctl.core.io import (InputError, UniqueLoader, choice, contained, digest,
                             file_digest, items, load_document, obj, relative_path,
                             stable_id, string, strings)
from archctl.core.models import (ACTIVE_DECISIONS, KINDS, Component, Decision,
                                 Domain, Interface, Model, Policy, Relationship,
                                 Snapshot, Verification, Workflow)


def _objects(data: dict, name: str, cls: type) -> list[dict]:
    allowed = {f.name for f in fields(cls)}
    return [obj(v, f"{name}[{i}]", allowed) for i, v in enumerate(items(data.get(name, []), name))]


def parse_model(data: Any) -> Model:
    obj(data, "model", {f.name for f in fields(Model)}, {"system_id", "name"})
    enforcement = data.get("enforcement", "strict")
    if "enforcement" in data:
        choice(enforcement, {"strict", "selective"}, "model.enforcement")
    try:
        domains = tuple(Domain(stable_id(v["id"], "domain.id"), string(v["name"], "domain.name"),
                               strings(v["owners"], "domain.owners", nonempty=True))
                        for v in _objects(data, "domains", Domain))
        components = tuple(Component(
            stable_id(v["id"], "component.id"), string(v["name"], "component.name"),
            stable_id(v["domain"], "component.domain"),
            choice(v["kind"], {"service", "library", "database", "queue", "external", "ui"}, "component.kind"),
            tuple(relative_path(p, "component.paths", glob=True)
                  for p in strings(v["paths"], "component.paths", nonempty=True)))
            for v in _objects(data, "components", Component))
        decisions = tuple(Decision(
            stable_id(v["id"], "decision.id"),
            choice(v["status"], {"proposed", "accepted", "deprecated", "superseded", "rejected"}, "decision.status"),
            string(v["title"], "decision.title"), strings(v["components"], "decision.components"),
            strings(v.get("supersedes", []), "decision.supersedes"),
            relative_path(v["path"], "decision.path"), string(v["body"], "decision.body"))
            for v in _objects(data, "decisions", Decision))
        relationships = []
        for v in _objects(data, "relationships", Relationship):
            required = v.get("required", False)
            if type(required) is not bool:
                raise InputError("relationship.required must be a boolean")
            relationships.append(Relationship(
                stable_id(v["id"], "relationship.id"), stable_id(v["source"], "relationship.source"),
                stable_id(v["target"], "relationship.target"), choice(v["kind"], KINDS, "relationship.kind"),
                stable_id(v["decision"], "relationship.decision"), required))
        interfaces = tuple(Interface(
            stable_id(v["id"], "interface.id"), stable_id(v["provider"], "interface.provider"),
            strings(v["consumers"], "interface.consumers", nonempty=True),
            strings(v["verification"], "interface.verification", nonempty=True),
            stable_id(v["decision"], "interface.decision"))
            for v in _objects(data, "interfaces", Interface))
        policies = []
        for v in _objects(data, "policies", Policy):
            kind = choice(v["kind"], {"forbidden_dependency", "required_verification"}, "policy.kind")
            common = dict(id=stable_id(v["id"], "policy.id"), kind=kind,
                          decision=stable_id(v["decision"], "policy.decision"),
                          severity=choice(v.get("severity", "error"), {"error", "warning"}, "policy.severity"))
            common["obligation"] = choice(v.get("obligation"), {"required", "advisory"}, "policy.obligation")
            if kind == "forbidden_dependency":
                if v.get("checks") or v.get("components"):
                    raise InputError("forbidden_dependency cannot contain checks or components")
                kinds = strings(v.get("kinds", ["imports"]), "policy.kinds", nonempty=True)
                if not set(kinds) <= KINDS:
                    raise InputError("policy.kinds includes an unsupported relationship kind")
                policies.append(Policy(**common, source=stable_id(v["source"], "policy.source"),
                                       target=stable_id(v["target"], "policy.target"), kinds=kinds))
            else:
                if v.get("source") or v.get("target") or v.get("kinds"):
                    raise InputError("required_verification cannot contain dependency selectors")
                policies.append(Policy(**common,
                    components=strings(v["components"], "policy.components", nonempty=True),
                    checks=strings(v["checks"], "policy.checks", nonempty=True)))
        verification = []
        for v in _objects(data, "verification", Verification):
            timeout = v.get("timeout_seconds", 30)
            if type(timeout) is not int or not 1 <= timeout <= 300:
                raise InputError("verification.timeout_seconds must be an integer between 1 and 300")
            verification.append(Verification(
                stable_id(v["id"], "verification.id"),
                choice(v["kind"], {"contract", "integration", "workflow", "architecture"}, "verification.kind"),
                strings(v["command"], "verification.command", nonempty=True),
                relative_path(v.get("cwd", "."), "verification.cwd"), timeout,
                strings(v["components"], "verification.components", nonempty=True)))
        workflows = tuple(Workflow(
            stable_id(v["id"], "workflow.id"), strings(v["participants"], "workflow.participants", nonempty=True),
            strings(v["verification"], "workflow.verification", nonempty=True),
            stable_id(v["decision"], "workflow.decision"))
            for v in _objects(data, "workflows", Workflow))
        model = Model(stable_id(data["system_id"], "system_id"), string(data["name"], "name"),
                      domains, components, decisions, tuple(relationships), interfaces,
                      tuple(policies), tuple(verification), workflows, enforcement)
    except KeyError as exc:
        raise InputError(f"Missing model field: {exc.args[0]}") from exc
    _validate(model)
    # Lists are sets of named entities, sorted for deterministic compilation.
    values = {f.name: getattr(model, f.name) for f in fields(Model)}
    for name, value in values.items():
        if isinstance(value, tuple):
            values[name] = tuple(sorted(value, key=lambda v: v.id))
    return Model(**values)


def _validate(model: Model) -> None:
    spaces: dict[str, dict] = {}
    for name in ("domains", "components", "decisions", "relationships", "interfaces", "policies", "verification", "workflows"):
        values = getattr(model, name)
        index = {v.id: v for v in values}
        if len(index) != len(values):
            raise InputError(f"Duplicate identifier in {name}")
        spaces[name] = index

    def refs(values: tuple[str, ...], space: str, label: str) -> None:
        missing = set(values) - spaces[space].keys()
        if missing:
            raise InputError(f"{label} references unknown {space}: {sorted(missing)}")

    def authority(value: str, label: str) -> None:
        refs((value,), "decisions", label)
        if spaces["decisions"][value].status not in ACTIVE_DECISIONS:
            raise InputError(f"{label} requires an accepted or deprecated decision: {value}")

    for c in model.components:
        refs((c.domain,), "domains", c.id)
    for d in model.decisions:
        refs(d.components, "components", d.id)
        refs(d.supersedes, "decisions", d.id)
        for old in d.supersedes:
            if spaces["decisions"][old].status != "superseded":
                raise InputError(f"{old} must have status superseded when replaced by {d.id}")
    def visit(ident: str, ancestors: frozenset[str]) -> None:
        if ident in ancestors:
            raise InputError(f"Decision supersession cycle at {ident}")
        for old in spaces["decisions"][ident].supersedes:
            visit(old, ancestors | {ident})
    for d in model.decisions:
        visit(d.id, frozenset())
        if d.status == "superseded":
            successors = [other for other in model.decisions if d.id in other.supersedes]
            if len(successors) != 1 or successors[0].status not in ACTIVE_DECISIONS | {"superseded"}:
                raise InputError(f"Superseded decision {d.id} needs exactly one active or superseded successor")
    for r in model.relationships:
        refs((r.source, r.target), "components", r.id)
        authority(r.decision, r.id)
        if r.source == r.target:
            raise InputError(f"{r.id} must connect two different components")
    keys = [(r.source, r.target, r.kind) for r in model.relationships]
    if len(keys) != len(set(keys)):
        raise InputError("Duplicate declared relationship (source, target, kind)")
    for i in model.interfaces:
        refs((i.provider, *i.consumers), "components", i.id)
        refs(i.verification, "verification", i.id)
        authority(i.decision, i.id)
    for v in model.verification:
        refs(v.components, "components", v.id)
    for w in model.workflows:
        refs(w.participants, "components", w.id)
        refs(w.verification, "verification", w.id)
        authority(w.decision, w.id)
    for p in model.policies:
        authority(p.decision, p.id)
        if p.kind == "forbidden_dependency":
            refs((p.source, p.target), "components", p.id)
            if any(r.source == p.source and r.target == p.target and r.kind in p.kinds
                   for r in model.relationships):
                raise InputError(f"{p.id} contradicts a declared relationship")
        else:
            refs(p.components, "components", p.id)
            refs(p.checks, "verification", p.id)


SECTIONS = ("components", "interfaces", "relationships", "policies", "verification", "workflows")
SYSTEM_FIELDS = {"schema_version", "system_id", "name", "domains", "enforcement"}
AUTHORING_SUFFIXES = {".yaml", ".yml", ".json"}


def authoring_files(directory: Path) -> list[Path]:
    """Return candidate authoring files without interpreting their contents."""
    if not directory.is_dir():
        return []
    # Context bindings are optional advisory overrides, not governed authoring inputs.
    return [path for path in sorted(directory.iterdir()) if path.suffix in AUTHORING_SUFFIXES
            and path.name != "context.yaml"]


def has_authoring_model(directory: Path) -> bool:
    """Whether the directory contains a model or system entry point."""
    return any(path.stem in {"model", "system"} for path in authoring_files(directory))


def _authoring_version(content: dict) -> None:
    if content["schema_version"] != "archctl.authoring.v2":
        raise InputError("Expected archctl.authoring.v2; run archctl model migrate for legacy intent")
    choice(content.get("enforcement", "strict"), {"strict", "selective"}, "system.enforcement")


def _expand_targets(policies: Any) -> list:
    """Authoring shorthand: one forbidden_dependency per listed target, id <id>-<target>."""
    expanded = []
    for index, policy in enumerate(items(policies, "policies")):
        if not isinstance(policy, dict) or "targets" not in policy:
            expanded.append(policy)
            continue
        label = f"policies[{index}]"
        if policy.get("kind") != "forbidden_dependency" or "target" in policy:
            raise InputError(f"{label}: targets requires kind forbidden_dependency and no target")
        base = {k: v for k, v in policy.items() if k != "targets"}
        for target in strings(policy["targets"], f"{label}.targets", nonempty=True):
            expanded.append({**base, "id": f"{stable_id(policy.get('id'), 'policy.id')}-{target}", "target": target})
    return expanded


def compile_model(root: Path, model_dir: str = "architecture") -> Snapshot:
    root = root.resolve()
    directory = contained(root, model_dir)
    if not directory.is_dir():
        raise InputError(f"Architecture directory does not exist: {directory}")
    data: dict[str, Any] = {}
    sources: dict[str, str] = {}
    files = authoring_files(directory)
    if any(path.stem == "model" for path in files) and len(files) > 1:
        raise InputError("A model file cannot be combined with other authoring files")
    seen: set[str] = set()
    legacy_split = False
    for path in files:
        if path.stem not in {"model", "system", *SECTIONS} or path.stem in seen:
            raise InputError(f"Unknown or duplicate authoring file: {path.name}")
        seen.add(path.stem)
        rel = path.relative_to(root).as_posix()
        path = contained(root, rel)
        content = load_document(path)
        sources[rel] = file_digest(path)
        if path.stem in {"model", "system"}:
            obj(content, path.stem, SYSTEM_FIELDS | (set(SECTIONS) if path.stem == "model" else set()),
                {"schema_version", "system_id", "name", "domains"})
            if content.get("schema_version") == "archctl.authoring.v1":
                legacy_split = path.stem == "system"
                from archctl.core.migration import migrate_document
                content = migrate_document(content)
            _authoring_version(content)
            data.update({k: v for k, v in content.items() if k != "schema_version"})
        else:
            obj(content, path.stem, {path.stem}, {path.stem})
            data[path.stem] = content[path.stem]
    if not seen & {"model", "system"}:
        raise InputError("Missing architecture/model.yaml or system.yaml (or .json/.yml)")
    if legacy_split:
        from archctl.core.migration import migrate_document
        legacy = {"schema_version": "archctl.authoring.v1", **data}
        legacy.pop("enforcement", None)
        data = migrate_document(legacy)
        data.pop("schema_version")
    if "policies" in data:
        data["policies"] = _expand_targets(data["policies"])
    data["decisions"] = []
    decisions_dir = contained(root, f"{model_dir}/decisions")
    for path in sorted(decisions_dir.glob("*.md")):
        rel = path.relative_to(root).as_posix()
        path = contained(root, rel)
        try:
            front, body = parse_decision(path.read_text(encoding="utf-8"), rel)
        except (OSError, UnicodeError) as exc:
            raise InputError(f"Invalid ADR {rel}: {exc}") from exc
        obj(front, rel, {"id", "title", "status", "components", "supersedes"},
            {"id", "title", "status", "components"})
        data["decisions"].append({**front, "path": rel, "body": body})
        sources[rel] = file_digest(path)
    model = parse_model(data)
    content = {"model": model.to_dict(), "sources": dict(sorted(sources.items()))}
    return Snapshot(digest(content), model, tuple(sorted(sources.items())))


def parse_decision(text: str, label: str) -> tuple[dict, str]:
    """Read one ADR's front matter and body; the caller decides whether malformed text is fatal."""
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) != 3 or parts[0].strip():
        raise InputError(f"ADR requires YAML front matter: {label}")
    try:
        front = yaml.load(parts[1], Loader=UniqueLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        raise InputError(f"Invalid ADR {label}: {exc}") from exc
    if not isinstance(front, dict):
        raise InputError(f"ADR front matter must be a mapping: {label}")
    return front, parts[2].strip()


def read_snapshot(path: Path) -> Snapshot:
    data = load_document(path)
    obj(data, "snapshot", {"schema_version", "revision", "model", "sources"},
        {"schema_version", "revision", "model", "sources"})
    if data["schema_version"] != "archctl.snapshot.v2":
        raise InputError("Expected archctl.snapshot.v2; recompile migrated authoring intent")
    model = parse_model(data["model"])
    if not isinstance(data["sources"], dict):
        raise InputError("snapshot.sources must be a path-to-SHA256 object")
    for key, value in data["sources"].items():
        relative_path(key, "snapshot.sources")
        if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
            raise InputError(f"Invalid source digest: {key}")
    expected = digest({"model": model.to_dict(), "sources": data["sources"]})
    if data["revision"] != expected:
        raise InputError("Snapshot integrity check failed")
    return Snapshot(expected, model, tuple(sorted(data["sources"].items())))
