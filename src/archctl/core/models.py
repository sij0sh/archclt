"""Immutable in-process representations of architectural intent and evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from archctl.core.io import matches

KINDS = {"imports", "calls", "reads", "writes", "publishes", "consumes"}
ACTIVE_DECISIONS = {"accepted", "deprecated"}


def owners(path: str, scopes) -> list[str]:
    """Declared component or binding IDs whose paths contain this path."""
    return [scope.id for scope in scopes if any(matches(path, pattern) for pattern in scope.paths)]


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    owners: tuple[str, ...]


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    domain: str
    kind: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    id: str
    status: str
    title: str
    components: tuple[str, ...]
    supersedes: tuple[str, ...]
    path: str
    body: str


@dataclass(frozen=True)
class Relationship:
    id: str
    source: str
    target: str
    kind: str
    decision: str
    required: bool


@dataclass(frozen=True)
class Interface:
    id: str
    provider: str
    consumers: tuple[str, ...]
    verification: tuple[str, ...]
    decision: str


@dataclass(frozen=True)
class Policy:
    id: str
    kind: str
    decision: str
    severity: str
    source: str = ""
    target: str = ""
    kinds: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    obligation: str = "required"


@dataclass(frozen=True)
class Verification:
    id: str
    kind: str
    command: tuple[str, ...]
    cwd: str
    timeout_seconds: int
    components: tuple[str, ...]


@dataclass(frozen=True)
class Workflow:
    id: str
    participants: tuple[str, ...]
    verification: tuple[str, ...]
    decision: str


@dataclass(frozen=True)
class Model:
    system_id: str
    name: str
    domains: tuple[Domain, ...]
    components: tuple[Component, ...]
    decisions: tuple[Decision, ...]
    relationships: tuple[Relationship, ...]
    interfaces: tuple[Interface, ...]
    policies: tuple[Policy, ...]
    verification: tuple[Verification, ...]
    workflows: tuple[Workflow, ...]
    enforcement: str = "strict"

    def to_dict(self) -> dict[str, Any]:
        # Canonical JSON conversion turns immutable tuples into exchange lists.
        import json
        data = json.loads(json.dumps(asdict(self)))
        return data


@dataclass(frozen=True)
class Snapshot:
    revision: str
    model: Model
    sources: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict:
        return {"schema_version": "archctl.snapshot.v2", "revision": self.revision,
                "model": self.model.to_dict(), "sources": dict(self.sources)}


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    location: str
    description: str


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    kind: str
    origin: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Coverage:
    analysis: str
    status: str
    components: tuple[str, ...]
    relationship_kinds: tuple[str, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class Observations:
    producer: str
    producer_version: str
    source_revision: str
    files: tuple[tuple[str, str], ...]
    coverage: Coverage
    evidence: tuple[Evidence, ...]
    edges: tuple[Edge, ...]

    @property
    def source_digest(self) -> str:
        from archctl.core.io import digest
        return digest({"revision": self.source_revision, "files": dict(self.files)})

    def covers(self, source: str, target: str, kinds: tuple[str, ...]) -> bool:
        c = self.coverage
        return (c.analysis == "static" and c.status == "complete" and not c.gaps
                and {source, target} <= set(c.components)
                and set(kinds) <= set(c.relationship_kinds))

    def to_dict(self) -> dict:
        import json
        return json.loads(json.dumps({"schema_version": "archctl.evidence.v2",
                "producer": {"name": self.producer, "version": self.producer_version},
                "source": {"revision": self.source_revision, "files": dict(self.files)},
                "coverage": asdict(self.coverage), "evidence": [asdict(e) for e in self.evidence],
                "edges": [asdict(e) for e in self.edges]}))


@dataclass(frozen=True)
class Finding:
    id: str
    status: str
    message: str
    severity: str = "error"
    decision: str = ""
    evidence_refs: tuple[str, ...] = ()

    obligation: str = "required"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data
