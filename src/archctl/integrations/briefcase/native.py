"""Map a retained Briefcase Python source view into normalized archctl evidence.

The mapper uses Briefcase's public JSON operations. It never reads Briefcase's
database directly and never invents an import edge: every emitted edge cites a
retained Briefcase assertion. Unresolved imports whose literal target could be a
declared component keep coverage partial. Matched component files outside regular
Python source also keep coverage partial. Unresolved external imports and files
outside declared components are outside the declared relationship scope.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterator

from archctl.core.io import (InputError, contained, file_digest, matches,
                             source_files)
from archctl.core.models import Snapshot

SCHEMA = "archctl.evidence.v2"
PRODUCER = "briefcase-native-exporter"
SUPPORT = {"profile": "briefcase-0.1.0-python-imports", "languages": ["python"], "predicates": ["imports"],
           "limitation": "Only Python import edges are assessed. Other languages, dynamic imports and runtime structure are not."}
MAX_PAGE_BYTES = 1024 * 1024


def _run(binary: str, root: Path, arguments: list[str], *, timeout: int = 300) -> str:
    try:
        result = subprocess.run([binary, *arguments], cwd=root, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise InputError(f"Briefcase executable not found: {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise InputError(f"Briefcase command timed out after {timeout}s: {arguments[:2]}") from exc
    if result.returncode:
        message = (result.stderr or result.stdout).strip()[:2000]
        raise InputError(f"Briefcase command failed ({result.returncode}): {' '.join(arguments[:2])}: {message}")
    return result.stdout


def _json(binary: str, root: Path, arguments: list[str], *, timeout: int = 300) -> dict:
    output = _run(binary, root, arguments, timeout=timeout)
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        raise InputError(f"Briefcase returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError("Briefcase returned a non-object JSON document")
    return value


def _call(binary: str, root: Path, database: Path, operation: str,
          arguments: dict, *, timeout: int = 300) -> dict:
    return _json(binary, root, ["call", operation, "--args", json.dumps(arguments),
                                "--db", str(database), "--json"], timeout=timeout)


def _items(document: dict) -> list[dict]:
    items = document.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    details = document.get("details")
    if isinstance(details, dict):
        return [dict(item, id=item.get("id") or key) for key, item in details.items()
                if isinstance(item, dict)]
    return []


def _documents(binary: str, root: Path, database: Path, operation: str,
               arguments: dict) -> Iterator[dict]:
    document = _call(binary, root, database, operation, arguments)
    yield document
    while document.get("continue_with"):
        request = dict(document["continue_with"].get("arguments", {}))
        request["max_bytes"] = MAX_PAGE_BYTES
        document = _call(binary, root, database, "page", request)
        yield document


def _paged(binary: str, root: Path, database: Path, operation: str,
           arguments: dict) -> Iterator[dict]:
    for document in _documents(binary, root, database, operation, arguments):
        yield from _items(document)


def _version(binary: str, root: Path) -> str:
    output = _run(binary, root, ["--version"]).strip()
    return output.split()[-1] if output else "unknown"


def _owners(snapshot: Snapshot, relative: str) -> list[str]:
    return [component.id for component in snapshot.model.components
            if any(matches(relative, pattern) for pattern in component.paths)]


def _supported(relative: str) -> bool:
    """The native mapper analyzes regular Python source files only."""
    return relative.endswith(".py")


def _unsupported_gaps(files: list[str]) -> list[str]:
    """Disclose every matched component file outside the supported Python scope."""
    return [f"Component file outside supported Python import scope: {relative}"
            for relative in files if not _supported(relative)]


def _import_targets(text: str) -> list[str] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                return None
            targets.append(node.module or "")
        elif isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
    return targets


def _module_index(files: list[str], roots: tuple[str, ...]) -> set[str]:
    roots = roots or (".",)
    modules: set[str] = set()
    for relative in files:
        if not _supported(relative):
            continue
        for root in roots:
            prefix = "" if root in {"", "."} else root.rstrip("/") + "/"
            if prefix and not relative.startswith(prefix):
                continue
            path = relative[len(prefix):] if prefix else relative
            parts = path[:-3].split("/")
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            for index in range(1, len(parts) + 1):
                modules.add(".".join(parts[:index]))
    return modules


def _internal_target(module: str, modules: set[str]) -> bool:
    parts = module.split(".")
    return any(".".join(parts[:index]) in modules for index in range(1, len(parts) + 1))


def _retained_digests(binary: str, root: Path, database: Path, view: str,
                      files: list[str], gaps: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    chunk_size = 32
    for offset in range(0, len(files), chunk_size):
        chunk = files[offset:offset + chunk_size]
        paths = [str(contained(root, relative)) for relative in chunk]
        try:
            result = _json(binary, root, ["inspect-external", *paths, "--db", str(database),
                                          "--view", view, "--json"])
        except InputError as exc:
            gaps.append(f"Briefcase could not inspect retained bytes for {len(chunk)} file(s): {exc}")
            continue
        for item in result.get("items", []):
            if not isinstance(item, dict):
                continue
            identity = item.get("identity")
            digest = item.get("digest")
            matching = item.get("matching_source_paths") or []
            relative = None
            if isinstance(item.get("path"), str):
                try:
                    relative = Path(item["path"]).resolve().relative_to(root.resolve()).as_posix()
                except ValueError:
                    relative = None
            if relative is None:
                candidates = [path for path in matching if path in chunk]
                relative = candidates[0] if len(candidates) == 1 else None
            if relative is None:
                continue
            if identity not in {"exact_retained_bytes", "ambiguous_retained_matches"}:
                gaps.append(f"Briefcase did not retain current bytes for {relative}: {identity}")
                continue
            if relative not in matching:
                gaps.append(f"Briefcase did not retain path {relative}: {identity}")
                continue
            if not isinstance(digest, str) or not re.fullmatch("sha256:[0-9a-f]{64}", digest):
                gaps.append(f"Briefcase returned an invalid digest for {relative}")
                continue
            if digest[7:] != file_digest(contained(root, relative)):
                gaps.append(f"Briefcase retained bytes differ from the current file: {relative}")
                continue
            digests[relative] = digest[7:]
        for relative in chunk:
            if relative not in digests:
                gaps.append(f"Briefcase did not retain exact current bytes for {relative}")
    return digests


def _neighbors(binary: str, root: Path, database: Path, view: str, relative: str,
               gaps: list[str]) -> list[dict]:
    try:
        return list(_paged(binary, root, database, "neighbors", {
            "target": relative, "direction": "out", "predicate": "IMPORTS",
            "limit": 1000, "max_bytes": MAX_PAGE_BYTES, "view": view}))
    except InputError as exc:
        gaps.append(f"Briefcase neighbors query failed for {relative}: {exc}")
        return []


def _unresolved_imports(binary: str, root: Path, database: Path, view: str,
                        files: list[str], modules: set[str], gaps: list[str]) -> list[str]:
    problems: list[str] = []
    for relative in files:
        if not _supported(relative):
            continue
        try:
            documents = list(_documents(binary, root, database, "unresolved", {
                "component": relative, "limit": 1000,
                "max_bytes": MAX_PAGE_BYTES, "view": view}))
        except InputError as exc:
            gaps.append(f"Briefcase unresolved query failed for {relative}: {exc}")
            continue
        for document in documents:
            report_id = document.get("report_id")
            handles = {result.get("id"): result.get("explanation_handle")
                       for result in (document.get("response") or {}).get("results", [])
                       if isinstance(result, dict)}
            for row in _items(document):
                if row.get("predicate") != "IMPORTS":
                    continue
                handle = handles.get(row.get("id"))
                if not isinstance(handle, str) or not isinstance(report_id, str):
                    gaps.append(f"Cannot classify unresolved import in {relative}: no explanation handle")
                    continue
                try:
                    explanation = _call(binary, root, database, "explain", {
                        "ref": handle, "report_id": report_id, "source_offset": 0,
                        "limit": 100, "max_bytes": MAX_PAGE_BYTES})
                except InputError as exc:
                    gaps.append(f"Cannot classify unresolved import in {relative}: {exc}")
                    continue
                sources = [support.get("unresolved_source", {}).get("text")
                           for support in explanation.get("support", [])
                           if isinstance(support, dict)]
                texts = [text for text in sources if isinstance(text, str)]
                if not texts:
                    gaps.append(f"Cannot classify unresolved import in {relative}: Briefcase returned no source span")
                    continue
                targets: list[str] = []
                parsed_all = True
                for text in texts:
                    parsed = _import_targets(text)
                    if parsed is None:
                        parsed_all = False
                        break
                    targets.extend(parsed)
                if not parsed_all:
                    gaps.append(f"Cannot classify unresolved import in {relative}: unparsed or relative source span")
                    continue
                internal = [target for target in targets if _internal_target(target, modules)]
                if internal:
                    problems.append(f"Unresolved internal import in {relative}: {', '.join(sorted(set(internal)))}")
    return problems


def export_evidence(root: Path, snapshot: Snapshot, *, binary: str = "briefcase",
                    database: Path | None = None,
                    source_roots: tuple[str, ...] = ()) -> dict[str, Any]:
    """Run Briefcase and return a validated ``archctl.evidence.v2`` bundle."""
    root = root.resolve()
    database = (database or (root / ".briefcase/briefcase.db")).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    version = _version(binary, root)
    scan_arguments = ["scan", "--language", "python", "--no-calls", "--db", str(database), "--json"]
    for source_root in source_roots:
        scan_arguments.extend(["--python-source-root", source_root])
    scan = _json(binary, root, scan_arguments)
    gaps: list[str] = []
    if scan.get("status") != "published":
        gaps.append(f"Briefcase scan did not publish a view: {scan.get('status')}")
    view_id = scan.get("view_id") or "unknown"
    context = scan.get("context") or {}
    snapshot_id = context.get("snapshot_id") or "unknown"
    diagnostics = scan.get("diagnostics") or {}
    capture = diagnostics.get("capture") or {}
    inventory = capture.get("inventory") or {}
    if diagnostics.get("files_attempted") != diagnostics.get("files_completed"):
        gaps.append("Briefcase analysis did not complete every attempted source file")

    component_paths = tuple(pattern for component in snapshot.model.components
                            for pattern in component.paths)
    unretained = sorted(str(path) for path in inventory.get("unretained_tracked_paths") or [])
    component_unretained = [path for path in unretained
                            if any(matches(path, pattern) for pattern in component_paths)]
    if component_unretained:
        gaps.append("Briefcase capture left tracked component paths unretained: " +
                    ", ".join(component_unretained))
    if not inventory.get("tracked_text_complete", False) and not unretained:
        gaps.append("Briefcase capture did not retain complete tracked text")
    files = sorted(source_files(root, component_paths))
    gaps.extend(_unsupported_gaps(files))
    owner: dict[str, str] = {}
    for relative in files:
        owners = _owners(snapshot, relative)
        if len(owners) == 1:
            owner[relative] = owners[0]
        else:
            gaps.append(f"File has {len(owners)} component bindings: {relative}")
    for component in snapshot.model.components:
        if not any(owner.get(relative) == component.id for relative in files):
            gaps.append(f"Component {component.id} has no source files")
        for pattern in component.paths:
            if not any(matches(relative, pattern) for relative in files):
                gaps.append(f"Component path matched no files: {component.id}: {pattern}")

    retained = _retained_digests(binary, root, database, view_id, files, gaps)
    pins = {relative: retained.get(relative, file_digest(contained(root, relative)))
            for relative in files}

    evidence: dict[str, dict] = {}
    grouped: dict[tuple[str, str], set[str]] = {}
    for relative in files:
        if not _supported(relative):
            continue
        for item in _neighbors(binary, root, database, view_id, relative, gaps):
            if item.get("predicate") != "IMPORTS" or item.get("basis") != "retained_assertion":
                continue
            source_file = item.get("from")
            target_file = item.get("to")
            target_files = item.get("to_files") or []
            if not isinstance(source_file, str) or source_file not in owner:
                continue
            if isinstance(target_file, str) and target_file in owner:
                target = target_file
            else:
                candidates = [path for path in target_files if path in owner]
                if len(candidates) != 1:
                    continue
                target = candidates[0]
            source_component, target_component = owner[source_file], owner[target]
            identifier = str(item.get("id") or f"briefcase-import-{len(evidence)}")
            evidence[identifier] = {
                "id": identifier,
                "kind": "static",
                "location": f"briefcase:{view_id}/{identifier}",
                "description": f"Briefcase retained IMPORTS edge {source_file} -> {target}",
            }
            grouped.setdefault((source_component, target_component), set()).add(identifier)

    provider = diagnostics.get("provider") or {}
    roots = tuple(str(root) for root in provider.get("source_roots") or [])
    gaps.extend(_unresolved_imports(binary, root, database, view_id, files,
                                    _module_index(files, roots), gaps))
    edges = [{
        "id": f"briefcase-import-{index}",
        "source": source_component,
        "target": target_component,
        "kind": "imports",
        "origin": "static",
        "evidence_refs": sorted(refs),
    } for index, ((source_component, target_component), refs) in enumerate(sorted(grouped.items()))]

    unique_gaps = sorted(set(gaps))
    coverage = {
        "analysis": "static",
        "status": "partial" if unique_gaps else "complete",
        "components": sorted(component.id for component in snapshot.model.components),
        "relationship_kinds": ["imports"],
        "gaps": unique_gaps,
    }
    bundle = {
        "schema_version": SCHEMA,
        "producer": {"name": PRODUCER, "version": f"1+briefcase-{version}"},
        "source": {"revision": f"briefcase:{view_id}:{snapshot_id}", "files": pins},
        "coverage": coverage,
        "evidence": [evidence[key] for key in sorted(evidence)],
        "edges": edges,
    }
    # Fail here, not later in Guard, if the mapped bundle violates the contract.
    from archctl.integrations.briefcase.adapter import parse_evidence
    parse_evidence(bundle, snapshot)
    return bundle
