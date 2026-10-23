"""Compose evidence and architectural reasons for an agent's current decision."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from archctl.core.context import Binding, terms
from archctl.core.contracts import version
from archctl.core.io import InputError, contained, digest, file_digest, matches
from archctl.core.memory import Memory, freshness as memory_freshness
from archctl.core.models import Observations, Snapshot, owners


def _score(task_terms: set[str], text: str) -> int:
    return len(task_terms & terms(text))


def _decision_rank(item: dict) -> int:
    if item["status"] == "superseded" or item["superseded_by"]:
        return 4
    return {"accepted": 0, "deprecated": 1, "proposed": 2, "rejected": 3}.get(item["status"], 2)


def _sort_decisions(items: list[dict]) -> None:
    # Score is primary; lifecycle breaks ties and demotes replaced records.
    items.sort(key=lambda item: item["id"], reverse=True)
    items.sort(key=lambda item: _decision_rank(item))
    items.sort(key=lambda item: -item["score"])


def _path_match(paths: list[str], patterns: tuple[str, ...]) -> bool:
    return any(matches(path, pattern) for path in paths for pattern in patterns)


def _route(edges: list[dict], start: str, end: str) -> list[dict] | None:
    queue = deque([(start, [])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        if node == end:
            return path
        for edge in edges:
            if edge["source"] == node and edge["target"] not in visited:
                visited.add(edge["target"])
                queue.append((edge["target"], path + [edge]))
    return None


def _snippets(root: Path, files: list[str], paths: list[str], task_terms: set[str],
              bindings: list[Binding], focus: set[str], limit: int) -> tuple[list[dict], dict]:
    ranked = []
    candidates = sorted(files, key=lambda p: (p not in paths, not (set(owners(p, bindings)) & focus), p))
    read = 0
    for path in candidates[:400]:
        # Memory is retrieved separately, never counted as fresh source evidence.
        if path.startswith("architecture/memory/"):
            continue
        file = contained(root, path)
        try:
            pin = file_digest(file)
            with file.open("rb") as stream:
                raw = stream.read(32769)
            text = raw[:32768].decode("utf-8")
            if file_digest(file) != pin:
                continue  # Never attach a newer file identity to an older excerpt.
        except (OSError, UnicodeError):
            continue
        read += 1
        score = _score(task_terms, path + " " + text) + (12 if path in paths else 0)
        if not score:
            continue
        lines = text.splitlines()
        line_scores = [_score(task_terms, line) for line in lines]
        best = max(range(len(lines)), key=lambda i: line_scores[i]) if lines else 0
        start = max(0, best - 2)
        excerpt = "\n".join(lines[start:start + 12])[:1600]
        ranked.append((score, path, {"path": path, "start_line": start + 1, "excerpt": excerpt,
            "origin": "source", "sha256": pin, "score": score,
            "components": owners(path, bindings), "file_excerpt_truncated": len(raw) > 32768,
            "meaning": "Retrieval candidate; read implementation and callers before inferring suitability"}))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in ranked[:limit]], {
        "files_considered": len(candidates), "files_read": read,
        "search_truncated": len(candidates) > 400, "matches": len(ranked),
        "returned": min(limit, len(ranked)), "retrieval": "lexical; interpretation belongs to the coding agent"}


def build_context(root: Path, task: str, paths: list[str], bindings: list[Binding],
                  files: list[str], memories: tuple[Memory, ...], *, snapshot: Snapshot | None = None,
                  observations: Observations | None = None, evidence_gaps: list[str] | None = None,
                  stale_evidence: list[str] | None = None, dependencies: list[list[str]] | None = None,
                  context_refs: list[str] | None = None, decision_notes: list[dict] | None = None,
                  limit: int = 8) -> dict:
    paths = sorted(set(paths))
    query = terms(task)
    gaps = [{"category": "evidence", "affects": ["dependency conclusions"], "message": g}
            for g in evidence_gaps or []]
    stale_evidence = stale_evidence or []
    aliases = {a: b.id for b in bindings for a in (b.id, *b.aliases)}
    def identity(value: str) -> str:
        if value in aliases:
            return aliases[value]
        mapped = owners(value, bindings)
        if len(mapped) == 1:
            return mapped[0]
        raise InputError(f"Dependency endpoint has no unique component: {value}; use --paths or context.yaml")
    proposals = [(identity(source), identity(target)) for source, target in (dependencies or [])]
    focus = {owner for path in paths for owner in owners(path, bindings)} | {s for pair in proposals for s in pair}
    for binding in bindings:
        if _score(query, binding.id + " " + binding.purpose + " " + " ".join(binding.paths)):
            focus.add(binding.id)
    if not focus:
        gaps.append({"category": "scope", "affects": ["impact"],
                     "message": "No concrete component scope; task terms and source candidates guide investigation"})
    for path in paths:
        if not contained(root, path).exists():
            gaps.append({"category": "planned", "affects": [path],
                         "message": f"Planned or deleted path has no current source: {path}"})
    edges = []
    evidence = []
    if observations:
        normalized = observations.to_dict()
        evidence = normalized["evidence"]
        edges = [e for e in normalized["edges"] if e["source"] != e["target"]]
        for message in observations.coverage.gaps:
            gaps.append({"category": "coverage", "affects": ["unlocalized dependency coverage"], "message": message})
        if observations.coverage.status != "complete" or observations.coverage.analysis != "static":
            gaps.append({"category": "coverage", "affects": ["absence of additional consumers"],
                         "message": "Evidence is partial or runtime-only; undiscovered dependencies remain possible"})
    else:
        gaps.append({"category": "evidence", "affects": ["dependency conclusions"],
                     "message": "No normalized Briefcase evidence supplied; no source dependency graph was inferred"})
    for message in stale_evidence:
        gaps.append({"category": "freshness", "affects": ["observed edges"], "message": message})
    # Build one shortest explanatory path for each potential consumer.
    affected = {c: {"id": c, "basis": "task_scope", "path": [], "edit_required": False} for c in focus}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge["target"] in affected and edge["source"] not in affected:
                affected[edge["source"]] = {"id": edge["source"], "basis": "possible_consumer",
                    "path": [edge] + affected[edge["target"]]["path"], "edit_required": False}
                changed = True
        if snapshot:
            for interface in snapshot.model.interfaces:
                if interface.provider in affected:
                    for c in interface.consumers:
                        if c not in affected:
                            affected[c] = {"id": c, "basis": "declared_interface_consumer", "path": [], "edit_required": False}
                            changed = True
            for workflow in snapshot.model.workflows:
                if set(workflow.participants) & affected.keys():
                    for c in workflow.participants:
                        if c not in affected:
                            affected[c] = {"id": c, "basis": "declared_workflow_participant", "path": [], "edit_required": False}
                            changed = True
    active_scope = set(affected)
    if observations:
        missing = active_scope - set(observations.coverage.components)
        if missing:
            gaps.append({"category": "coverage", "affects": sorted(missing),
                         "message": "These task components lack declared dependency analysis coverage"})
    successors: dict[str, list[str]] = {}
    for record in memories:
        for old in record.supersedes:
            successors.setdefault(old, []).append(record.id)
    successors = {key: sorted(set(value)) for key, value in successors.items()}
    def successor_values(record_id: str) -> tuple[str | None, list[str]]:
        values = successors.get(record_id, [])
        return (values[0] if values else None), values
    ranked = []
    for record in memories:
        components = {aliases.get(c, c) for c in record.components}
        lexical = _score(query, " ".join((record.statement, record.rationale, *record.topics, *record.assumptions)))
        score = lexical + (8 if components & active_scope else 0) + (12 if _path_match(paths, record.paths) else 0)
        if not score:
            continue
        value = record.to_dict()
        primary, ids = successor_values(record.id)
        value.update(score=score, freshness=memory_freshness(root, record),
                     superseded_by=primary, superseded_by_ids=ids, relevance="lexical_and_scope")
        ranked.append((score, record.id, value))
    selected_ids = {row[1] for row in ranked}
    # Contradicting and replacement context travels with a match, not only on lexical coincidence.
    for record in memories:
        if record.id not in selected_ids and (set(record.contradicts) & selected_ids or set(record.supersedes) & selected_ids
                or any(record.id in {*r.contradicts, *r.supersedes} for r in memories if r.id in selected_ids)):
            value = record.to_dict()
            primary, ids = successor_values(record.id)
            value.update(score=0, freshness=memory_freshness(root, record),
                         superseded_by=primary, superseded_by_ids=ids, relevance="related_record")
            ranked.append((0, record.id, value))
    ranked.sort(key=lambda row: (row[2]["superseded_by"] is not None, -row[0], row[1]))
    memory_items = [row[2] for row in ranked[:limit]]
    for item in memory_items:
        item["excerpt_truncated"] = len(item["rationale"]) > 2000
        item["rationale"] = item["rationale"][:2000]
    concerns = []
    for item in memory_items:
        if item["freshness"]["status"] == "stale":
            concerns.append({"kind": "stale_reasoning", "references": [item["id"]],
                             "message": "Implementation inputs changed; reassess applicability before using this rationale"})
        if item["contradicts"]:
            concerns.append({"kind": "conflicting_reasoning", "references": [item["id"], *item["contradicts"]],
                             "message": "Preserve both accounts and resolve their assumptions in the current task"})
    decision_successors: dict[str, list[str]] = {}
    for decision in (snapshot.model.decisions if snapshot else decision_notes or []):
        if isinstance(decision, dict):
            ident, supersedes = decision["id"], decision.get("supersedes", [])
        else:
            ident, supersedes = decision.id, decision.supersedes
        for old in supersedes:
            decision_successors.setdefault(old, []).append(ident)
    decision_successors = {key: sorted(set(value)) for key, value in decision_successors.items()}
    decisions, checks = [], []
    if not snapshot:
        for decision in decision_notes or []:
            score = _score(query, decision["title"] + " " + decision["body"])
            if score or set(decision["components"]) & active_scope:
                decisions.append({"id": decision["id"], "status": decision["status"], "path": decision["path"],
                    "rationale_excerpt": decision["body"][:3000], "excerpt_truncated": len(decision["body"]) > 3000,
                    "origin": "declared", "score": score,
                    "supersedes": list(decision.get("supersedes", [])),
                    "superseded_by": decision_successors.get(decision["id"], [])})
        _sort_decisions(decisions)
    if snapshot:
        for decision in snapshot.model.decisions:
            score = _score(query, decision.title + " " + decision.body)
            if score or set(decision.components) & active_scope:
                decisions.append({"id": decision.id, "status": decision.status, "path": decision.path,
                    "rationale_excerpt": decision.body[:3000], "excerpt_truncated": len(decision.body) > 3000,
                    "origin": "declared", "score": score,
                    "supersedes": list(decision.supersedes),
                    "superseded_by": decision_successors.get(decision.id, [])})
        _sort_decisions(decisions)
        for check in snapshot.model.verification:
            if set(check.components) & active_scope or _score(query, check.id):
                checks.append({"id": check.id, "command": list(check.command), "cwd": check.cwd,
                    "timeout_seconds": check.timeout_seconds, "basis": "existing_model_check", "status": "not_executed"})
        for policy in snapshot.model.policies:
            violations = [e for e in edges if e["source"] == policy.source and e["target"] == policy.target and e["kind"] in policy.kinds]
            if policy.kind == "forbidden_dependency" and violations and {policy.source, policy.target} & active_scope:
                concerns.append({"kind": "declared_constraint", "references": [policy.id, policy.decision],
                    "message": f"Observed dependency contradicts {policy.id}",
                    "evidence_refs": sorted({r for e in violations for r in e["evidence_refs"]}),
                    "freshness": "stale" if stale_evidence else "current"})
    if len(decisions) > limit:
        gaps.append({"category": "scope", "affects": ["decisions"],
                     "message": f"Decision retrieval returned {limit} of {len(decisions)} matching decisions; raise --limit or inspect the full decision inventory"})
    hypothetical = []
    for source, target in proposals:
        imports = [e for e in edges if e["kind"] == "imports"]
        path = _route(imports, target, source)
        policies = [p.id for p in snapshot.model.policies if p.kind == "forbidden_dependency"
                    and (p.source, p.target) == (source, target) and "imports" in p.kinds] if snapshot else []
        hypothetical.append({"source": source, "target": target, "kind": "imports", "origin": "hypothetical",
            "cycle": "within_component" if source == target else
                     "possible_from_stale_evidence" if path is not None and stale_evidence else
                     "supported_path" if path is not None else "not_observed",
            "return_path": path or [], "constraint_refs": policies,
            "meaning": "Proposed edge is not observed; absence of a return path does not prove acyclicity"})
    snippets, retrieval = _snippets(root, files, paths, query, bindings, focus, limit)
    binding_items = [b.to_dict() for b in bindings if b.id in active_scope]
    relevant_edges = [e for e in edges if {e["source"], e["target"]} & active_scope]
    refs = {ref for edge in relevant_edges[:limit] for ref in edge["evidence_refs"]}
    refs.update(ref for item in hypothetical for edge in item["return_path"] for ref in edge["evidence_refs"])
    refs.update(ref for item in list(affected.values())[:limit] for edge in item["path"] for ref in edge["evidence_refs"])
    packet = {"schema_version": version("context"), "status": "assembled", "task": task,
        "planned_paths": paths, "context_references": context_refs or [],
        "components": binding_items[:limit], "potential_impact": [affected[k] for k in sorted(affected)][:limit],
        "memories": memory_items, "decisions": decisions[:limit], "source_candidates": snippets,
        "observed_edges": relevant_edges[:limit], "evidence": [e for e in evidence if e["id"] in refs],
        "proposed_dependencies": hypothetical, "verification_suggestions": checks[:limit],
        "concerns": concerns, "limitations": gaps, "executions": [],
        "source": {"model_revision": snapshot.revision if snapshot else None,
                   "evidence_revision": observations.source_revision if observations else None,
                   "evidence_freshness": "stale" if stale_evidence else "current" if observations else "unavailable"},
        "retrieval": retrieval,
        "totals": {"components": len(binding_items), "potential_impact": len(affected), "memories": len(ranked),
                   "decisions": len(decisions), "observed_edges": len(relevant_edges),
                   "verification_suggestions": len(checks), "executions": 0},
        "decision_prompts": ["Which existing capability fits this task's lifecycle, state, and failure assumptions?",
            "Read the source and usage examples before choosing direct reuse, extraction, or local implementation.",
            "Check relevant behavior and resource limits; record reasons that would be costly to forget."],
        "meaning": "Advisory context for agent judgment; assembled is not an architectural or behavioral pass"}
    packet["revision"] = digest(packet)
    return packet


def markdown(packet: dict) -> str:
    lines = [f"# Architectural context: {packet['task']}", "", packet["meaning"], "",
             "## Components and possible impact", ""]
    lines += [f"- `{c['id']}` ({c['basis']}); no edit implied" for c in packet["potential_impact"]]
    lines += ["", "## Reasons and assumptions", ""]
    for m in packet["memories"]:
        lines += [f"### {m['id']} ({m['origin']}, {m['freshness']['status']})", "", m["statement"], "", m["rationale"], "",
                  "References: " + ", ".join(m["references"]), ""]
        successors = m.get("superseded_by_ids") or ([m["superseded_by"]] if m.get("superseded_by") else [])
        if successors:
            lines += ["Superseded by: " + ", ".join(successors), ""]
    for d in packet["decisions"]:
        lines += [f"### {d['id']} ({d['status']})", "", d["rationale_excerpt"], "", f"Source: `{d['path']}`", ""]
        if d.get("supersedes"):
            lines += ["Supersedes: " + ", ".join(d["supersedes"]), ""]
        if d.get("superseded_by"):
            lines += ["Superseded by: " + ", ".join(d["superseded_by"]), ""]
    lines += ["## Source candidates", ""]
    for s in packet["source_candidates"]:
        lines += [f"- `{s['path']}` from line {s['start_line']}; read source for full context.", ""]
    lines += ["## Proposed dependencies", ""]
    for d in packet["proposed_dependencies"]:
        lines += [f"- `{d['source']} -> {d['target']}`: {d['cycle']}; constraints: {', '.join(d['constraint_refs']) or 'none declared'}"]
    lines += ["", "## Checks and execution evidence", ""]
    lines += [f"- `{c['id']}`: suggested, not executed by context" for c in packet["verification_suggestions"]]
    lines += [f"- {e['task']}: {e['result']['status']}; applicability {e['applicability']['status']}" for e in packet["executions"]]
    lines += ["", "## Concerns and limitations", ""]
    lines += ["- " + item["message"] for item in packet["concerns"] + packet["limitations"]]
    lines += ["", "## Next decisions", ""] + ["- " + p for p in packet["decision_prompts"]]
    lines += ["", "Totals before packet limits: " + str(packet["totals"]), ""]
    return "\n".join(lines)
