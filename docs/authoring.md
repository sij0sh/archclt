# Authoring architectural intent

This guide describes the optional governed v2 model. Default development can
use [context and architectural memory](context.md) without authoring or adopting
it. `architecture/context.yaml` is an independent advisory binding file and is
excluded from the compiler's governed authoring inputs. The global
`--model-dir` option moves the governed model and ADRs only; advisory bindings
and memory stay under `architecture/`.

## Identity and files

Put the whole model in `architecture/model.yaml`: `schema_version: archctl.authoring.v2`, `system_id`, `name`, `domains`, and any of the sections `components`, `interfaces`, `relationships`, `policies`, `verification` and `workflows`. ADRs stay in `architecture/decisions/*.md`. `archctl init` writes this layout. The unified v2 format defaults to `enforcement: strict`; policies declare `obligation: required` or `advisory`. Each domain needs an ID, name and at least one owner.

The older split layout still compiles: `system.yaml` holds the system fields and each other section file holds one key matching its filename, such as `components: [...]` in `components.yaml`. A model file cannot be combined with split files. Either layout compiles to the same normalized model, so moving between them is not an authority change.

IDs are case-sensitive, start with a letter, and contain letters, digits, `_`, `.`, or `-`. They are stable within their typed namespace. References are checked in the corresponding namespace. Names and path layout can change without changing identity. Named entity collections are sorted before snapshot serialization.

The compiler accepts `.yaml`, `.yml`, or `.json`. Do not provide two formats for the same section. Files with unknown section names and unknown object fields are rejected. Optional absent sections are empty. The system fields are required.

## Components and paths

```yaml
components:
  - id: orders
    name: Orders
    domain: commerce
    kind: service
    paths: ["src/orders/**"]
```

Supported component kinds: `service`, `library`, `database`, `queue`, `external`, `ui`. These are descriptive; a `database` kind alone does not imply a prohibition. File-bound components are the reconciliation unit. A component with no actual files cannot support complete static coverage.

Paths use repository-relative POSIX globs. `*` matches one segment and `**` spans segments. Absolute paths, `..`, non-normalized paths and symlink escapes are rejected. Source inventory and evidence pins share one exclusion policy: `.git`, `.archctl`, `.briefcase`, `__pycache__`, `.venv`, `venv`, `node_modules`, `target`, `dist`, `build`, `.pytest_cache`, hidden paths, `*.egg-info` and `architecture/memory/`. Use source-specific bindings, not a wildcard over an entire checkout. Overlapping bindings for a changed file create an explicit impact gap.

## Decisions

```markdown
---
id: ADR-012
title: Payment isolation
status: accepted
components: [orders, payments, ledger]
supersedes: []
---
# Payment isolation

## Decision
Only Payments may import the ledger.

## Rationale
Centralize idempotency and audit ownership.

## Alternatives
Direct caller access would distribute payment invariants.
```

An ADR needs front matter and a nonempty human body. Status is `proposed`, `accepted`, `deprecated`, `superseded`, or `rejected`. Only accepted/deprecated decisions govern current relationships, interfaces, workflows and policies. Deprecated decisions remain authoritative during migration.

When replacing ADR-012, mark it `superseded` and add its ID to the successor's `supersedes`. Update current model references to an active decision. A superseded decision requires exactly one active or superseded successor; cycles are rejected. Historical rationale is retained.

The status string is authoring metadata. Approval comes from the separately trusted snapshot. Guard does not accept a candidate merely because its new ADR says `accepted`.

## Relationships and interfaces

```yaml
relationships:
  - id: orders-payments
    source: orders
    target: payments
    kind: imports
    decision: ADR-012
    required: true
```

Kinds: `imports`, `calls`, `reads`, `writes`, `publishes`, `consumes`. These are direct component edges. A forbidden direct import does not automatically forbid every indirect path. Declare the architectural rule you actually intend.

`required: true` requires current evidence of that relationship. If it is absent within complete static coverage, Guard fails it; incomplete evidence remains unknown. Optional relationships describe permitted/expected structure without requiring that the edge always be observed.

Interfaces declare a `provider`, nonempty `consumers`, nonempty `verification` check IDs and a governing `decision`. They extend impact analysis and impose verification when a participant is affected. They do not imply an observed import or call edge.

## Policies

```yaml
policies:
  - id: payments-isolation
    kind: forbidden_dependency
    obligation: required
    decision: ADR-012
    severity: error
    source: orders
    target: ledger
    kinds: [imports, writes]

  - id: payment-contract-required
    kind: required_verification
    obligation: required
    decision: ADR-012
    severity: error
    components: [orders, payments]
    checks: [payment-contract]
```

List several targets for one source with `targets`. The compiler expands it to
one policy per target with the ID `<id>-<target>`, so this compiles exactly like
the separate policies:

```yaml
  - id: core-independent
    kind: forbidden_dependency
    obligation: required
    decision: ADR-001
    source: core
    targets: [atlas, guard, cli]   # core-independent-atlas, -guard, -cli
```

`guard check` with no scope checks every declared component. The composite `gate` checks policies that intersect the affected components, plus policies named in the Change Contract. If multiple kinds are selected, absence passes only when all have complete static coverage. Runtime edges can provide positive evidence of a violation; runtime sampling cannot prove absence.

## Obligation strength

All authoring and exchange contracts use v2. Every policy declares
`obligation: required` or `obligation: advisory`; severity is display metadata.
Required obligations dominate advisory ones for a shared check. Acceptance,
interface and workflow checks, freshness, trust, unresolved scope and global
coverage remain required. Advisory failures retain their actual result.

The default `enforcement: strict` keeps in-scope undeclared dependencies blocking.
An explicitly reviewed `enforcement: selective` makes undeclared observations
advisory. Both settings use the same schemas, types and reports.

## Migrating from v1

0.4.0 accepts only `archctl.authoring.v2`. If a repository still has v1 intent,
run this command with 0.3.0:

```bash
archctl model migrate --input architecture/model.yaml --out migrated-model.yaml
```

Review the result before replacing the original and selecting a new baseline.
The migration preserves old verification requirements and warning-only structural
policies. Legacy `selective-v2` becomes `selective`. The 0.4.0 CLI has no
`model migrate` command and rejects v1 intent instead of normalizing it. Legacy
snapshots, evidence and task contracts must be regenerated in the v2 format.

## Verification and workflows

```yaml
verification:
  - id: payment-contract
    kind: contract
    components: [orders, payments]
    command: [python3, -m, unittest, tests.test_payment_contract]
    cwd: .
    timeout_seconds: 30
```

Verification kinds: `contract`, `integration`, `workflow`, `architecture`. The command must be a nonempty list, with no implicit shell interpretation. The working directory must remain inside the repository. Timeouts are integers from 1 to 300 seconds. Executables resolve through the runner's environment, which should be pinned in CI.

Workflows have an ID, nonempty `participants`, nonempty `verification` references and a governing `decision`. Touching one participant expands impact to all declared participants and their checks. `observe run <workflow>` executes its declared checks against the matching trusted model. It makes no assertion that a test exercises every possible workflow path.

## Model changes

Follow the installed `architecture-control` skill's governed-change reference
for proposing, reviewing and baselining a model change. Its design reference
tests whether an obligation is worth declaring.
The schema rules above remain the authoring contract.

Do not update a baseline automatically because a gate failed.


## V1 recipes

Use existing mechanisms before proposing a new rule kind:

| Change | Model obligation | Verification |
|---|---|---|
| Component boundary | Component ownership, accepted ADR, permitted relationship or forbidden direct dependency | Fresh Python import evidence and dependency policy |
| Shared interface | Provider, declared consumers, accepted decision and verification IDs | Positive, negative and compatibility contract tests; impact includes observed consumers |
| Behavior | Change Contract acceptance criteria and existing required-verification policy/workflow | Success, failure and unchanged-behavior regression commands |

The skill's change reference lists the checks to choose for each kind of change.
New verification commands and enduring architectural constraints change authority;
review and baseline them before executing through Guard. The task contract may
reference approved checks but cannot redefine their commands. Test success
never creates observations or proves an assertion fully expresses user intent.

Default initialization now creates empty authoring lists with an unreviewed
application label. Populate real components and reviewed ownership before claiming
readiness. Use `init --demo` for Storefront only.
