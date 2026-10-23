# Bootstrap or adopt architecture

Use for deliberate adoption, not every model-free question.
For read-only investigation, use [evidence](evidence.md).
Establish a reviewed installation and producer outside candidate source before
executing project commands. Follow the repository's install guide, or
[installation](install.md). Set `ARCHCTL_BIN` to
the reviewed executable and never install archctl in the application's `.venv`.

## 1. Look

Run `"$ARCHCTL_BIN" status --format json` and inspect the live tree: build files, tests,
CI, existing ADRs and recent commit history.
Use Briefcase for observed structure.
Read recent history first; the paths that keep changing are the first model.

| Shape | What you see | Where the model starts |
|---|---|---|
| Greenfield | Little code; intent is ahead of implementation | The first real change and its owners |
| Brownfield | Behavior exists; intent is mostly implicit | Recent churn, known pain and real owners |
| Partial | Some docs or ADRs; no enforceable model | The documented decisions you can verify against code |

Answer every question the repository already answers.
Continue when you can name the candidate boundaries and their owners, and the
questions that only the operator can answer.

## 2. Propose

Run `"$ARCHCTL_BIN" init` when architecture intent is absent.
It writes a neutral, empty, unreviewed scaffold and refuses to overwrite files.
Use `init --demo` only for the executable Storefront example.

Write one proposal table before populating the model:

| Component | Paths | Owner | Basis | Confidence | Proposed obligations |
|---|---|---|---|---|---|
| `orders` | `src/orders/**` | `commerce-team` | Briefcase and `CODEOWNERS` | observed | optional `orders-payments`; forbid `orders-ledger` |

- Derive components and ownership from Briefcase and repository evidence.
- Use the project's words. Invent neither names nor teams.
- Propose the minimum model: components, relevant relationships, accepted
  decisions, constraints and verification commands you have run.
- Mark each row `observed`, `inferred` or `open`.
- When a boundary choice is contested or expensive to undo, present two
  decompositions and their trade-offs, then recommend one.

Greenfield and brownfield take different starting points:

| Decision | Greenfield | Brownfield |
|---|---|---|
| What gets frozen | not applicable | accepted existing edges as optional relationships |
| What gets prohibited | one or two directions with real cost | seams where the cost is already visible |
| First verification | the first test you actually run | the workflow that already has tests |
| First ADR | a hard-to-reverse choice | the answer a reviewer would re-litigate |
| First model | enough for the first change | enough for the next change, plus a replay match |

Continue when every proposed component has a path, an owner and a basis, and
the minimum model is small enough to review.

## 3. Ask

Ask one batched set of material questions, with facts first, options second and
your recommendation third.
Follow [intake](intake.md#stop-and-ask) for the triggers and the cost of guessing.
Derive owners, rules and commands from evidence or the operator.
Existing explicit authorization applies; do not ask for the same approval twice.

Continue when the operator has answered or explicitly deferred every material
question, and each answer is recorded in the draft model or an ADR.

## 4. Prove

Run the replay check against one to three recent reviewed changes:

1. List their changed paths, expected components, expected consumers and expected checks.
2. Run `impact` with current evidence and those paths.
3. Compare. Change the model, not the history.

Run one negative check in a disposable copy: add the import or behavior one
declared constraint forbids, confirm the expected failure, then discard the copy.
A self-supplied snapshot proves the rule fires; it does not approve the model.

Continue when the replay matches and at least one declared constraint fails
when violated.

## 5. Establish

Validate the model and inspect the compiled snapshot.
The operator reviews the concrete files and commits or accepts the commit.
Tag the full SHA the operator names: `git tag archctl-baseline <sha>`.
Export evidence and begin the [governed change workflow](change.md).

Bootstrap is complete when `status` reports ready with real ownership and
verification, the reviewed model is committed or accepted, and the operator has
selected the full baseline SHA.

## Enforcement start point

Choose with the operator:

| Repository shape | Starting point | Reason |
|---|---|---|
| Small, stable edge set | strict | A complete permission map is affordable and strongest |
| Large or volatile edge set | selective | Undeclared, unprohibited edges stay advisory |
| Uncertain, or low review capacity | ownership plus one workflow | Create only rules the team can review |

Selective enforcement is an explicit semantic choice.
The operator chooses it; strict remains the default until a reviewed model changes it.

## Limits

Limit automatic structural claims to supported Python import evidence.
Keep unsupported dependencies and global coverage gaps explicit.
Other projects can use declarations and test commands without claiming complete
enforcement.

For another app, use a reviewed archctl installation outside candidate source.
For the tool's first gate upgrade, a pre-gate baseline cannot supply the evaluator.
Present unit tests, demo, schema checks and package smoke for review, then
establish a baseline containing the new tool.
Never conceal this bootstrap as independent approval.
