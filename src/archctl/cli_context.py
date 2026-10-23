"""Context-first CLI composition. Existing v2 governed commands are independent."""

from __future__ import annotations

import json
from pathlib import Path

from archctl.atlas.context import build_context, markdown
from archctl.core.compiler import compile_model, has_authoring_model
from archctl.core.context import decision_notes, inventory, load_bindings, terms
from archctl.core.io import (InputError, contained, digest, load_document, relative_path,
                             string, write_json, write_text)
from archctl.core.memory import freshness, read_memories, remember
from archctl.core.models import Component, Domain, Model, Snapshot
from archctl.integrations.briefcase.adapter import check_freshness, parse_evidence
from archctl.integrations.briefcase.native import export_evidence
from archctl.integrations.verification import (execution_freshness, parse_execution,
    read_executions, run, save_execution)


def add_commands(commands) -> None:
    context = commands.add_parser("context", help="Assemble architectural reasons and evidence without adoption")
    context.add_argument("task")
    scope = context.add_mutually_exclusive_group()
    scope.add_argument("--paths", nargs="+", default=[])
    scope.add_argument("--changed", action="store_true")
    context.add_argument("--base-ref", default="HEAD")
    context.add_argument("--evidence", type=Path)
    context.add_argument("--refresh-evidence", action="store_true", help="Use the existing public Briefcase Python mapper")
    context.add_argument("--briefcase", help="Briefcase executable for explicit evidence refresh")
    context.add_argument("--source-root", action="append", default=[])
    context.add_argument("--dependency", nargs=2, action="append", default=[], metavar=("SOURCE", "TARGET"),
                         help="Hypothetical import between component IDs/aliases or file paths")
    context.add_argument("--reference", action="append", default=[], help="Opaque conversation/Case/source reference from the agent")
    context.add_argument("--limit", type=int, default=8, help="Maximum items per section, 1–50")
    context.add_argument("--format", choices=["json", "markdown"], default="json")
    context.add_argument("--out", type=Path, help="Generated output under .archctl/")
    memory = commands.add_parser("memory", help="Record and retrieve attributable architectural reasons")
    operations = memory.add_subparsers(dest="operation", required=True)
    record = operations.add_parser("record", help="Append immutable reasoning from the coding session")
    record.add_argument("--input", required=True, type=Path)
    show = operations.add_parser("show")
    show.add_argument("id")
    listing = operations.add_parser("list")
    listing.add_argument("query", nargs="?", default="")
    verify = commands.add_parser("verify", help="Run or import task checks independently of architecture approval")
    operations = verify.add_subparsers(dest="operation", required=True)
    running = operations.add_parser("run")
    source = running.add_mutually_exclusive_group(required=True)
    source.add_argument("--command", dest="command_json", help='JSON argument vector, e.g. ["python3", "-m", "unittest"]')
    source.add_argument("--check", help="Existing model verification ID")
    running.add_argument("--task", required=True)
    running.add_argument("--paths", nargs="+", default=[], help="Input paths/globs; default is the bounded source inventory")
    running.add_argument("--cwd", default=None)
    running.add_argument("--timeout", type=int, default=None)
    running.add_argument("--environment", default="local")
    importing = operations.add_parser("import", help="Retain a harness-produced archctl.execution.v1 result")
    importing.add_argument("--input", required=True, type=Path)


def _optional_model(root: Path, directory: str) -> tuple[Snapshot | None, list[str]]:
    try:
        if has_authoring_model(contained(root, directory)):
            return compile_model(root, directory), []
    except InputError as exc:
        return None, [f"Optional architecture model is invalid; context uses provisional bindings: {exc}"]
    return None, []


def _mapping_snapshot(bindings) -> Snapshot:
    # An ephemeral binding projection for the existing evidence parser, never written as approved intent.
    model = Model("context", "Provisional context bindings", (Domain("context", "Context", ()),),
        tuple(Component(b.id, b.purpose or b.id, "context", "library", b.paths) for b in bindings),
        (), (), (), (), (), (), "selective")
    return Snapshot(digest(model.to_dict()), model, ())


def context(root: Path, args, *, paths: list[str]) -> dict:
    string(args.task, "task")
    if not 1 <= args.limit <= 50:
        raise InputError("context --limit must be between 1 and 50")
    paths = sorted({relative_path(p, "context path") for p in paths})
    for path in paths:
        contained(root, path)
    snapshot, gaps = _optional_model(root, args.model_dir)
    files, truncated = inventory(root)
    bindings, mapping_gaps = load_bindings(root, snapshot, files, paths)
    gaps.extend(mapping_gaps)
    if truncated:
        gaps.append("Source inventory is truncated at 4000 files; undiscovered components remain possible")
    mapping = _mapping_snapshot(bindings)
    observations, stale = None, []
    evidence_path = args.evidence or Path(".archctl/evidence.json")
    evidence_path = evidence_path.resolve() if evidence_path.is_absolute() else contained(root, evidence_path.as_posix())
    if args.refresh_evidence:
        if args.evidence:
            raise InputError("Choose --evidence or --refresh-evidence")
        # Reuse verified public operations from the native mapper. No invented session API.
        try:
            import os
            binary = args.briefcase or os.environ.get("BRIEFCASE_BIN") or "briefcase"
            bundle = export_evidence(root, mapping, binary=binary, source_roots=tuple(args.source_root))
            observations = parse_evidence(bundle, mapping)
        except (InputError, OSError) as exc:
            gaps.append(f"Briefcase refresh unavailable: {exc}")
    elif evidence_path.is_file():
        try:
            observations = parse_evidence(load_document(evidence_path), mapping)
        except InputError as exc:
            if args.evidence:
                raise
            gaps.append(f"Optional default evidence is invalid: {exc}")
    elif args.evidence:
        raise InputError(f"Evidence file does not exist: {evidence_path}")
    if observations:
        stale = [f.message for f in check_freshness(root, mapping, observations)]
    memories = read_memories(root)
    packet = build_context(root, args.task, paths, bindings, files, memories, snapshot=snapshot,
        observations=observations, evidence_gaps=gaps, stale_evidence=stale,
        dependencies=args.dependency, context_refs=args.reference,
        decision_notes=decision_notes(root, args.model_dir) if not snapshot else [], limit=args.limit)
    # Results are selected by task or overlapping source scope, never treated as approval.
    results = []
    for record in read_executions(root):
        if terms(args.task) & terms(record["task"]) or set(paths) & record["source"]["files"].keys():
            results.append({**record, "applicability": execution_freshness(root, record)})
    results.sort(key=lambda r: (r["started_at"], r["id"]), reverse=True)
    packet["executions"] = results[:args.limit]
    packet["totals"]["executions"] = len(results)
    # The packet hash includes results selected after pure context composition.
    packet.pop("revision")
    packet["revision"] = digest(packet)
    return packet


def dispatch(root: Path, args, paths: list[str] | None = None) -> int:
    if not root.is_dir():
        raise InputError(f"Repository root is not a directory: {root}")
    if args.command == "context":
        packet = context(root, args, paths=paths or [])
        value = markdown(packet) if args.format == "markdown" else packet
        if args.out:
            path = args.out.resolve() if args.out.is_absolute() else contained(root, args.out.as_posix())
            base = contained(root, ".archctl")
            if not path.is_relative_to(base) or path == base or path.exists():
                raise InputError("Context output must be a new file under .archctl/")
            if isinstance(value, str):
                write_text(path, value)
            else:
                write_json(path, value)
            print(json.dumps({"schema_version": "archctl.output.v2", "status": "assembled", "output": str(path)}))
        else:
            print(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False))
        return 0  # Successful assembly says nothing about correctness or permission.
    if args.command == "memory":
        if args.operation == "record":
            path = args.input.resolve() if args.input.is_absolute() else contained(root, args.input.as_posix())
            record = remember(root, load_document(path))
            print(json.dumps({"schema_version": "archctl.memory-recorded.v1", "status": "recorded",
                "id": record.id, "revision": record.to_dict()["revision"],
                "path": f"architecture/memory/{record.id}.json"}))
        else:
            records = read_memories(root)
            if args.operation == "show":
                records = tuple(r for r in records if r.id == args.id)
                if not records:
                    raise InputError(f"Unknown memory: {args.id}")
            query = terms(getattr(args, "query", ""))
            result = [{**r.to_dict(), "freshness": freshness(root, r)} for r in records if not query or
                      query & terms(r.statement + " " + r.rationale + " " + " ".join(r.topics))]
            print(json.dumps({"schema_version": "archctl.memories.v1", "records": result}, indent=2))
        return 0
    if args.operation == "run":
        if args.check:
            snapshot = compile_model(root, args.model_dir)
            selected = next((v for v in snapshot.model.verification if v.id == args.check), None)
            if not selected:
                raise InputError(f"Unknown verification target: {args.check}")
            command = list(selected.command)
            cwd = args.cwd if args.cwd is not None else selected.cwd
            timeout = args.timeout if args.timeout is not None else selected.timeout_seconds
        else:
            try:
                command = json.loads(args.command_json)
            except json.JSONDecodeError as exc:
                raise InputError("verify --command requires a JSON argument vector") from exc
            if not isinstance(command, list) or not command or any(not isinstance(a, str) or not a for a in command):
                raise InputError("verify --command requires a nonempty JSON argument vector")
            cwd = args.cwd if args.cwd is not None else "."
            timeout = args.timeout if args.timeout is not None else 60
        record = run(root, command, task=args.task, paths=args.paths, cwd=cwd,
                     timeout_seconds=timeout, environment=args.environment)
    else:
        path = args.input.resolve() if args.input.is_absolute() else contained(root, args.input.as_posix())
        record = parse_execution(load_document(path))
        # Preserve bytes and origin of imported results; don't promote a harness result to local execution.
    output = save_execution(root, record)
    result = {**record, "applicability": execution_freshness(root, record), "record_path": str(output)}
    print(json.dumps(result, indent=2))
    if record["result"]["status"] == "failed":
        return 1
    return 0 if record["result"]["status"] == "passed" and result["applicability"]["status"] == "current" else 2
