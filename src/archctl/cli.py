"""One CLI over independently testable modules. JSON is the default interface."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import yaml

from archctl import __version__
from archctl.atlas.impact import build_impact
from archctl.atlas.reconcile import reconcile
from archctl.atlas.report import markdown
from archctl.core.enforcement import version
from archctl.core.compiler import compile_model, has_authoring_model, read_snapshot
from archctl.core.io import InputError, contained, load_document, matches, write_json, write_text
from archctl.core.migration import migrate_document
from archctl.core.models import ACTIVE_DECISIONS, Snapshot
from archctl.core.change import read_change
from archctl.cli_gate import EXIT, changed_paths, run_gate
from archctl.cli_context import add_commands as context_commands, dispatch as context_dispatch
from archctl.guard.evaluate import check
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence, read_evidence
from archctl.integrations.briefcase.native import PRODUCER, SUPPORT, export_evidence
from archctl.integrations.briefcase.preparation import prepare_evidence
from archctl.observatory.workflows import run_workflow
from archctl.templates import initialize


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def parser() -> argparse.ArgumentParser:
    cli = ArgumentParser(prog="archctl", description="Architectural context, memory and verification for coding agents")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument("--root", type=Path, default=Path("."), help="Application repository root (global option)")
    cli.add_argument("--model-dir", default="architecture", help="Repository-relative model directory")
    commands = cli.add_subparsers(dest="command", required=True)
    context_commands(commands)
    init = commands.add_parser("init", help="Create an optional governed model; context needs no initialization")
    gate = commands.add_parser("gate", help="Verify locally against an explicitly reviewed Git commit")
    gate.add_argument("--baseline-ref", required=True, help="Full reviewed Git commit SHA")
    gate.add_argument("--change", type=Path, help="Reviewed archctl.change.v2 task contract")
    gate.add_argument("--evidence", type=Path, help="Use pinned evidence instead of exporting with Briefcase")
    briefcase_bin = os.environ.get("BRIEFCASE_BIN") or "briefcase"
    gate.add_argument("--briefcase", default=briefcase_bin)
    gate.add_argument("--source-root", action="append", default=[])
    gate.add_argument("--no-briefcase", action="store_true")
    gate.add_argument("--run", action="store_true", help="Execute verification from approved intent")
    gate.add_argument("--scope", choices=["changed", "all"], default="changed")
    gate.add_argument("--out-dir", type=Path, help="Parent for a fresh run directory under .archctl/")
    change = commands.add_parser("change", help="Validate a task contract against the candidate model")
    change_ops = change.add_subparsers(dest="operation", required=True)
    change_validate = change_ops.add_parser("validate")
    change_validate.add_argument("--input", required=True, type=Path)
    status = commands.add_parser("status", help="Report model, evidence and readiness without approving intent")
    status.add_argument("--format", choices=["json", "text"], default="json")
    status.add_argument("--evidence", type=Path, help="Normalized evidence; defaults to .archctl/evidence.json")
    status.add_argument("--drift", action="store_true", help="Include repository-wide reconciliation; unresolved findings need attention")
    status.add_argument("--out", type=Path)
    model = commands.add_parser("model").add_subparsers(dest="operation", required=True)
    model.add_parser("validate")
    migrate = model.add_parser("migrate", help="Convert one legacy model file to canonical v2 without overwriting it")
    migrate.add_argument("--input", required=True, type=Path)
    migrate.add_argument("--out", required=True, type=Path)
    compile_ = model.add_parser("compile")
    compile_.add_argument("--out", type=Path, default=Path(".archctl/candidate.lock.json"))
    decisions = commands.add_parser("decisions").add_subparsers(dest="operation", required=True)
    listing = decisions.add_parser("list")
    listing.add_argument("--components", nargs="+")
    showing = decisions.add_parser("show")
    showing.add_argument("id")
    evidence = commands.add_parser("evidence").add_subparsers(dest="operation", required=True)
    for operation in ("validate", "import"):
        evidence_op = evidence.add_parser(operation)
        evidence_op.add_argument("--input", required=True, type=Path)
        if operation == "import":
            evidence_op.add_argument("--out", type=Path, default=Path(".archctl/evidence.json"))
    briefcase = commands.add_parser("briefcase").add_subparsers(dest="operation", required=True)
    exporting = briefcase.add_parser("export-intent", help="Normalized handoff; not a native Briefcase declaration")
    exporting.add_argument("--out", type=Path)
    mapping = briefcase.add_parser("export-evidence",
                                   help="Map a retained Briefcase Python view to archctl.evidence.v2")
    mapping.add_argument("--out", type=Path, default=Path(".archctl/evidence.json"))
    mapping.add_argument("--db", type=Path, help="Briefcase database; defaults to .briefcase/briefcase.db")
    mapping.add_argument("--source-root", action="append", default=[],
                         help="Repeated Briefcase Python source root")
    mapping.add_argument("--briefcase", default=briefcase_bin, help="Briefcase executable; defaults to BRIEFCASE_BIN or PATH")
    preparing = briefcase.add_parser("prepare-evidence", help="Prepare a fresh scoped Python projection with independent tools")
    archctl_bin = os.environ.get("ARCHCTL_BIN") or None
    configured_briefcase = os.environ.get("BRIEFCASE_BIN") or None
    preparing.add_argument("--archctl", type=Path, default=archctl_bin, required=archctl_bin is None,
                           help="Absolute reviewed executable; defaults to ARCHCTL_BIN")
    preparing.add_argument("--briefcase", type=Path, default=configured_briefcase, required=configured_briefcase is None,
                           help="Absolute reviewed executable; defaults to BRIEFCASE_BIN")
    preparing.add_argument("--source-root", action="append", required=True, help="Explicit Python import resolution root; repeat as needed")
    preparing.add_argument("--out-dir", type=Path, required=True, help="New output directory; inside the application use .archctl/")
    impact = commands.add_parser("impact")
    impact.add_argument("task")
    _evidence_args(impact)
    _scope_args(impact)
    impact.add_argument("--out", type=Path)
    for name in ("reconcile", "report"):
        view = commands.add_parser(name)
        _evidence_args(view)
        view.add_argument("--format", choices=["json", "markdown"], default="markdown" if name == "report" else "json")
        view.add_argument("--out", type=Path)
    guard = commands.add_parser("guard").add_subparsers(dest="operation", required=True)
    check_ = guard.add_parser("check")
    _evidence_args(check_)
    _scope_args(check_)
    check_.add_argument("--baseline", required=True, type=Path, help="Trusted snapshot from outside the candidate's authority")
    check_.add_argument("--run", action="store_true", help="Execute approved required commands if structural checks pass")
    check_.add_argument("--environment", default="local")
    check_.add_argument("--out", type=Path)
    observe = commands.add_parser("observe").add_subparsers(dest="operation", required=True)
    run = observe.add_parser("run")
    run.add_argument("workflow")
    _evidence_args(run)
    run.add_argument("--baseline", required=True, type=Path)
    run.add_argument("--environment", default="local")
    run.add_argument("--out", type=Path)
    importing = observe.add_parser("import", help="Normalize already-mapped runtime evidence; no invented traces")
    importing.add_argument("--input", required=True, type=Path)
    importing.add_argument("--out", type=Path, default=Path(".archctl/runtime.json"))
    return cli


def _scope_args(command: argparse.ArgumentParser) -> None:
    scope = command.add_mutually_exclusive_group()
    scope.add_argument("--paths", nargs="+", help="Explicit changed or planned repository-relative paths")
    scope.add_argument("--changed", action="store_true", help="Git delta plus untracked files")
    scope.add_argument("--all", action="store_true", help="Check every declared component")
    command.add_argument("--base-ref", default="HEAD", help="Git comparison base for --changed")


def _evidence_args(command: argparse.ArgumentParser) -> None:
    command.add_argument("--evidence", required=True, type=Path)


def _path(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else contained(root, path.as_posix())


def _emit(args: argparse.Namespace, value: dict | str, root: Path) -> None:
    output = getattr(args, "out", None)
    if output:
        path = _path(root, output)
        if path in getattr(args, "_protected_paths", set()):
            raise InputError(f"Output would overwrite an authoring or evidence input: {path}")
        if any(path.is_relative_to(directory) for directory in getattr(args, "_protected_dirs", ())):
            raise InputError(f"Generated output cannot overwrite the model directory: {path}")
        if path.is_relative_to(root):
            rel = path.relative_to(root).as_posix()
            if any(matches(rel, pattern) for pattern in getattr(args, "_component_paths", ())):
                raise InputError(f"Generated output cannot overwrite component source: {path}")
        if isinstance(value, str):
            write_text(path, value)
        else:
            write_json(path, value)
        print(json.dumps({"schema_version": "archctl.output.v2", "output": str(path),
                          "status": value.get("status", "written") if isinstance(value, dict) else "written"}))
    elif isinstance(value, str):
        print(value, end="" if value.endswith("\n") else "\n")
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False))


STATUS_LIMIT = 20


def _display_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def _bounded(values: list, limit: int = STATUS_LIMIT) -> tuple[list, int, bool]:
    values = list(values)
    return values[:limit], len(values), len(values) > limit


def _status_model(model_dir: str) -> dict:
    return {"state": "missing", "directory": model_dir, "revision": None, "system_id": None, "name": None,
            "domains": 0, "components": 0,
            "decisions": {"total": 0, "active": 0, "by_status": {}},
            "relationships": 0, "interfaces": 0, "policies": 0, "verification": 0,
            "workflows": 0, "sources": 0, "message": None}


def _status_evidence(path: str) -> dict:
    return {"state": "not_checked", "path": path, "producer": None, "source_revision": None,
            "source_digest": None, "coverage": None, "pins": 0, "evidence_items": 0, "edges": 0,
            "freshness": {"status": "not_executed", "total": 0, "returned": 0, "truncated": False,
                          "findings": []},
            "message": None}


def _status(root: Path, model_dir: str, evidence_arg: Path | None, *, drift: bool = False) -> tuple[dict, Snapshot | None]:
    model_path = contained(root, model_dir)
    model = _status_model(model_dir)
    snapshot = None
    unknowns: list[str] = []
    actions: list[str] = []
    drift_report = {"state": "not_checked", "findings": [], "findings_total": 0,
                    "findings_truncated": False, "unresolved": 0, "ignored_intra_component": 0}
    if not has_authoring_model(model_path):
        unknowns.append(f"No architecture/model.* or system.* file was found in: {model_dir}")
        actions.append("Author architecture/model.yaml or run archctl init")
    else:
        try:
            snapshot = compile_model(root, model_dir)
        except (InputError, OSError, UnicodeError, ValueError) as exc:
            model.update(state="invalid", message=str(exc))
            unknowns.append(f"Architecture model is invalid: {exc}")
            actions.append("Fix the model validation error, then run model validate")
        else:
            by_status = dict(sorted(Counter(d.status for d in snapshot.model.decisions).items()))
            model.update(state="valid", revision=snapshot.revision,
                         system_id=snapshot.model.system_id, name=snapshot.model.name,
                         domains=len(snapshot.model.domains), components=len(snapshot.model.components),
                         decisions={"total": len(snapshot.model.decisions),
                                    "active": sum(d.status in ACTIVE_DECISIONS for d in snapshot.model.decisions),
                                    "by_status": by_status},
                         relationships=len(snapshot.model.relationships),
                         interfaces=len(snapshot.model.interfaces), policies=len(snapshot.model.policies),
                         verification=len(snapshot.model.verification), workflows=len(snapshot.model.workflows),
                         sources=len(snapshot.sources))
            if not snapshot.model.components:
                unknowns.append("Architecture model has no components")
                actions.append("Bind at least one source component in the architecture model")

    evidence_path = _path(root, evidence_arg) if evidence_arg else contained(root, ".archctl/evidence.json")
    evidence = _status_evidence(_display_path(root, evidence_path))
    if snapshot is None:
        evidence["message"] = "Evidence was not checked because the model is not valid"
    elif not evidence_path.is_file():
        evidence.update(state="missing", message="No normalized evidence bundle was found")
        unknowns.append(f"Evidence is missing: {evidence['path']}")
        actions.append("Produce archctl.evidence.v2 evidence")
    else:
        try:
            observations = read_evidence(evidence_path, snapshot)
            freshness = check_freshness(root, snapshot, observations)
        except (InputError, OSError, UnicodeError, ValueError) as exc:
            evidence.update(state="invalid", message=str(exc))
            unknowns.append(f"Evidence is invalid: {exc}")
            actions.append("Regenerate or repair the evidence bundle")
        else:
            coverage = observations.coverage
            covered = set(coverage.components)
            needed_components = {c.id for c in snapshot.model.components}
            needed_kinds = {r.kind for r in snapshot.model.relationships} | {
                kind for policy in snapshot.model.policies if policy.kind == "forbidden_dependency"
                for kind in policy.kinds}
            missing_components = sorted(needed_components - covered)
            missing_kinds = sorted(needed_kinds - set(coverage.relationship_kinds))
            if freshness:
                state = "stale"
            elif coverage.analysis != "static":
                state = "runtime"
            elif coverage.status != "complete" or coverage.gaps or missing_components or missing_kinds:
                state = "partial"
            else:
                state = "current"
            gaps, gaps_total, gaps_truncated = _bounded(list(coverage.gaps))
            findings, findings_total, findings_truncated = _bounded([f.to_dict() for f in freshness])
            messages = {"current": None, "stale": "Evidence pins are stale; regenerate evidence",
                        "runtime": "Evidence is runtime-only; it cannot prove absence",
                        "partial": "Evidence coverage is incomplete"}
            evidence.update(state=state, message=messages[state],
                            producer={"name": observations.producer, "version": observations.producer_version},
                            source_revision=observations.source_revision,
                            source_digest=observations.source_digest,
                            coverage={"analysis": coverage.analysis, "status": coverage.status,
                                      "components": len(coverage.components),
                                      "relationship_kinds": list(coverage.relationship_kinds),
                                      "gaps": gaps, "gaps_total": gaps_total, "gaps_truncated": gaps_truncated},
                            pins=len(observations.files), evidence_items=len(observations.evidence),
                            edges=len(observations.edges),
                            freshness={"status": "unknown" if freshness else "passed",
                                       "total": findings_total, "returned": len(findings),
                                       "truncated": findings_truncated, "findings": findings})
            if observations.producer == PRODUCER:
                evidence["support"] = dict(SUPPORT)
            unknowns.extend(f.message for f in freshness)
            if coverage.analysis != "static":
                unknowns.append("Evidence analysis is runtime-only; absence cannot be proven")
                actions.append("Obtain complete static evidence for a passing gate")
            if coverage.status != "complete":
                unknowns.append("Evidence coverage is partial")
                actions.append("Close the declared evidence gaps or regenerate evidence")
            unknowns.extend(coverage.gaps)
            if missing_components:
                unknowns.append("Evidence does not cover components: " + ", ".join(missing_components))
                actions.append("Regenerate evidence for every declared component")
            if missing_kinds:
                unknowns.append("Evidence does not cover relationship kinds: " + ", ".join(missing_kinds))
                actions.append("Regenerate evidence for every declared relationship kind")
            if state == "stale":
                actions.append("Regenerate evidence after the source changes")
            if drift:
                reconciliation = reconcile(snapshot, observations, freshness)
                unresolved = [f for f in reconciliation["findings"] if f["status"] != "passed"]
                entries, count, truncated = _bounded(reconciliation["findings"])
                drift_report.update(state="unresolved" if unresolved else "clean", findings=entries,
                                    findings_total=count, findings_truncated=truncated,
                                    unresolved=len(unresolved),
                                    ignored_intra_component=len(reconciliation["ignored"]))
                unknowns.extend("Drift: " + f["message"] for f in unresolved)
                if unresolved:
                    actions.append("Triage drift against reviewed intent; use reconcile for all findings")

    unknowns = list(dict.fromkeys(unknowns))
    returned, total, truncated = _bounded(unknowns)
    if model["state"] == "missing":
        status = "needs_model"
    elif model["state"] == "invalid":
        status = "needs_attention"
    elif evidence["state"] == "current" and not unknowns:
        status = "ready"
    else:
        status = "needs_attention"
    actions.append("Run gate with the reviewed baseline and a change contract for a task verdict")
    actions = list(dict.fromkeys(actions))
    return {"schema_version": "archctl.status.v2", "operation": "status", "root": str(root),
            "status": status, "tool": {"name": "archctl", "version": __version__},
            "model": model, "evidence": evidence,
            "gate": {"status": "not_executed",
                     "reason": "status does not run Guard or execute verification commands"},
            "approval": {"status": "not_assessed",
                         "reason": "A separately supplied reviewed baseline establishes authority"},
            "unknowns": returned, "unknowns_total": total, "unknowns_truncated": truncated,
            "next_actions": actions, **({"drift": drift_report} if drift else {})}, snapshot


def _status_text(report: dict) -> str:
    model, evidence = report["model"], report["evidence"]
    if model["state"] == "valid":
        model_line = (f"Model: valid (revision {model['revision']}; {model['components']} components; "
                      f"{model['decisions']['total']} decisions)")
    else:
        model_line = f"Model: {model['state']}" + (f" ({model['message']})" if model["message"] else "")
    evidence_line = f"Evidence: {evidence['state']} ({evidence['path']})"
    if evidence["message"]:
        evidence_line += f" - {evidence['message']}"
    lines = [f"Status: {report['status']}", model_line, evidence_line]
    if evidence.get("support"):
        lines.append("Support: " + evidence["support"]["limitation"])
    if "drift" in report:
        lines.append(f"Drift: {report['drift']['state']} ({report['drift']['unresolved']} unresolved)")
    lines += [f"Gate: {report['gate']['status']}", f"Approval: {report['approval']['status']}", "",
              "Unknowns:"]
    lines += [f"- {item}" for item in report["unknowns"]] or ["- None"]
    if report["unknowns_truncated"]:
        lines.append(f"- ... and {report['unknowns_total'] - len(report['unknowns'])} more")
    lines += ["", "Next actions:"]
    lines += [f"- {item}" for item in report["next_actions"]]
    return "\n".join(lines) + "\n"


def dispatch(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if args.command in {"context", "memory", "verify"}:
        paths = (changed_paths(root, args.base_ref) if getattr(args, "changed", False)
                 else getattr(args, "paths", []))
        return context_dispatch(root, args, paths)
    if args.command == "gate":
        code, result = run_gate(root, args)
        print(json.dumps(result, indent=2))
        return code
    args._protected_paths = {_path(root, getattr(args, name)) for name in ("input", "evidence", "baseline")
                             if isinstance(getattr(args, name, None), Path)}
    if args.command == "init":
        if args.model_dir != "architecture":
            raise InputError("init currently uses architecture/; rename it afterwards to use --model-dir")
        _emit(args, {"created": initialize(root),
                     "next": "Use context without adoption, or review and baseline this optional model for governed gates"}, root)
        return 0
    if args.command == "status":
        if not root.is_dir():
            raise InputError(f"Repository root is not a directory: {root}")
        report, snapshot = _status(root, args.model_dir, args.evidence, drift=args.drift)
        args._protected_dirs = {contained(root, args.model_dir)}
        args._protected_paths.add(contained(root, ".archctl/evidence.json"))
        if snapshot is not None:
            args._protected_paths.update(contained(root, rel) for rel, _ in snapshot.sources)
            args._component_paths = tuple(p for c in snapshot.model.components for p in c.paths)
        _emit(args, _status_text(report) if args.format == "text" else report, root)
        return 0 if report["status"] == "ready" else 2
    if args.command == "model" and args.operation == "migrate":
        source, target = _path(root, args.input), _path(root, args.out)
        if source.resolve() == target.resolve() or target.exists():
            raise InputError("Migration output must be a new file; review it before replacing intent")
        value = migrate_document(load_document(source))
        write_text(target, yaml.safe_dump(value, sort_keys=False))
        print(json.dumps({"schema_version": "archctl.output.v2", "status": "written", "output": str(target)}))
        return 0
    snapshot = compile_model(root, args.model_dir)
    args._protected_paths.update(contained(root, rel) for rel, _ in snapshot.sources)
    args._component_paths = tuple(p for c in snapshot.model.components for p in c.paths)
    if args.command == "change":
        change = read_change(_path(root, args.input), snapshot)
        unknowns = [f"Acceptance criterion has no verification: {a.id}" for a in change.acceptance if not a.checks]
        unknowns += [f"Open question: {q}" for q in change.open_questions]
        _emit(args, {"schema_version": "archctl.change-validation.v2", "status": "unknown" if unknowns else "passed",
                     "change_revision": change.revision, "unknowns": unknowns}, root)
        return 2 if unknowns else 0
    if args.command == "model":
        _emit(args, snapshot.to_dict() if args.operation == "compile" else
              {"schema_version": "archctl.model-validation.v2", "status": "passed",
               "revision": snapshot.revision, "components": len(snapshot.model.components)}, root)
        return 0
    if args.command == "decisions":
        decisions = snapshot.model.decisions
        if args.operation == "show":
            selected = next((d for d in decisions if d.id == args.id), None)
            if selected is None:
                raise InputError(f"Unknown decision: {args.id}")
            _emit(args, {"schema_version": "archctl.decision.v2", **asdict(selected)}, root)
        else:
            requested = set(args.components or [])
            known = {c.id for c in snapshot.model.components}
            if requested - known:
                raise InputError(f"Unknown components: {sorted(requested - known)}")
            _emit(args, {"schema_version": "archctl.decisions.v2", "model_revision": snapshot.revision,
                         "decisions": [asdict(d) for d in decisions if not requested or set(d.components) & requested]}, root)
        return 0
    if args.command == "briefcase":
        if args.operation == "prepare-evidence":
            result = prepare_evidence(root, snapshot, archctl=args.archctl, briefcase=args.briefcase,
                                      destination=_path(root, args.out_dir), source_roots=tuple(args.source_root),
                                      model_dir=args.model_dir)
            _emit(args, result, root)
        elif args.operation == "export-evidence":
            database = _path(root, args.db) if args.db else None
            bundle = export_evidence(root, snapshot, binary=args.briefcase, database=database,
                                     source_roots=tuple(args.source_root))
            _emit(args, parse_evidence(bundle, snapshot).to_dict(), root)
        else:
            _emit(args, {"schema_version": version("intent"), "model_revision": snapshot.revision,
                        "native_briefcase_format": False, "model": snapshot.model.to_dict()}, root)
        return 0
    if args.command == "evidence" or (args.command == "observe" and args.operation == "import"):
        observations = read_evidence(_path(root, args.input), snapshot)
        if args.command == "observe" and observations.coverage.analysis != "runtime":
            raise InputError("observe import requires runtime evidence")
        freshness = check_freshness(root, snapshot, observations)
        if args.command == "evidence" and args.operation == "validate":
            _emit(args, {"status": "unknown" if freshness else "passed", "source_digest": observations.source_digest,
                         "findings": [f.to_dict() for f in freshness]}, root)
        else:
            _emit(args, observations.to_dict(), root)
        return 2 if freshness else 0
    observations = read_evidence(_path(root, args.evidence), snapshot)
    freshness_fn = lambda: check_freshness(root, snapshot, observations)
    freshness = freshness_fn()
    if args.command in {"reconcile", "report"}:
        result = reconcile(snapshot, observations, freshness)
        _emit(args, markdown(snapshot, result) if args.format == "markdown" else result, root)
        return 0  # Views report drift; Guard owns the blocking decision.
    if args.command == "observe":
        baseline = read_snapshot(_path(root, args.baseline))
        report = run_workflow(root, snapshot, baseline, observations, args.workflow,
                              environment=args.environment, freshness=freshness_fn)
        _emit(args, report, root)
        return EXIT[report["status"]]
    paths = changed_paths(root, args.base_ref) if args.changed else (args.paths or [])
    # With no explicit scope, Guard checks the entire model. Impact without
    # concrete planned paths stays incomplete, rather than inventing scope.
    all_components = args.all or (args.command == "guard" and not args.paths and not args.changed)
    impact = build_impact(snapshot, observations, paths,
                          args.task if args.command == "impact" else "Verify candidate change",
                          freshness, all_components=all_components)
    if args.command == "impact":
        _emit(args, impact, root)
        return 2 if impact["assessment"] == "partial" else 0
    baseline = read_snapshot(_path(root, args.baseline))
    report = check(root, snapshot, baseline, observations, impact, execute=args.run,
                   environment=args.environment, freshness=freshness_fn)
    _emit(args, report, root)
    return EXIT[report["status"]]


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return dispatch(args)
    except (InputError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"schema_version": "archctl.error.v2", "status": "error", "message": str(exc)}), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
