# Working on Archclt

For architecture changes, use [the bundled skill](skills/architecture-control/SKILL.md).
Read ARCHITECTURE.md and relevant architecture/decisions/ ADRs before crossing
module boundaries. Source investigation uses Briefcase when available and direct
inspection; preserve evidence gaps.

- Core is independent of features. Atlas never imports Guard. Guard and Observatory
  share the process adapter. CLI composes features. Intent and observations stay
  distinct types; observations never approve decisions.
- Default to `archctl context` before consequential changes. Use Briefcase for
  source evidence and retrieve full source when a candidate matters. Context,
  memories and ordinary `verify` commands require no model, baseline or approval.
- Record consequential reasoning with `memory record`, retaining origin and original
  references. Inferences never become user statements through repetition. Keep
  explicit conflicts and supersession history. Check actual behavior and resources.
- Use reviewed external tools and an independent baseline only for the optional
  governed `gate` workflow. Context-first changes use the existing task authorization.
  Keep run artifacts under .archctl/.
- Validate with PYTHONPATH=src python3 -m unittest discover -s tests -v and
  PYTHONPATH=src python3 scripts/demo.py. Release with python3 scripts/validate.py.
  Also run PYTHONPATH=src python3 scripts/demo_context.py for the default workflow.
  Native Briefcase skips remain visible; unknown, partial and unexecuted never
  mean passed. npm packaging also runs npm test.
- Preserve v2 gates in contracts/v2; advisory memory/context/execution contracts
  live in contracts/context/v2. Keep the core independent and Atlas free of execution.
- Out of scope: hosted governance, new policy kinds, graph UI, MCP, non-Python
  mapping, tracing and placeholder implementations.
