"""Strict input parsing, stable hashing, and repository path containment."""

from __future__ import annotations

import fnmatch
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

import yaml


class InputError(ValueError):
    """An authoring or exchange contract is invalid."""


# One exclusion policy for repository source inventory and evidence pins.
SKIP = {".git", ".archctl", ".briefcase", "__pycache__", ".venv", "venv", "node_modules",
        "target", "dist", "build", ".pytest_cache"}
MEMORY_ROOT = "architecture/memory"


def excluded(relative: str) -> bool:
    """Return whether a repository-relative path is outside source evidence."""
    if relative == MEMORY_ROOT or relative.startswith(MEMORY_ROOT + "/"):
        return True
    return any(part in SKIP or part.startswith(".") or part.endswith(".egg-info")
               for part in PurePosixPath(relative).parts)


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader: UniqueLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise InputError(f"YAML keys must be unique strings: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise InputError(f"Cannot serialize contract: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_document(path: Path) -> Any:
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise InputError(f"Input exceeds 16 MiB: {path}")
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            def pairs(items: list[tuple[str, Any]]) -> dict:
                result = {}
                for key, val in items:
                    if key in result:
                        raise InputError(f"Duplicate JSON key: {key}")
                    result[key] = val
                return result
            return json.loads(text, object_pairs_hook=pairs,
                              parse_constant=lambda x: (_ for _ in ()).throw(InputError(f"Invalid number: {x}")))
        return yaml.load(text, Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    """Replace a generated artifact atomically, never partially."""
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    write_text(path, payload)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def relative_path(value: Any, label: str, *, glob: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise InputError(f"{label} must be a nonempty repository-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("-"):
        raise InputError(f"{label} escapes the repository: {value!r}")
    if not glob and any(char in value for char in "*?["):
        raise InputError(f"{label} must be a concrete path")
    if str(path) != value and value != ".":
        raise InputError(f"{label} is not normalized: {value!r}")
    return value


def contained(root: Path, value: str) -> Path:
    relative_path(value, "path")
    result = (root / value).resolve()
    if not result.is_relative_to(root.resolve()):
        raise InputError(f"Symlink escapes repository: {value}")
    return result


def matches(path: str, pattern: str) -> bool:
    # POSIX globs: * is within a segment; ** can cross segments.
    parts, patterns = path.split("/"), pattern.split("/")
    @lru_cache(maxsize=None)
    def match_at(pi: int, gi: int) -> bool:
        if gi == len(patterns):
            return pi == len(parts)
        if patterns[gi] == "**":
            return match_at(pi, gi + 1) or (pi < len(parts) and match_at(pi + 1, gi))
        return pi < len(parts) and fnmatch.fnmatchcase(parts[pi], patterns[gi]) and match_at(pi + 1, gi + 1)
    return match_at(0, 0)


def source_files(root: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in patterns:
        expanded = pattern + "/*" if pattern.endswith("/**") else pattern
        for path in root.glob(expanded):
            rel = path.relative_to(root).as_posix()
            if excluded(rel):
                continue
            target = contained(root, rel)
            if target.is_file():
                files[rel] = file_digest(target)
    return dict(sorted(files.items()))


def obj(value: Any, label: str, allowed: set[str], required: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise InputError(f"{label} must be an object")
    extra, missing = set(value) - allowed, required - set(value)
    if extra or missing:
        raise InputError(f"{label}: unknown keys {sorted(extra)}; missing keys {sorted(missing)}")
    return value


def stable_id(value: Any, label: str) -> str:
    value = string(value, label)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", value):
        raise InputError(f"{label} is not a stable identifier: {value!r}")
    return value


def string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label} must be a nonempty string")
    return value


def strings(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InputError(f"{label} must be a list")
    result = tuple(string(v, label) for v in value)
    if len(result) != len(set(result)) or (nonempty and not result):
        raise InputError(f"{label} must contain unique{' nonempty' if nonempty else ''} values")
    return result


def items(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise InputError(f"{label} must be a list")
    return value


def choice(value: Any, options: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in options:
        raise InputError(f"{label} must be one of {sorted(options)}")
    return value
