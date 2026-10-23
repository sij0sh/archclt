"""Task-authorized execution and harness results, independent of gate approval."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from archctl.core.context import inventory
from archctl.core.contracts import version
from archctl.core.io import (InputError, contained, digest, file_digest, load_document,
                             obj, relative_path, source_files, string, strings, write_json)
from archctl.integrations.process import execute_command


def pin_scope(root: Path, paths: list[str]) -> tuple[dict, list[str]]:
    if not paths:
        files, truncated = inventory(root)
        return {p: file_digest(contained(root, p)) for p in files}, (
            ["Source inventory truncated; execution identity covers a partial inventory"] if truncated else [])
    pins = source_files(root, tuple(paths))
    for path in paths:
        if not any(c in path for c in "*?[") and path not in pins:
            pins[relative_path(path, "execution path")] = None
    return dict(sorted(pins.items())), []


def execution_freshness(root: Path, record: dict) -> dict:
    source = record["source"]
    current, gaps = pin_scope(root, source["paths"])
    changed = sorted(p for p in source["files"].keys() | current.keys()
                     if source["files"].get(p) != current.get(p))
    status = ("stale" if changed or not source["stable_during_execution"] else
              "unverified" if not source["files"] or source["gaps"] or gaps else "current")
    return {"status": status, "changed_paths": changed,
            "limitations": source["gaps"] + gaps,
            "meaning": "Applies only to the recorded inputs and environment; not proof of requirement adequacy"}


def parse_execution(value: object) -> dict:
    v = obj(value, "execution", {"schema_version", "id", "origin", "task", "command", "cwd",
        "timeout_seconds", "environment", "started_at", "source", "result", "references", "revision"},
        {"schema_version", "id", "origin", "task", "command", "cwd", "timeout_seconds",
         "environment", "started_at", "source", "result", "references"})
    if v["schema_version"] != version("execution") or v["origin"] not in {"archctl", "harness"}:
        raise InputError(f"Expected {version('execution')} with archctl or harness origin")
    for key in ("id", "task", "environment", "started_at"):
        string(v[key], key)
    if not isinstance(v["command"], list) or not v["command"]:
        raise InputError("execution.command must be a nonempty argument vector")
    for arg in v["command"]:
        string(arg, "command argument")
    relative_path(v["cwd"], "execution.cwd")
    if type(v["timeout_seconds"]) is not int or not 1 <= v["timeout_seconds"] <= 300:
        raise InputError("execution timeout must be between 1 and 300")
    strings(v["references"], "execution.references")
    source = obj(v["source"], "execution.source", {"paths", "files", "gaps", "stable_during_execution"},
                 {"paths", "files", "gaps", "stable_during_execution"})
    for path in strings(source["paths"], "execution paths"):
        relative_path(path, "execution path", glob=True)
    if not isinstance(source["files"], dict) or type(source["stable_during_execution"]) is not bool:
        raise InputError("Invalid execution source pins")
    for path, pin in source["files"].items():
        relative_path(path, "execution source pin")
        if pin is not None and (not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin)):
            raise InputError("Invalid execution SHA256")
    strings(source["gaps"], "execution gaps")
    result = obj(v["result"], "execution.result", {"status", "message", "returncode", "duration_seconds",
        "stdout", "stderr", "output_truncated"}, {"status", "message", "returncode", "duration_seconds",
        "stdout", "stderr", "output_truncated"})
    if result["status"] not in {"passed", "failed", "unknown", "not_executed"}:
        raise InputError("Invalid execution status")
    code = result["returncode"]
    if code is not None and type(code) is not int:
        raise InputError("Execution returncode must be an integer or null")
    if (result["status"] == "passed" and code != 0) or (result["status"] == "failed" and code in {0, None}):
        raise InputError("Execution outcome contradicts its returncode")
    if result["status"] == "not_executed" and code is not None:
        raise InputError("Unexecuted command cannot have a returncode")
    if type(result["duration_seconds"]) not in {int, float} or result["duration_seconds"] < 0:
        raise InputError("Invalid execution duration")
    if type(result["output_truncated"]) is not bool:
        raise InputError("output_truncated must be boolean")
    for key in ("stdout", "stderr", "message"):
        if not isinstance(result[key], str) or len(result[key].encode()) > 262144:
            raise InputError("Invalid or oversized execution output")
    data = {k: item for k, item in v.items() if k != "revision"}
    revision = digest(data)
    if v.get("revision", revision) != revision:
        raise InputError("Execution revision does not match content")
    return {**data, "revision": revision}


def save_execution(root: Path, record: dict) -> Path:
    path = contained(root, f".archctl/executions/{uuid.uuid4().hex}.json")
    write_json(path, parse_execution(record))
    return path


def run(root: Path, command: list[str], *, task: str, paths: list[str], cwd: str = ".",
        timeout_seconds: int = 60, environment: str = "local", references: list[str] | None = None) -> dict:
    string(task, "task")
    string(environment, "environment")
    paths = sorted({relative_path(p, "execution path", glob=True) for p in paths})
    before, gaps = pin_scope(root, paths)
    started = datetime.now(timezone.utc).isoformat()
    result = execute_command(root, tuple(command), cwd, timeout_seconds)
    after, after_gaps = pin_scope(root, paths)
    return parse_execution({"schema_version": version("execution"), "id": "run-" + uuid.uuid4().hex,
        "origin": "archctl", "task": task, "command": command, "cwd": cwd,
        "timeout_seconds": timeout_seconds, "environment": environment, "started_at": started,
        "source": {"paths": paths, "files": before, "gaps": sorted(set(gaps + after_gaps)),
                   "stable_during_execution": before == after}, "result": result,
        "references": references or []})


def read_executions(root: Path) -> list[dict]:
    result = []
    for path in sorted(contained(root, ".archctl/executions").glob("*.json")):
        contained(root, path.relative_to(root).as_posix())
        result.append(parse_execution(load_document(path)))
    return result
