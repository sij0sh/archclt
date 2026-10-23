# Governed change

## 1. Establish trust

Resolve repository tool pins and the baseline: `git rev-parse archctl-baseline`.
Use `ARCHCTL_BIN` and `BRIEFCASE_BIN`; never run the application's `.venv`
archctl. Without the tag, ask the operator for a reviewed full SHA and tag it.
For a baseline predating the evaluator, follow [adoption](adoption.md) before execution.
For new enduring rules or commands, follow [authoring](authoring.md).
Continue when the baseline SHA and tool provenance are recorded.

## 2. Establish impact

Inspect live Git state, including pre-existing work.
Use Briefcase's public read operations for task context; reuse relevant fresh evidence.
Read the model, governing ADRs, implementation and test assertions.
When the change alters a boundary, interface or obligation, read [design](design.md)
before recording it.
Run `"$ARCHCTL_BIN" status --format json`, then assess concrete planned paths with `impact`.
Resolve stale or insufficient inputs through [evidence](evidence.md) before relying on them.
Account for direct ownership, indirect consumers and workflow participants.

Choose checks by the change:

- **Ownership or imports.** Map paths to owners; read governing ADRs, permitted
  relationships and forbidden dependencies; prefer the approved interface over
  reaching into another component. Observed imports do not authorize new
  relationships, and import absence means something only within complete scope.
- **Provider/consumer contracts.** Compare declared and observed consumers,
  including indirect ones; exercise preserved inputs, outputs and errors with
  positive, negative and compatibility assertions, not import presence.
- **Observable behavior.** Read assertions, not test names; cover success,
  relevant failure and unchanged behavior; show a representative incorrect
  implementation fails. Reuse discovery commands that already run new tests.

Continue when planned paths and affected consumers are accounted for or explicitly unknown.
Resolve material unknowns before dependent implementation.

## 3. Record scope and acceptance

Write `.archctl/change.yaml` through [intake](intake.md), then run
`"$ARCHCTL_BIN" change validate --input .archctl/change.yaml`.
Begin implementation when scope fits existing authorization and material questions are resolved.

## 4. Implement

Make scoped edits and meaningful positive, negative and regression assertions.
Recheck the live diff, untracked files and affected consumers.
Return to intake when new findings materially change scope or behavior.
Finish when every actual edit fits the contract and every criterion maps to a reviewed check.

## 5. Verify and hand off

Follow [evidence](evidence.md) for fresh export or a supplied pinned bundle.
Run the composite gate:

```bash
"$ARCHCTL_BIN" gate --baseline-ref <full-reviewed-sha> --change .archctl/change.yaml --run
```

The gate compares every actual Git change since the baseline, including pre-existing work.
Review cumulative verification scope separately from permission to edit.
Review material scope expansion instead of widening the contract to clear a finding.
A changed-scope run with no delta is unknown; use `--scope all` for a deliberate baseline audit.

Run the gate with `--baseline-ref "$(git rev-parse archctl-baseline)"`.
Read the newly printed run directory and follow [review](review.md).
Without `--run`, required checks remain unexecuted.
