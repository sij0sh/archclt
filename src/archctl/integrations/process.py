"""Bounded subprocess execution shared by Guard and Observatory."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Callable

from archctl.core.compiler import compile_model
from archctl.core.io import InputError, contained, digest, file_digest, string
from archctl.core.models import Finding, Observations, Snapshot, Verification


def authority_matches(candidate: Snapshot, baseline: Snapshot) -> bool:
    return candidate.model.to_dict() == baseline.model.to_dict()


def authoring_freshness(root: Path, snapshot: Snapshot) -> list[Finding]:
    problems = []
    for rel, expected in snapshot.sources:
        path = contained(root, rel)
        if not path.is_file() or file_digest(path) != expected:
            problems.append(Finding(f"model-stale:{rel}", "unknown", f"Architecture authoring input changed during verification: {rel}"))
    # Recompile to detect added ADRs/files, which checking only existing pins misses.
    if snapshot.sources:
        directory = os.path.commonpath([str(Path(rel).parent) for rel, _ in snapshot.sources]) or "."
        try:
            current = compile_model(root, directory)
            if current.revision != snapshot.revision and not problems:
                problems.append(Finding("model-inventory-changed", "unknown", "Architecture input inventory changed during verification"))
        except InputError as exc:
            problems.append(Finding("model-became-invalid", "unknown", f"Architecture became invalid during verification: {exc}"))
    return problems


def _result(check: Verification, snapshot: Snapshot, observations: Observations,
            environment: str, status: str, message: str) -> dict:
    return {"id": check.id, "obligation": "required", "required_by": [], "status": status, "message": message,
            "model_revision": snapshot.revision, "source_digest": observations.source_digest,
            "environment": environment, "command": list(check.command), "cwd": check.cwd,
            "command_digest": digest({"command": check.command, "cwd": check.cwd,
                                      "timeout_seconds": check.timeout_seconds}),
            "returncode": None, "duration_seconds": 0.0, "stdout": "", "stderr": "",
            "output_truncated": False}


def execute_command(root: Path, command: tuple[str, ...], cwd: str,
                    timeout_seconds: int) -> dict:
    """Run a caller-selected argument vector independently of architecture policy."""
    if not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise ValueError("command must be a nonempty argument vector")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise ValueError("timeout_seconds must be between 1 and 300")
    directory = contained(root, cwd)
    result = {"status": "unknown", "message": "Command did not start", "returncode": None,
              "duration_seconds": 0.0, "stdout": "", "stderr": "", "output_truncated": False}
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = None
        try:
            process = subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, shell=False, start_new_session=os.name == "posix")
            code = process.wait(timeout=timeout_seconds)
            result.update(status="passed" if code == 0 else "failed", returncode=code,
                          message="Command completed successfully" if code == 0 else "Command returned a nonzero exit code")
        except subprocess.TimeoutExpired:
            if process is not None:
                _kill(process)
            result["message"] = f"Command timed out after {timeout_seconds}s"
        except OSError as exc:
            result["message"] = f"Command could not start: {exc}"
        except BaseException:
            if process is not None:
                _kill(process)
            raise
        result["duration_seconds"] = round(time.monotonic() - started, 4)
        for stream, name in ((stdout, "stdout"), (stderr, "stderr")):
            size = stream.tell()
            stream.seek(0)
            result[name] = stream.read(65536).decode("utf-8", errors="replace")
            result["output_truncated"] |= size > 65536
    return result


def run_checks(root: Path, snapshot: Snapshot, baseline: Snapshot,
               observations: Observations, ids: list[str], *, execute: bool,
               environment: str, freshness: Callable[[], list[Finding]]) -> list[dict]:
    index = {v.id: v for v in snapshot.model.verification}
    environment = string(environment, "environment")
    results = []
    approved = authority_matches(snapshot, baseline)
    for ident in sorted(set(ids)):
        if ident not in index:
            raise InputError(f"Unknown verification target: {ident}")
        check = index[ident]
        result = _result(check, snapshot, observations, environment, "not_executed", "Execution was not requested")
        if not approved:
            result["message"] = "Candidate intent differs from the trusted baseline; commands were not executed"
        elif not execute:
            pass
        elif freshness() or authoring_freshness(root, snapshot):
            result.update(status="unknown", message="Source or model pins are stale; command was not executed")
        else:
            result.update(execute_command(root, check.command, check.cwd, check.timeout_seconds))
            if freshness() or authoring_freshness(root, snapshot):
                result.update(status="unknown", message="Source or architecture changed during execution; result cannot attest the candidate")
        results.append(result)
    return results


def _kill(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()
