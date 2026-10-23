"""Prepare a disposable scoped projection; independent tools still produce evidence.

This is not a mapper, a gate, or a fix for Briefcase's full-tree analysis limit.
Only the final evidence.json is usable. Failed attempts retain diagnostics only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from archctl.core.compiler import compile_model
from archctl.core.io import (InputError, contained, file_digest, load_document,
                             matches, relative_path, source_files, write_json)
from archctl.core.models import Snapshot
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence
from archctl.integrations.briefcase.native import PRODUCER, SUPPORT


def _environment() -> dict[str, str]:
    # In particular, verification's candidate PYTHONPATH must not select the
    # exporter implementation, and a user's database override must not leak in.
    excluded = {"PYTHONPATH", "PYTHONHOME", "BRIEFCASE_DB", "GIT_DIR", "GIT_WORK_TREE",
                "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES"}
    return {**{k: v for k, v in os.environ.items() if k not in excluded}, "PYTHONSAFEPATH": "1"}


def _git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *arguments],
                                capture_output=True, text=True, env=_environment(), timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        raise InputError("Git command timed out during preparation") from exc
    if result.returncode:
        raise InputError(f"Git {arguments[0]} failed: {result.stderr.strip()[:2000]}")
    return result.stdout


def _run(argv: list[str], cwd: Path, output: Path) -> str:
    with output.open("w") as stdout, output.with_suffix(".stderr.txt").open("w") as stderr:
        try:
            result = subprocess.run(argv, cwd=cwd, env=_environment(), stdout=stdout,
                                    stderr=stderr, timeout=300, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise InputError(f"External command unavailable or timed out: {argv[0]}") from exc
    if result.returncode:
        detail = output.with_suffix(".stderr.txt").read_text()[:2000]
        raise InputError(f"External command failed ({result.returncode}): {argv[0]}: {detail}")
    return output.read_text()


def _tool(path: Path, root: Path) -> dict:
    if not path.is_absolute():
        raise InputError("External executable paths must be absolute")
    path = path.resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise InputError(f"External executable is missing or not executable: {path}")
    checkout = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                              capture_output=True, env=_environment(), timeout=60, check=False)
    if path.is_relative_to(root) or checkout.returncode == 0:
        raise InputError(f"External executable must be outside source checkouts: {path}")
    return {"path": str(path), "sha256": file_digest(path)}


def _regular(root: Path, relative: str, *, missing: bool = False) -> Path:
    path = contained(root, relative)
    current = root / relative
    while current != root:
        if current.is_symlink():
            raise InputError(f"Symlink cannot establish exact projection input: {relative}")
        current = current.parent
    if not missing and not path.is_file():
        raise InputError(f"Projection input is missing: {relative}")
    return path


def _inventory(root: Path, snapshot: Snapshot) -> dict[str, str]:
    owners: dict[str, str] = {}
    files: dict[str, str] = {}
    for component in snapshot.model.components:
        actual = source_files(root, component.paths)
        if not actual:
            raise InputError(f"Component {component.id} has no source files")
        for pattern in component.paths:
            if not any(matches(path, pattern) for path in actual):
                raise InputError(f"Component path matched no files: {component.id}: {pattern}")
        for relative, sha in actual.items():
            if relative in owners:
                raise InputError(f"Ambiguous component binding: {relative}")
            if not relative.endswith(".py"):
                raise InputError(f"Scoped preparation supports Python .py component files only: {relative}")
            _regular(root, relative)
            owners[relative], files[relative] = component.id, sha
    if not files:
        raise InputError("Scoped preparation needs component source files")
    return dict(sorted(files.items()))


def prepare_evidence(root: Path, snapshot: Snapshot, *, archctl: Path, briefcase: Path,
                     destination: Path, source_roots: tuple[str, ...],
                     model_dir: str = "architecture") -> dict:
    """Publish evidence only after complete application/projection pin checks.

    HEAD identifies the starting tree, not architecture authority. Current bytes
    overlay that tree, including uncommitted additions, edits and deletions.
    Executable hashes identify launchers, not authenticated installations.
    """
    root, destination = root.resolve(), destination.resolve()
    if destination.is_relative_to(root) and not destination.is_relative_to(root / ".archctl"):
        raise InputError("Preparation output inside the application must be under .archctl/")
    if destination.exists():
        raise InputError(f"Preparation output already exists; use a fresh directory: {destination}")
    if _git(root, "rev-parse", "--show-toplevel").strip() != str(root):
        raise InputError("Scoped preparation requires the Git worktree root")
    destination.mkdir(parents=True)
    started = time.monotonic()
    manifest = {"preparation_version": 1, "status": "error", "gate": "not_executed",
                "approval": "not_assessed", "support": dict(SUPPORT), "source_roots": list(source_roots)}
    export = destination / "export.json"
    try:
        if not source_roots:
            raise InputError("Scoped preparation requires explicit source roots")
        for source_root in source_roots:
            relative_path(source_root, "source root")
            import_root = contained(root, source_root)
            if not import_root.is_dir():
                raise InputError(f"Source root is not a directory: {source_root}")
            if (import_root / "__init__.py").is_file():
                raise InputError(f"Source root must be a package parent, not a Python package: {source_root}")
        tools = {"archctl": _tool(archctl, root), "briefcase": _tool(briefcase, root)}
        manifest["tools"] = tools
        for name, tool in tools.items():
            tool["version"] = _run([tool["path"], "--version"], root, destination / f"{name}-version.txt").strip()
        head = _git(root, "rev-parse", "HEAD").strip()
        files = _inventory(root, snapshot)
        if any(not any(r == "." or p.startswith(r + "/") for r in source_roots) for p in files):
            raise InputError("Source roots do not contain every component file")
        authority = dict(snapshot.sources)
        selected = {**files, **authority}
        for relative in selected:
            _regular(root, relative)
            if any(ord(char) < 32 for char in relative):
                raise InputError(f"Unsupported control character in projection path: {relative!r}")
        tracked = set(_git(root, "ls-tree", "-r", "--name-only", "-z", head).split("\0")) - {""}
        patterns = tuple(p for c in snapshot.model.components for p in c.paths)
        head_inputs = {p for p in tracked if p in authority or any(matches(p, g) for g in patterns)}
        overlay = {}
        for relative in sorted(head_inputs | selected.keys()):
            before = None
            if relative in tracked:
                # Hash raw blob bytes, not decoded text or checkout-filter output.
                blob = subprocess.run(["git", "-C", str(root), "show", f"{head}:{relative}"],
                                      capture_output=True, env=_environment(), timeout=60, check=True).stdout
                before = hashlib.sha256(blob).hexdigest()
            if before != selected.get(relative):
                overlay[relative] = {"head_sha256": before, "candidate_sha256": selected.get(relative)}
        manifest.update(model_revision=snapshot.revision,
                        source={"root": str(root), "head_sha": head, "component_files": files,
                                "authoring_files": authority, "overlay": overlay},
                        omitted_tracked_paths=sorted(tracked - selected.keys()))

        def recheck(application: Path) -> None:
            if compile_model(application, model_dir).revision != snapshot.revision:
                raise InputError("Authoring inputs changed during preparation")
            if _inventory(application, snapshot) != files:
                raise InputError("Component inventory changed during preparation")

        recheck(root)
        with tempfile.TemporaryDirectory(prefix="projection-", dir=destination) as temporary:
            projection = Path(temporary) / "tree"
            registered = False
            try:
                _git(root, "worktree", "add", "--detach", "--no-checkout", str(projection), head)
                registered = True
                # Anchored literal Git-ignore patterns select files, not trees.
                sparse = "\n".join("/" + re.sub(r"([\\*?\[\]#! ])", r"\\\1", p) for p in selected) + "\n"
                sparse_path = Path(_git(projection, "rev-parse", "--git-path", "info/sparse-checkout").strip())
                sparse_path.parent.mkdir(parents=True, exist_ok=True)
                sparse_path.write_text(sparse)
                # Command-local settings avoid changing the application Git config.
                _git(projection, "-c", "core.sparseCheckout=true", "-c", "core.sparseCheckoutCone=false",
                     "read-tree", "-mu", head)
                for relative, sha in selected.items():
                    target = _regular(projection, relative, missing=True)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(_regular(root, relative).read_bytes())
                    if file_digest(target) != sha:
                        raise InputError(f"Projection input changed while copying: {relative}")
                recheck(projection)
                database = projection / ".briefcase/briefcase.db"
                command = [tools["archctl"]["path"], "--root", str(projection), "--model-dir", model_dir,
                           "briefcase", "export-evidence", "--briefcase", tools["briefcase"]["path"],
                           "--db", str(database), "--out", str(export)]
                for source_root in source_roots:
                    command.extend(["--source-root", source_root])
                manifest["export_command"] = command
                _run(command, projection, destination / "exporter.stdout.txt")
                bundle = load_document(export)
                export_pin = file_digest(export)
                observations = parse_evidence(bundle, snapshot)
                if dict(observations.files) != files:
                    raise InputError("Exported component inventory differs from the candidate")
                if (observations.producer != PRODUCER or observations.coverage.analysis != "static"
                        or observations.coverage.status != "complete" or observations.coverage.gaps
                        or set(observations.coverage.components) != {c.id for c in snapshot.model.components}
                        or observations.coverage.relationship_kinds != ("imports",)):
                    raise InputError("Exported coverage does not establish the selected Python import scope")
                _run([tools["briefcase"]["path"], "status", "--db", str(database), "--json"],
                     projection, destination / "producer-status.json")
                status = load_document(destination / "producer-status.json")
                if not isinstance(status, dict) or not isinstance(status.get("scans"), list):
                    raise InputError("Invalid Briefcase publication inventory")
                publication = next((scan for scan in status.get("scans", [])
                                    if isinstance(scan, dict) and observations.source_revision.startswith(f"briefcase:{scan.get('view_id')}:")), None)
                if not publication or publication.get("status") != "published" or publication.get("scope") != "source":
                    raise InputError("Cannot identify the producing Briefcase publication")
                diagnostics = publication.get("diagnostics")
                if not isinstance(diagnostics, dict) or not isinstance(diagnostics.get("capture"), dict):
                    raise InputError("Invalid Briefcase publication capture diagnostics")
                capture = diagnostics["capture"]
                if (status.get("current_view") != publication["view_id"]
                        or capture.get("repository_root") != str(projection)
                        or capture.get("capture_head") != head):
                    raise InputError("Producing Briefcase publication has the wrong root, HEAD or view")
                manifest.update(publication=publication, source_revision=observations.source_revision)
                recheck(projection)
                recheck(root)
                if check_freshness(root, snapshot, observations):
                    raise InputError("Exported source inventory is stale or ambiguous")
            finally:
                if registered:
                    _git(root, "worktree", "remove", "--force", str(projection))
        if _git(root, "rev-parse", "HEAD").strip() != head:
            raise InputError("Candidate HEAD changed during preparation")
        for tool in tools.values():
            if file_digest(Path(tool["path"])) != tool["sha256"]:
                raise InputError("External executable changed during preparation")
        # Recheck after cleanup too. Never repair pins or reuse default evidence.
        recheck(root)
        if file_digest(export) != export_pin:
            raise InputError("Exported evidence changed after validation")
        manifest.update(status="prepared", evidence_sha256=export_pin)
        manifest["elapsed_seconds"] = round(time.monotonic() - started, 4)
        write_json(destination / "manifest.json", manifest)
        export.replace(destination / "evidence.json")
        return {"schema_version": "archctl.output.v2", "status": "written",
                "output": str(destination / "evidence.json"), "manifest": str(destination / "manifest.json")}
    except (InputError, OSError, ValueError, subprocess.SubprocessError) as exc:
        manifest.update(status="error", error=str(exc), elapsed_seconds=round(time.monotonic() - started, 4))
        write_json(destination / "manifest.json", manifest)
        raise InputError(f"Scoped evidence preparation failed; see {destination}: {exc}") from exc
