from __future__ import annotations

from archctl.core.models import Snapshot
from archctl.core.text import markdown_cell


def markdown(snapshot: Snapshot, reconciliation: dict) -> str:
    lines = [f"# {markdown_cell(snapshot.model.name)} architecture", "",
             f"Model revision: `{snapshot.revision}`", "",
             f"Observed source: `{markdown_cell(reconciliation['source_revision'])}`", "",
             "## Components", "", "| Component | Domain | Kind | Owners |", "|---|---|---|---|"]
    owners = {d.id: ", ".join(d.owners) for d in snapshot.model.domains}
    for c in snapshot.model.components:
        lines.append(f"| {markdown_cell(c.id)} | {markdown_cell(c.domain)} | {c.kind} | {markdown_cell(owners[c.domain])} |")
    lines += ["", "## Decisions", "", "| Decision | Status | Title |", "|---|---|---|"]
    for d in snapshot.model.decisions:
        lines.append(f"| {markdown_cell(d.id)} | {d.status} | {markdown_cell(d.title)} |")
    lines += ["", "## Reconciliation", "", "| Finding | Status | Decision | Detail |", "|---|---|---|---|"]
    for f in reconciliation["findings"]:
        lines.append(f"| {markdown_cell(f['id'])} | {f['status']} ({f.get('obligation', 'legacy')}) | {markdown_cell(f['decision'])} | {markdown_cell(f['message'])} |")
    ignored = reconciliation.get("ignored") or []
    if ignored:
        lines += ["", "### Ignored intra-component observations", "",
                  "| Source | Target | Kind | Reason |", "|---|---|---|---|"]
        for item in ignored:
            lines.append(f"| {markdown_cell(item['source'])} | {markdown_cell(item['target'])} | {markdown_cell(item['kind'])} | {markdown_cell(item['reason'])} |")
    lines += ["", "Observations do not approve or modify architectural intent.", ""]
    return "\n".join(lines)
