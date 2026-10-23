"""Immutable, attributable architectural reasoning; no approval lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import re
import tempfile

from archctl.core.io import (InputError, choice, contained, digest, file_digest,
                             load_document, obj, relative_path, source_files,
                             stable_id, string, strings)

ORIGINS = {"observed", "user_stated", "agent_inferred", "agent_chosen"}


@dataclass(frozen=True)
class Memory:
    id: str
    statement: str
    rationale: str
    origin: str
    references: tuple[str, ...]
    components: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    source_files: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict:
        value = json.loads(json.dumps(asdict(self)))
        value["source_files"] = dict(self.source_files)
        value["schema_version"] = "archctl.memory.v1"
        value["revision"] = digest(value)
        return value


def parse_memory(value: object) -> Memory:
    fields = {"schema_version", "revision", *Memory.__dataclass_fields__}
    data = obj(value, "memory", fields,
               {"schema_version", "id", "statement", "rationale", "origin", "references"})
    if data["schema_version"] != "archctl.memory.v1":
        raise InputError("Expected archctl.memory.v1")
    pins = data.get("source_files", {})
    if not isinstance(pins, dict):
        raise InputError("memory.source_files must be a path-to-SHA256 object")
    for path, pin in pins.items():
        relative_path(path, "memory.source_files")
        if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin):
            raise InputError("Memory file pins must be lowercase SHA256 values")
    record = Memory(stable_id(data["id"], "memory.id"),
        string(data["statement"], "memory.statement"), string(data["rationale"], "memory.rationale"),
        choice(data["origin"], ORIGINS, "memory.origin"),
        strings(data["references"], "memory.references", nonempty=True),
        tuple(stable_id(v, "memory.components") for v in strings(data.get("components", []), "memory.components")),
        tuple(relative_path(v, "memory.paths", glob=True) for v in strings(data.get("paths", []), "memory.paths")),
        *(strings(data.get(k, []), f"memory.{k}") for k in ("topics", "assumptions", "supersedes", "contradicts")),
        tuple(sorted(pins.items())))
    if len(record.statement) > 4000 or len(record.rationale) > 12000 or len(record.references) > 64:
        raise InputError("Memory must stay compact: statement 4000, rationale 12000 characters, 64 references")
    for target in (*record.supersedes, *record.contradicts):
        stable_id(target, "memory relation")
    if record.id in {*record.supersedes, *record.contradicts}:
        raise InputError("Memory cannot supersede or contradict itself")
    if set(record.supersedes) & set(record.contradicts):
        raise InputError("Use supersedes or contradicts for a target, not both")
    if "revision" in data and data["revision"] != record.to_dict()["revision"]:
        raise InputError(f"Memory revision does not match content: {record.id}")
    return record


def read_memories(root: Path, directory: str = "architecture/memory") -> tuple[Memory, ...]:
    folder = contained(root, directory)
    records = []
    for path in sorted(folder.glob("*.json")):
        contained(root, path.relative_to(root).as_posix())
        record = parse_memory(load_document(path))
        if path.name != f"{record.id}.json":
            raise InputError(f"Memory filename must match its ID: {path.name}")
        records.append(record)
    index = {r.id: r for r in records}
    if len(index) != len(records):
        raise InputError("Duplicate memory ID")
    for record in records:
        missing = {*record.supersedes, *record.contradicts} - index.keys()
        if missing:
            raise InputError(f"Memory {record.id} has missing references: {sorted(missing)}")
    def visit(ident: str, ancestors: frozenset[str]) -> None:
        if ident in ancestors:
            raise InputError("Memory supersession cycle")
        for old in index[ident].supersedes:
            visit(old, ancestors | {ident})
    for ident in index:
        visit(ident, frozenset())
    return tuple(records)


def freshness(root: Path, record: Memory) -> dict:
    changed = [path for path, pin in record.source_files
               if not contained(root, path).is_file() or file_digest(contained(root, path)) != pin]
    current = source_files(root, record.paths) if record.paths else {}
    new = sorted(current.keys() - dict(record.source_files).keys()) if record.source_files else []
    return {"status": "stale" if changed or new else "current" if record.source_files else "unverified",
            "changed_paths": sorted(changed), "new_paths": new}


def remember(root: Path, value: object, directory: str = "architecture/memory") -> Memory:
    """Append once, retaining original evidence pins and all historical records."""
    record = parse_memory(value)
    existing = {r.id: r for r in read_memories(root, directory)}
    missing = {*record.supersedes, *record.contradicts} - existing.keys()
    if missing:
        raise InputError(f"Memory relation targets do not exist: {sorted(missing)}")
    if record.id in existing:
        old = existing[record.id]
        # An identical unpinned input is an idempotent retry, not a repin.
        candidate = record.to_dict()
        if not record.source_files:
            candidate["source_files"] = dict(old.source_files)
            candidate.pop("revision")
            candidate["revision"] = digest(candidate)
        if candidate != old.to_dict():
            raise InputError(f"Memory {record.id} is immutable; use a new ID and supersedes")
        return old
    if not record.source_files:
        data = record.to_dict()
        data.pop("revision")
        data["source_files"] = source_files(root, record.paths)
        record = parse_memory(data)
    path = contained(root, f"{directory}/{record.id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".memory-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record.to_dict(), stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        try:
            os.link(temporary, path)  # Publish a complete record without replacing a concurrent write.
        except FileExistsError as exc:
            raise InputError(f"Memory already exists: {record.id}; retry to compare") from exc
    finally:
        Path(temporary).unlink(missing_ok=True)
    return record
