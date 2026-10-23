# Working on Archclt

For architecture changes, use [the bundled skill](skills/architecture-control/SKILL.md).
Read ARCHITECTURE.md and relevant architecture/decisions/ ADRs before crossing
module boundaries. Source investigation uses Briefcase when available and direct
inspection; preserve evidence gaps.

- Core is independent of features. Atlas never imports Guard. Guard and Observatory
  share the process adapter. CLI composes features. Intent and observations stay
  distinct types; observations never approve decisions.
- Use reviewed ARCHCTL_BIN and BRIEFCASE_BIN installations outside candidate
  checkouts. Installation and release provenance are in docs/install.md and
  docs/releasing.md. Candidate tools are test subjects, never independent evidence
  producers or evaluators for their own acceptance.
- Gate against the full SHA resolved from archctl-baseline with a scoped
  .archctl/change.yaml and --run. Baseline changes affecting authority, ownership,
  ADRs or commands require operator review. Keep local run records under .archctl/.
- Validate with PYTHONPATH=src python3 -m unittest discover -s tests -v and
  PYTHONPATH=src python3 scripts/demo.py. Release with python3 scripts/validate.py.
  Native Briefcase skips remain visible; unknown, partial and unexecuted never
  mean passed. npm packaging also runs npm test.
- One v2 exchange family lives in contracts/v2. Strict enforcement is the default;
  advisory obligations require explicit intent. Use model migrate for legacy models.
- Out of scope: hosted governance, new policy kinds, graph UI, MCP, non-Python
  mapping, tracing and placeholder implementations.
