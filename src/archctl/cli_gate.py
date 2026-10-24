"""A local gate with a baseline evaluator and an isolated directory per run.

The launcher and filesystem are trusted. This is a reproducible review workflow,
not protection from an agent with the operator's credentials and permissions.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from archctl.atlas.change_scope import acceptance_results, apply_change
from archctl.atlas.impact import build_impact
from archctl.atlas.reconcile import reconcile
from archctl.cli_report import markdown, overall_status
from archctl.core.contracts import version
from archctl.core.enforcement import GUARANTEE
from archctl.core.change import read_change
from archctl.core.compiler import compile_model
from archctl.core.io import InputError, contained, digest, file_digest, load_document, write_json, write_text
from archctl.guard.evaluate import check
from archctl.integrations.briefcase.adapter import check_freshness, read_evidence
from archctl.integrations.briefcase.native import PRODUCER, SUPPORT, export_evidence
from archctl.integrations.git import changed_paths, git as _git


EXIT = {"passed": 0, "failed": 1, "unknown": 2, "not_executed": 2, "error": 3}
LAUNCHER = """import sys
sys.path.insert(0, sys.argv[1])
from archctl.cli_gate import worker
sys.exit(worker(sys.argv[2]))
"""


def _tool_digest(source: Path) -> str:
    return digest({p.relative_to(source).as_posix(): file_digest(p)
                   for p in sorted((source / "archctl").rglob("*.py"))})


def _path_pins(root: Path, paths: list[str]) -> dict:
    return {path: file_digest(contained(root, path)) if contained(root, path).is_file() else None
            for path in paths}


def _save(report: Path, summary: dict) -> int:
    summary["gate_status"] = summary["status"]  # compatibility for review consumers
    write_json(report / "gate-summary.json", summary)
    write_text(report / "gate-summary.md", markdown(summary))
    return EXIT[summary["status"]]


def blocking_drift(snapshot, observations, report: dict, affected: set[str]) -> list[dict]:
    """Optional missing declarations and unrelated warnings are informational."""
    relations = {r.id: r for r in snapshot.model.relationships}
    edges = {e.id: e for e in observations.edges}
    policies = {p.id: p for p in snapshot.model.policies}
    result = []
    for finding in report["findings"]:
        if finding["status"] == "passed" or finding.get("obligation") == "advisory":
            continue
        prefix, _, ident = finding["id"].partition(":")
        if prefix == "missing" and ident in relations:
            entity = relations[ident]
            if not entity.required:
                continue
        elif prefix == "observed" and ident in edges:
            entity = edges[ident]
        elif prefix == "violation" and ident in policies:
            entity = policies[ident]
        else:
            result.append(finding)  # freshness findings have no edge scope
            continue
        if {entity.source, entity.target} & affected:
            result.append(finding)
    return result


def evaluate(request: dict) -> int:
    """Executed only in the selected evaluator's fresh Python process."""
    root, report, baseline_root = (Path(request[k]) for k in ("root", "report", "baseline_root"))
    summary = {"schema_version": version("gate"), "status": "unknown",
               "baseline_sha": request["baseline_sha"], "head_sha": _git(root, "rev-parse", "HEAD"),
               "candidate_dirty": bool(changed_paths(root, "HEAD")), "scope": request["scope"],
               "evaluator": request["evaluator"], "approval": "not_assessed", "stages": {},
               "findings": [], "verification": [], "acceptance": []}
    try:
        baseline = compile_model(baseline_root, request["model_dir"])
        snapshot = compile_model(root, request["model_dir"])
        summary.update(schema_version=version("gate"),
                       enforcement=snapshot.model.enforcement, guarantee=GUARANTEE)
        write_json(report / "baseline.lock.json", baseline.to_dict())
        write_json(report / "candidate.lock.json", snapshot.to_dict())
        summary.update(model_revision=snapshot.revision, baseline_revision=baseline.revision)
        change_path = Path(request["change"]) if request.get("change") else None
        change_pin = file_digest(change_path) if change_path else None
        change = read_change(change_path, snapshot) if change_path else None
        if change:
            write_json(report / "change.json", change.to_dict())
            summary["change_revision"] = change.revision
        paths = changed_paths(root, request["baseline_sha"])
        path_pins = _path_pins(root, paths)
        evidence_path = Path(request["evidence"]) if request.get("evidence") else root / ".archctl/evidence.json"
        if not request.get("evidence") and not request["no_briefcase"] and shutil.which(request["briefcase"]):
            # A failed fresh export never silently falls back to an old bundle.
            bundle = export_evidence(root, snapshot, binary=request["briefcase"],
                                     source_roots=tuple(request["source_roots"]))
            write_json(report / "evidence.json", bundle)
        elif evidence_path.is_file():
            write_json(report / "evidence.json", load_document(evidence_path))
        else:
            summary.update(status="unknown", error="No source evidence is available. Install Briefcase or supply --evidence.")
            return _save(report, summary)
        observations = read_evidence(report / "evidence.json", snapshot)
        if observations.producer == PRODUCER:
            summary["support"] = dict(SUPPORT)
        freshness = lambda: check_freshness(root, snapshot, observations)
        stale = freshness()
        validation = {"status": "unknown" if stale else "passed", "source_digest": observations.source_digest,
                      "findings": [f.to_dict() for f in stale]}
        write_json(report / "evidence-validation.json", validation)
        impact = build_impact(snapshot, observations, paths, change.objective if change else "Local architecture audit",
                              stale, all_components=request["scope"] == "all")
        if change:
            impact = apply_change(change, snapshot, baseline, impact)
        recon = reconcile(snapshot, observations, stale)
        write_json(report / "reconcile.json", recon)
        affected = {c["id"] for c in impact["affected_components"]}
        drift = blocking_drift(snapshot, observations, recon, affected)
        write_json(report / "impact.json", impact)
        # In-scope drift blocks command execution while Guard still evaluates
        # explicit policies, allowing proven violations to remain failures.
        guard_impact = dict(impact)
        if drift:
            guard_impact["unknowns"] = sorted(set(impact["unknowns"] + [f["message"] for f in drift]))
            guard_impact["unknown_details"] = impact["unknown_details"] + [
                {"message": f["message"], "category": "drift", "obligation": "required"} for f in drift]
            guard_impact["assessment"] = "partial"
            guard_impact.pop("revision", None)
            guard_impact["revision"] = digest(guard_impact)
            write_json(report / "impact.json", guard_impact)
        guard = check(root, snapshot, baseline, observations, guard_impact, execute=request["run"],
                      environment="local", freshness=freshness, scope_components=affected,
                      required_policies=set(change.policies) if change else set())
        write_json(report / "guard.json", guard)
        criteria = acceptance_results(change, guard["verification"]) if change else []
        contract_status = overall_status(*(c["status"] for c in criteria)) if change else None
        stability_status = "passed"
        if change_path and (not change_path.is_file() or file_digest(change_path) != change_pin):
            stability_status = "unknown"
            summary["findings"].append({"status": "unknown", "message": "Change contract changed during verification"})
        if changed_paths(root, request["baseline_sha"]) != paths or _path_pins(root, paths) != path_pins:
            stability_status = "unknown"
            summary["findings"].append({"status": "unknown", "message": "Changed path inventory or contents changed during verification; rerun"})
        stages = {"evidence": validation["status"], "guard": guard["status"],
                  "drift": overall_status(*(f["status"] for f in drift)) if drift else "passed"}
        if contract_status is not None:
            stages["acceptance"] = contract_status
        stages["stability"] = stability_status
        summary.update(status=overall_status(*stages.values()), stages=stages,
                       source_revision=observations.source_revision, source_digest=observations.source_digest,
                       authority_changed=guard["authority_changed"], acceptance=criteria,
                       verification=guard["verification"], changed_paths=paths,
                       affected_components=guard_impact["affected_components"],
                       drift={"status": stages["drift"], "blocking": drift,
                              "informational": [f for f in recon["findings"] if f not in drift]},
                       findings=summary["findings"] + [f for f in guard["findings"] if f["status"] != "passed"] + drift)
        reported = {(f.get("id"), f["message"]) for f in summary["findings"]}
        summary["findings"] += [f for f in recon["findings"] if f.get("obligation") == "advisory"
                                and f["status"] != "passed" and (f.get("id"), f["message"]) not in reported]
        return _save(report, summary)
    except (InputError, OSError, UnicodeError, ValueError) as exc:
        summary.update(status="error", error=str(exc))
        return _save(report, summary)


def worker(request_file: str) -> int:
    return evaluate(load_document(Path(request_file)))


def run_gate(root: Path, args) -> tuple[int, dict]:
    """Select a reproducible baseline and run its evaluator, never candidate code."""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.baseline_ref):
        raise InputError("--baseline-ref requires the full reviewed Git commit SHA, not a branch or tag")
    sha = _git(root, "rev-parse", "--verify", f"{args.baseline_ref}^{{commit}}")
    prefix = _git(root, "rev-parse", "--show-prefix")
    destination = (args.out_dir if args.out_dir else root / ".archctl/runs")
    destination = (root / destination).resolve() if not destination.is_absolute() else destination.resolve()
    if not destination.is_relative_to(root / ".archctl"):
        raise InputError("--out-dir must be under the application's .archctl/ directory")
    destination.mkdir(parents=True, exist_ok=True)
    report = Path(tempfile.mkdtemp(prefix="run-", dir=destination))
    # Some restricted environments use the application's cwd as the system
    # temporary directory. Keep the worktree in explicitly excluded tool space
    # rather than letting its nested Git files contaminate application scope.
    temporary_root = root / ".archctl/worktrees"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="baseline-", dir=temporary_root) as directory:
        worktree = Path(directory) / "tree"
        try:
            _git(root, "worktree", "add", "--detach", str(worktree), sha)
            baseline_root = worktree / prefix
            baseline_source = baseline_root / "src"
            if (baseline_source / "archctl").is_dir():
                if not (baseline_source / "archctl/cli_gate.py").is_file():
                    raise InputError("Baseline tool predates the local gate. Review and baseline a supported tool before dogfooding it.")
                source = baseline_source
            else:
                source = Path(__file__).resolve().parents[1]
                if source.is_relative_to(root):
                    raise InputError("Install a reviewed archctl outside the candidate repository")
            evaluator = {"source": "baseline" if source == baseline_source else "installation",
                         "digest": _tool_digest(source), "python": sys.version.split()[0]}
            def absolute(value):
                return str((root / value).resolve()) if value else None
            request = {"root": str(root), "report": str(report), "baseline_root": str(baseline_root),
                       "baseline_sha": sha, "model_dir": args.model_dir,
                       "change": absolute(args.change), "evidence": absolute(args.evidence),
                       "briefcase": absolute(Path(args.briefcase)) if "/" in args.briefcase else args.briefcase,
                       "no_briefcase": args.no_briefcase,
                       "source_roots": args.source_root, "run": args.run, "scope": args.scope,
                       "evaluator": evaluator}
            request_file = report / "request.json"
            write_json(request_file, request)
            environment = os.environ.copy()
            # The evaluator uses its absolute interpreter with -I. Reviewed
            # application commands keep the caller's runner environment.
            result = subprocess.run([sys.executable, "-I", "-c", LAUNCHER, str(source), str(request_file)],
                                    cwd=report, env=environment, capture_output=True, text=True, check=False)
            write_text(report / "evaluator.log", result.stdout + result.stderr)
            summary_file = report / "gate-summary.json"
            if not summary_file.is_file():
                raise InputError("Trusted evaluator did not produce a result; see evaluator.log")
            summary = load_document(summary_file)
            if result.returncode != EXIT.get(summary.get("status")):
                raise InputError("Evaluator exit and reported status disagree")
            return result.returncode, {"schema_version": version("gate-output"), "status": summary["status"],
                                       "baseline_sha": sha, "report": str(report)}
        except (InputError, OSError, ValueError) as exc:
            _save(report, {"schema_version": version("gate"), "status": "error", "baseline_sha": sha,
                           "approval": "not_assessed", "stages": {}, "error": str(exc)})
            return 3, {"schema_version": version("gate-output"), "status": "error", "report": str(report), "message": str(exc)}
        finally:
            if worktree.exists():
                subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(worktree)], capture_output=True)
