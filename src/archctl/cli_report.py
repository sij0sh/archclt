"""The composite local result and its reviewable Markdown representation."""

from __future__ import annotations

from archctl.core.text import markdown_cell


def overall_status(*states: str) -> str:
    if "error" in states:
        return "error"
    if "failed" in states:
        return "failed"
    return "passed" if states and all(s == "passed" for s in states) else "unknown"


def markdown(summary: dict) -> str:
    def reasons(item: dict) -> str:
        return ", ".join(f"{reason['id']} ({reason.get('obligation', 'required')})"
                         for reason in item.get("required_by", []))

    lines = [f"# Architecture change review: {summary['status']}", "",
             "| Check | Result |", "|---|---|",
             *[f"| {markdown_cell(k)} | {markdown_cell(v)} |" for k, v in summary.get("stages", {}).items()], "",
             f"Baseline: `{summary.get('baseline_sha', 'unknown')}`",
             f"Evaluator: `{markdown_cell(summary.get('evaluator', {}).get('source', 'unknown'))}`",
             f"Evaluator digest: `{summary.get('evaluator', {}).get('digest', 'unknown')}`",
             f"Candidate model: `{summary.get('model_revision', 'unknown')}`",
             f"Source: `{summary.get('source_revision', 'unknown')}` / `{summary.get('source_digest', 'unknown')}`",
             f"Change contract: `{summary.get('change_revision', 'not supplied')}`"]
    if summary.get("enforcement"):
        lines += [f"Enforcement: `{markdown_cell(summary['enforcement'])}`", "",
                  markdown_cell(summary.get("guarantee", ""))]
    if summary.get("support"):
        lines += ["", "Support: " + markdown_cell(summary["support"]["limitation"])]
    lines += ["", "## Acceptance checks", ""]
    if summary.get("acceptance"):
        lines += ["| Criterion | Status | Checks |", "|---|---|---|"]
        for item in summary["acceptance"]:
            lines.append(f"| {markdown_cell(item['id'])}: {markdown_cell(item['requirement'])} | {item['status']} | {markdown_cell(', '.join(item['checks']))} |")
    else:
        lines += ["Task acceptance: not assessed (no Change Contract supplied)."]
    lines += ["", "## Verification", "", "| Check | Obligation | Status | Command | Required by |",
              "|---|---|---|---|---|"]
    for item in summary.get("verification", []):
        lines.append(f"| {markdown_cell(item['id'])} | {markdown_cell(item.get('obligation', 'required'))} | {item['status']} "
                     f"| {markdown_cell(' '.join(item['command']))} | {markdown_cell(reasons(item))} |")
    lines += ["", "## Findings", ""]
    for finding in summary.get("findings", []):
        lines.append(f"- {markdown_cell(finding['status'])}"
                     + (f" ({markdown_cell(finding['obligation'])})" if finding.get('obligation') else "")
                     + f": {markdown_cell(finding['message'])}"
                     + (f" (decision: {markdown_cell(finding['decision'])})" if finding.get("decision") else "")
                     + (f" (evidence: {markdown_cell(', '.join(finding['evidence_refs']))})" if finding.get("evidence_refs") else ""))
    if summary.get("error"):
        lines += [f"- {markdown_cell(summary['error'])}"]
    lines += ["", "## Review", "", "Operator acceptance: not assessed.",
              "The selected Git SHA and contract digest identify inputs; they do not authenticate approval.",
              "Passing checks verify the mapped commands, not the completeness of natural-language requirements.",
              "Detailed inputs, command output and findings are retained in this run directory."]
    return "\n".join(lines) + "\n"
