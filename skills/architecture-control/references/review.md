# Review and handoff

Read `gate-summary.json` and `gate-summary.md` in the just-printed run directory.
Use the composite outcome, not Guard alone or a prior successful report.
Check the model's `enforcement` and explicit policy `obligation`;
verification records its reasons in `required_by`. `strict` is the default.
Keep advisory findings visible without relabeling them as required failures.

## Diagnose before correcting

| Finding | Action |
|---|---|
| Implementation defect | Fix the violated behavior or dependency, then rerun. |
| Stale or incomplete evidence | Refresh supported analysis and retain known gaps. |
| Mistaken scope | Review the concrete expansion through [intake](intake.md). |
| Disputed intent or unreviewed command | Follow [authoring](authoring.md); establish authority outside the gate. |
| Optional missing relationship or unrelated drift | Preserve its informational classification. |

In-scope undeclared edges remain blocking under `strict` enforcement.
Review ownership and ADRs rather than automatically declaring observed edges.
A disputed rule stays binding until authorized revision.
Preserve the original finding and operator disposition.

## Hand off one result

Use the fresh gate summary as the primary record.
Report:

- Outcome and reviewed scope, including exclusions and indirect consumers.
- Baseline SHA, evaluator, model/source/contract identities and report path.
- Each acceptance criterion's actual verification result.
- Failed, unknown or unexecuted checks, coverage gaps and remaining assumptions.
- Concrete architecture/command changes or operator decisions still needed.

## Accept or escalate

Self-accept when the gate passed on a clean committed HEAD, the contract has no
open questions, and nothing under `architecture/` changed (a pass already means
compiled authority is unchanged). Then advance the baseline and record it:

```bash
git tag -f archctl-baseline HEAD
```

Escalate to the operator instead when the change edits policies, ADRs,
ownership or verification commands, or when a failed or unknown result cannot be
resolved without widening scope or weakening a rule. After the operator approves
an authority change, rerun the gate against the approved commit and advance the tag.
A passing change to the evaluator becomes the next evaluator; review evaluator
changes with that in mind.

Where the repository keeps a change record, write only `change.yaml`, the run's
`gate-summary.md` and a short README: baseline, per-criterion outcome,
disposition (`self-accepted` or the operator's words) and friction.

A pass covers mapped checks within reported scope and coverage.
An audit without a Change Contract makes no task-acceptance claim.
It does not establish complete user intent, adequate assertions, hidden dependencies or approval.
Rerun after source, scope or other pinned inputs change.

Share the run's `gate-summary.md` and retain adjacent `gate-summary.json` and
supporting artifacts. Use this one composite record for handoff.

Gate exits are 0 passed, 1 failed, 2 unknown and 3 input/evaluator error.
