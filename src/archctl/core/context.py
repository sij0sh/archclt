"""Optional architecture bindings and bounded source inventories, not an analyzer."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from archctl.core.compiler import parse_decision
from archctl.core.contracts import version
from archctl.core.io import (InputError, contained, digest, excluded, load_document, obj,
                             relative_path, stable_id, string, strings)
from archctl.core.models import Snapshot, owners

CODE = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java", ".kt", ".c", ".h",
        ".cpp", ".cs", ".rb", ".sql", ".swift", ".scala"}


@dataclass(frozen=True)
class Binding:
    id: str
    paths: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    purpose: str = ""
    origin: str = "provisional"

    def to_dict(self) -> dict:
        return {"id": self.id, "paths": list(self.paths), "aliases": list(self.aliases),
                "purpose": self.purpose, "origin": self.origin}


def inventory(root: Path, limit: int = 4000) -> tuple[list[str], bool]:
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs
                         if not excluded((Path(directory) / d).relative_to(root).as_posix())
                         and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            if (excluded(rel) or path.is_symlink()
                    or path.suffix.lower() not in CODE | {".md", ".yaml", ".yml", ".toml", ".json"}):
                continue
            files.append(rel)
            if len(files) == limit:
                return sorted(files), True
    return sorted(files), False


def load_bindings(root: Path, snapshot: Snapshot | None, files: list[str],
                  planned: list[str]) -> tuple[list[Binding], list[str]]:
    bindings = {c.id: Binding(c.id, c.paths, purpose=c.name, origin="declared")
                for c in snapshot.model.components} if snapshot else {}
    config = contained(root, "architecture/context.yaml")
    if config.is_file():
        data = obj(load_document(config), "context config", {"schema_version", "components"},
                   {"schema_version", "components"})
        if data["schema_version"] != version("context-config") or not isinstance(data["components"], list):
            raise InputError(f"Expected {version('context-config')} and a components list")
        seen = set()
        for item in data["components"]:
            v = obj(item, "context component", {"id", "paths", "aliases", "purpose"}, {"id", "paths"})
            ident = stable_id(v["id"], "component.id")
            if ident in seen:
                raise InputError(f"Duplicate context component: {ident}")
            seen.add(ident)
            paths = tuple(relative_path(p, "component.paths", glob=True)
                          for p in strings(v["paths"], "component.paths", nonempty=True))
            aliases = tuple(stable_id(a, "component.alias") for a in strings(v.get("aliases", []), "aliases"))
            purpose = string(v["purpose"], "purpose") if "purpose" in v else ""
            bindings[ident] = Binding(ident, paths, aliases, purpose, "override")
    identities = list(bindings)
    for binding in bindings.values():
        identities.extend(binding.aliases)
    if len(identities) != len(set(identities)):
        raise InputError("Component IDs and aliases must be unambiguous")
    gaps = []
    for path in sorted(set(files) | set(planned)):
        bound = owners(path, bindings.values())
        if len(bound) > 1:
            gaps.append(f"Ambiguous component binding: {path}")
        if bound or (Path(path).suffix.lower() not in CODE and path not in planned):
            continue
        parts = Path(path).parts
        width = 2 if len(parts) > 2 and parts[0] in {"src", "app", "lib", "packages"} else 1
        prefix = "/".join(parts[:width]) if len(parts) > width else path
        stem = re.sub(r"[^A-Za-z0-9_.-]", "-", prefix)[:90]
        ident = f"path.{stem}.{digest(prefix)[:8]}"
        # Bind generated candidates to actual/planned files; never overlap an explicit subtree.
        previous = bindings.get(ident)
        patterns = (*previous.paths, path) if previous else (path,)
        bindings[ident] = Binding(ident, patterns)
    return sorted(bindings.values(), key=lambda b: b.id), sorted(set(gaps))


def terms(text: str) -> set[str]:
    # Retrieval is lexical and inspectable; semantic interpretation belongs to the agent.
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    stop = {"the", "and", "for", "with", "from", "that", "this", "into", "use", "add", "change"}
    return {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", text) if t.lower() not in stop}


def decision_notes(root: Path, directory: str) -> tuple[list[dict], list[str]]:
    """Read existing rationale even when no complete governed model exists."""
    result, gaps = [], []
    for path in sorted(contained(root, f"{directory}/decisions").glob("*.md")):
        rel = path.relative_to(root).as_posix()
        path = contained(root, rel)
        try:
            if path.stat().st_size > 65536:
                gaps.append(f"Decision record exceeds 65536 bytes and was skipped: {rel}")
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            gaps.append(f"Decision record could not be read and was skipped: {rel}: {exc}")
            continue
        try:
            front, body = parse_decision(text, rel)
        except InputError:
            front, body = {}, text
        components = front.get("components", [])
        if not isinstance(components, list) or any(not isinstance(c, str) for c in components):
            components = []
        supersedes = front.get("supersedes", [])
        if not isinstance(supersedes, list) or any(not isinstance(c, str) for c in supersedes):
            supersedes = []
        result.append({"id": str(front.get("id", path.stem)), "status": str(front.get("status", "unclassified")),
            "title": str(front.get("title", path.stem)), "path": rel, "body": body,
            "components": components, "supersedes": supersedes})
    return result, gaps
