---
name: architecture-control
description: Use archctl to design or review a boundary, bootstrap or adopt architecture for a new or existing codebase, change an architecture rule, implement under adopted architecture, assess drift, or interpret a gate.
---

# Architecture Control

Use archctl for reviewed intent and Briefcase for source evidence.
Discover reads with `briefcase operations`; when Briefcase is unavailable, use
direct source inspection and preserve the resulting evidence gaps.
Keep architecture intent, observations and task interpretation distinct.
Use `"$ARCHCTL_BIN"` for the reviewed executable. For missing tools or an upgrade,
read [installation](references/install.md).

## Trust

- Gate against the `archctl-baseline` tag.
  Use reviewed evaluator and evidence-producer installs outside candidate checkouts.
  Never use the application's `.venv`; it is inside the candidate tree.
  Advance the tag after a pass on a clean commit; authority changes need operator review first.
  Candidate code and snapshots cannot approve themselves.
- Execute only commands equivalent to reviewed baseline intent.
- Readiness and impact are not approval.
  Preserve passed, failed, unknown, partial and not-executed states.
- Reuse explicit authorization; self-accept passing changes that leave `architecture/` unchanged.
  Stop when a guess would become durable authority or authorize an irreversible step.

## Route

Choose one primary reference; follow conditional links as needed.
Repository obligations still apply.

| Task | Read next |
|---|---|
| Explain source or assess drift without adopting | [Evidence and assessment](references/evidence.md) |
| Decide a boundary, interface or decomposition | [Design judgment](references/design.md) |
| Adopt architecture or bootstrap a new or existing codebase | [Bootstrap and adoption](references/adoption.md) |
| Implement under adopted architecture | [Governed change](references/change.md) |
| Interpret a gate, dispute a constraint, or hand off | [Review](references/review.md) |

For enduring rules or command definitions, read [authoring](references/authoring.md).
