# Author approved obligations

When deciding whether an obligation is worth declaring, read [design](design.md).

Use the existing model mechanisms:

| Obligation | Authoring |
|---|---|
| Ownership | Component paths and domain owners |
| Permitted dependency | Relationship tied to an active ADR |
| Prohibited dependency | `forbidden_dependency` policy with source, `target` or `targets`, and kinds |
| Required source relationship | Relationship with `required: true` |
| Required behavior | `required_verification` policy and reviewed verification IDs |
| Shared interface | Provider, consumers, contract-check IDs and ADR |
| Workflow | Participants, verification IDs and ADR |

Use `required: true` only when the relationship's continued presence is required.
A permitted dependency is not necessarily required to persist through a refactor.
Do not add declarations automatically to silence observed drift.

Put enduring authority in `architecture/model.yaml` and `architecture/decisions/`, not the task contract. Define
verification as argument vectors, cwd, component scope and bounded timeout.
Read and exercise the tests; a command that always succeeds is not verification.

Keep the proposal separate from approval. Explain the current constraint, why the
change is needed, affected consumers, new tests and remaining uncertainty. The
operator can authorize it in this session. Review the concrete files before
establishing the new baseline; the gate never promotes its own candidate model.
Do not weaken authority simply to remove a finding.

Every v2 model declares each policy `obligation` explicitly. `strict` is the default;
`selective` makes undeclared observations advisory only after explicit review.
Prefer `required` unless the constraint is genuinely advisory, keep acceptance,
interface and workflow verification required, and expect a review of any weaker
choice. `severity` is display metadata in v2 and never sets the obligation.

Run `"$ARCHCTL_BIN" model validate` after edits. Refresh evidence when source changes.
V1 excludes hosted governance, tracing, graph UI, new policy kinds, non-Python
mapping and specialized security/distributed-systems frameworks.
No GitHub or mandatory two-PR workflow is required.
[Change](change.md) lists the checks to choose for each kind of change.
