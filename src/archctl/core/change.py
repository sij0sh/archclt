"""A reviewed task description, separate from enduring architecture authority."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archctl.core.contracts import version
from archctl.core.io import (InputError, digest, items, load_document, obj, relative_path,
                             stable_id, string, strings)
from archctl.core.models import ACTIVE_DECISIONS, Snapshot


@dataclass(frozen=True)
class Acceptance:
    id: str
    requirement: str
    checks: tuple[str, ...]


@dataclass(frozen=True)
class Change:
    id: str
    objective: str
    components: tuple[str, ...]
    excluded_components: tuple[str, ...]
    paths: tuple[str, ...]
    acceptance: tuple[Acceptance, ...]
    decisions: tuple[str, ...]
    policies: tuple[str, ...]
    open_questions: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"schema_version": version("change"), "id": self.id, "objective": self.objective,
                "scope": {"components": list(self.components),
                          "excluded_components": list(self.excluded_components), "paths": list(self.paths)},
                "acceptance": [{"id": a.id, "requirement": a.requirement, "checks": list(a.checks)} for a in self.acceptance],
                "constraints": {"decisions": list(self.decisions), "policies": list(self.policies)},
                "open_questions": list(self.open_questions)}

    @property
    def allowed_components(self) -> tuple[str, ...]:
        excluded = set(self.excluded_components)
        return tuple(component for component in self.components if component not in excluded)

    @property
    def revision(self) -> str:
        return digest(self.to_dict())


def parse_change(data: object, snapshot: Snapshot) -> Change:
    keys = {"schema_version", "id", "objective", "scope", "acceptance", "constraints", "open_questions"}
    obj(data, "change", keys, keys)
    if data["schema_version"] != version("change"):
        raise InputError(f"Expected {version('change')}")
    scope = obj(data["scope"], "change.scope", {"components", "excluded_components", "paths"}, {"components"})
    constraints = obj(data["constraints"], "change.constraints", {"decisions", "policies"}, {"decisions", "policies"})
    components = strings(scope["components"], "scope.components", nonempty=True)
    excluded = strings(scope.get("excluded_components", []), "scope.excluded_components")
    if not set(components) - set(excluded):
        raise InputError("Change scope must include at least one component after exclusions")
    known = {c.id for c in snapshot.model.components}
    if (set(components) | set(excluded)) - known:
        raise InputError("Change scope references unknown components")
    acceptance = []
    for raw in items(data["acceptance"], "acceptance"):
        obj(raw, "acceptance criterion", {"id", "requirement", "checks"}, {"id", "requirement", "checks"})
        acceptance.append(Acceptance(stable_id(raw["id"], "acceptance.id"),
                                     string(raw["requirement"], "acceptance.requirement"),
                                     strings(raw["checks"], "acceptance.checks")))
    if not acceptance or len({a.id for a in acceptance}) != len(acceptance):
        raise InputError("Acceptance criteria must be nonempty and have unique IDs")
    checks = {v.id for v in snapshot.model.verification}
    missing = {c for a in acceptance for c in a.checks} - checks
    if missing:
        raise InputError(f"Unknown verification references in change: {sorted(missing)}")
    decisions = strings(constraints["decisions"], "constraints.decisions")
    policies = strings(constraints["policies"], "constraints.policies")
    active = {d.id for d in snapshot.model.decisions if d.status in ACTIVE_DECISIONS}
    if set(decisions) - active or set(policies) - {p.id for p in snapshot.model.policies}:
        raise InputError("Change constraints reference unknown or inactive architecture authority")
    return Change(stable_id(data["id"], "change.id"), string(data["objective"], "change.objective"),
                  components, excluded,
                  tuple(relative_path(p, "scope.paths", glob=True) for p in strings(scope.get("paths", []), "scope.paths")),
                  tuple(acceptance), decisions, policies, strings(data["open_questions"], "open_questions"))


def read_change(path: Path, snapshot: Snapshot) -> Change:
    return parse_change(load_document(path), snapshot)
