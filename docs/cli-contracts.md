# CLI JSON and exit contracts

`archctl` is a local CLI. Agents should prefer JSON output and treat the exit code as the command outcome.

## Default context and verification commands

`context`, `memory` and `verify` use the advisory contracts under
`contracts/context/v2`; [the context guide](context.md) documents their input
formats. They require no baseline or approved model. Context exit 0 means
`assembled`, including useful packets with partial evidence. `memory record`
appends an immutable reason with provenance and returns `recorded`.

`verify run` uses an explicit JSON argument vector or existing model check ID.
`verify import` retains a supplied harness record. Actual execution outcome and
applicability to current source remain separate. Exit 0 means passed with current
recorded inputs, 1 failed execution, 2 unresolved outcome/applicability, and 3
invalid input. These outcomes make no architectural acceptance claim.

The conventions and baseline requirements below describe the optional v2 model
and gate workflow, whose contracts are preserved for compatibility.

## Conventions

- JSON is written to stdout. Errors are written to stderr as one `archctl.error.v2` object.
- Global options precede the command: `archctl [--root R] [--model-dir DIR] <command>`.
  `--model-dir` selects the governed model and ADRs; advisory `architecture/context.yaml`
  and `architecture/memory/` remain repository-level.
- Relative paths resolve against `--root`. Paths in JSON are repository-relative when they are inside the root.
- Every versioned object has a `schema_version`. All public contracts share one version.
  Within v2, archctl output may add fields; output consumers must ignore fields they
  do not recognize. Archctl input parsers are strict: unknown input fields are rejected
  so typos and unsupported extensions stay visible. Removing or renaming an output
  field, or changing its meaning, requires a new shared version.
- Every model emits `archctl.*.v2` objects. `enforcement: strict` is the default; `selective` changes undeclared-drift treatment without changing contract versions.
- `--out` writes the object atomically and prints an `archctl.output.v2` acknowledgement. Without `--out`, the object is printed to stdout.
- `status`, `model validate`, `decisions`, `impact` and read-only views do not approve architecture. `gate` is the composite local result for feature handoff; `guard check` remains a lower-level policy/test operation whose pass does not imply complete task verification.
- `unknown`, `not_executed`, `partial`, stale evidence and a missing baseline are never converted to `passed`.
- Examples use `"$ARCHCTL_BIN"` for the reviewed external install. `--briefcase`
  overrides `BRIEFCASE_BIN`, then defaults to `briefcase` on PATH. Preparation
  also accepts `ARCHCTL_BIN` as its default exporter. Verification inherits the
  caller's PATH; the isolated evaluator uses its own absolute Python interpreter.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The command completed with `ready` (status), `passed` (model or Guard), a complete impact, or a successful read-only query. |
| 1 | Guard found a failed policy or verification result. |
| 2 | The command completed with an unknown or incomplete state: `needs_model`, `needs_attention`, partial impact, stale/invalid evidence accepted for inspection, or Guard `unknown` / `not_executed`. |
| 3 | Invalid invocation, malformed or missing required input, invalid model for a command that requires one, or another input error. |
| 130 | Interrupted. |

`status` reports a broken model or evidence bundle as an ordinary state with exit code 2. It does not crash or hide the reason. A command that requires the model, such as `model validate` or `guard check`, reports the same problem as an input error with exit code 3.

## Obligation reports

The composite result preserves stage and exit semantics. It includes
`enforcement: strict|selective` and a `guarantee` sentence stating that required
obligations passed within reported scope and coverage. Verification results and
findings carry `obligation`, and verification reasons carry `required_by` so a
reviewer can see which requirement made a check blocking. Advisory failures are
retained in `findings` and in the drift diagnostics. They do not change a stage
to `passed` when the underlying check failed.

`impact.json` in v2 adds `unknown_details` with a category (`freshness`,
`coverage`, `scope` or `drift`). Category does not weaken the obligation;
freshness, scope and global coverage gaps stay required. `candidate.lock.json`
uses `archctl.snapshot.v2`, so an older evaluator rejects the candidate model as
unsupported instead of silently reading it as v1.

## briefcase prepare-evidence

```bash
"$ARCHCTL_BIN" --root R briefcase prepare-evidence \
  --archctl /absolute/reviewed/archctl --briefcase /absolute/reviewed/briefcase \
  --source-root src --out-dir .archctl/prepared/new-attempt
```

Both executable paths must be supplied by flags or `ARCHCTL_BIN` and
`BRIEFCASE_BIN`. At least one `--source-root` and a new `--out-dir` are required.
Inside the application, the output directory must be under `.archctl/`.
Exit 0 returns an `archctl.output.v2` acknowledgement with `status: written`,
`output` pointing to `evidence.json` and `manifest` pointing to `manifest.json`.
Preparation does not run verification or assess approval.
Invalid inputs, incomplete/mismatched evidence or failed tools exit 3 using the
existing JSON error contract. No failed attempt publishes `evidence.json`.
An existing output directory is left untouched.
See [the preparation boundary](briefcase-integration.md#scoped-evidence-preparation)
for source overlays, provenance, supported inputs and retained failure artifacts.

## status

```bash
"$ARCHCTL_BIN" --root R status --format json
"$ARCHCTL_BIN" --root R status --format json --evidence E
"$ARCHCTL_BIN" --root R status --format text
```

`--evidence` defaults to `.archctl/evidence.json`. The command is read-only except for `--out`.

`status` answers one question: **are the local inputs coherent enough to run impact analysis and Guard?** It does not run Guard, execute commands, compare a baseline, or approve intent.

| `status` | Meaning |
|---|---|
| `ready` | The model is valid and evidence is current, static, complete for every declared component and relationship kind, and has no freshness findings. |
| `needs_model` | No `architecture/model.*` or `system.*` file was found. Evidence was not checked. |
| `needs_attention` | The model is invalid, evidence is missing/invalid/stale/partial/runtime, the model has no components, or another declared gap remains. |

`ready` is not `passed`. The report always includes:

```json
{
  "gate": {"status": "not_executed", "reason": "..."},
  "approval": {"status": "not_assessed", "reason": "..."}
}
```

Shape:

```json
{
  "schema_version": "archctl.status.v2",
  "operation": "status",
  "root": "/absolute/repository/root",
  "status": "ready",
  "tool": {"name": "archctl", "version": "0.4.0"},
  "model": {
    "state": "valid",
    "directory": "architecture",
    "revision": "sha256",
    "system_id": "example",
    "name": "Example",
    "domains": 1,
    "components": 3,
    "decisions": {"total": 1, "active": 1, "by_status": {"accepted": 1}},
    "relationships": 2,
    "interfaces": 0,
    "policies": 1,
    "verification": 1,
    "workflows": 0,
    "sources": 4,
    "message": null
  },
  "evidence": {
    "state": "current",
    "path": ".archctl/evidence.json",
    "producer": {"name": "exporter", "version": "1"},
    "source_revision": "producer-revision",
    "source_digest": "sha256",
    "coverage": {
      "analysis": "static",
      "status": "complete",
      "components": 3,
      "relationship_kinds": ["imports"],
      "gaps": [],
      "gaps_total": 0,
      "gaps_truncated": false
    },
    "pins": 12,
    "evidence_items": 20,
    "edges": 4,
    "freshness": {"status": "passed", "total": 0, "returned": 0, "truncated": false, "findings": []},
    "message": null
  },
  "gate": {"status": "not_executed", "reason": "..."},
  "approval": {"status": "not_assessed", "reason": "..."},
  "unknowns": [],
  "unknowns_total": 0,
  "unknowns_truncated": false,
  "next_actions": ["..."]
}
```

`model.state` is `valid`, `missing` or `invalid`. A single `architecture/model.*` file and the older split `system.*` layout are both accepted; combining them is invalid. `evidence.state` is `not_checked`, `missing`, `invalid`, `stale`, `runtime`, `partial` or `current`. Counts are zero and nullable fields are `null` when the state is unavailable.

`evidence.freshness.status` is `passed` only when every evidence pin matches the current source and the component inventories have no new, missing or ambiguous files. Otherwise it is `unknown` or `not_executed`.

Collections are bounded to 20 items. `unknowns_total`, `coverage.gaps_total` and `freshness.total` preserve the untruncated counts. Check the matching `*_truncated` field before assuming the listed items are complete.

The `--format text` view is for people. Its wording is not a stable machine contract.

`status --drift` adds a repository-wide reconciliation summary with `state`
(`not_checked`, `clean` or `unresolved`), bounded `findings`, `findings_total`,
`findings_truncated`, an `unresolved` count and `ignored_intra_component` count.
Drift is checked only when model and evidence parse successfully. Any non-passed
finding changes readiness to `needs_attention`, including optional or advisory
findings that a scoped gate may retain as informational. This inspection executes
no commands and makes no task or approval claim. Use `reconcile` for all findings.

## model validate

```bash
"$ARCHCTL_BIN" --root R model validate
```

```json
{
  "schema_version": "archctl.model-validation.v2",
  "status": "passed",
  "revision": "sha256",
  "components": 9
}
```

Exit 0 means the model compiled and validated. It does not mean the model is approved. Exit 3 with an `archctl.error.v2` object means the model is missing or invalid. Use `model compile` for the full `archctl.snapshot.v2` snapshot.

## decisions

```bash
"$ARCHCTL_BIN" --root R decisions list [--components ID ...]
"$ARCHCTL_BIN" --root R decisions show ADR-ID
```

```json
{
  "schema_version": "archctl.decisions.v2",
  "model_revision": "sha256",
  "decisions": [
    {"id": "ADR-001", "status": "accepted", "title": "...", "components": ["orders"],
     "supersedes": [], "path": "architecture/decisions/ADR-001.md", "body": "..."}
  ]
}
```

`decisions show` returns `schema_version: "archctl.decision.v2"` plus the same decision fields. Exit 0 on success, 3 for an unknown decision or component, or 3 for an invalid model.

## impact

```bash
"$ARCHCTL_BIN" --root R impact "task" --evidence E (--paths P ... | --changed [--base-ref REV] | --all) [--out F]
```

The object is `archctl.impact.v2`; its schema is `contracts/v2/impact.schema.json`.

- Exit 0: `assessment: "complete"`.
- Exit 2: `assessment: "partial"`; read `unknowns`.
- Exit 3: invalid model, evidence, path, or Git revision.

A complete impact contract is not an architecture approval and does not execute verification.

## guard check

```bash
"$ARCHCTL_BIN" --root R guard check --baseline B --evidence E [scope] [--run] [--out F]
```

The object is `archctl.guard.v2`; its schema is `contracts/v2/guard.schema.json`.

- Exit 0: `status: "passed"`.
- Exit 1: `status: "failed"`.
- Exit 2: `status: "unknown"` or required verification `not_executed`.
- Exit 3: invalid or missing baseline, evidence, model, or other input.

`authority_changed` reports whether the candidate normalized model differs from the supplied baseline. `true` requires external review. It is not a request to update the baseline. A baseline hash is not reviewer authentication; the baseline must come from protected history or an independently reviewed artifact.

## reconcile and report

```bash
"$ARCHCTL_BIN" --root R reconcile --evidence E [--format json|markdown] [--out F]
"$ARCHCTL_BIN" --root R report --evidence E [--format json|markdown] [--out F]
```

The object is `archctl.reconciliation.v2`; its schema is `contracts/v2/reconciliation.schema.json`. `report` renders the same reconciliation as Markdown.

- Exit 0: the view was produced. Drift is reported, never blocked.
- Exit 3: invalid model or evidence.

The object holds `model_revision`, `source_revision`, `source_digest`, `findings`, `ignored` and `authority_updated: false`.

| Field | Meaning |
|---|---|
| `findings` | One entry per freshness problem, observed relationship, missing declared relationship and policy contradiction. Each finding has `id`, `status`, `message`, `severity`, `decision` and `evidence_refs`. |
| `ignored` | Observed relationships inside one component. An import inside a component is not a relationship between components, so it is listed with a reason and never counted as undeclared drift. |

`findings` statuses are `passed`, `failed` and `unknown`. An undeclared observed relationship is `unknown` and asks for review. It is never turned into intent by this command.

## observe run and observe import

```bash
"$ARCHCTL_BIN" --root R observe run WORKFLOW --baseline B --evidence E [--environment NAME] [--out F]
"$ARCHCTL_BIN" --root R observe import --input F [--out F]
```

`observe run` returns `archctl.workflow-result.v2`; its schema is `contracts/v2/workflow-result.schema.json`. It executes the checks of one declared workflow against a trusted baseline.

- Exit 0: `status: "passed"`.
- Exit 1: `status: "failed"`.
- Exit 2: `status: "unknown"`, or a required check `not_executed`.
- Exit 3: invalid model, evidence, baseline, workflow name, or input.

One workflow is not an overall gate. `runtime_observations` is always empty; the command never invents traces. `observe import` normalizes already-mapped runtime evidence and rejects static bundles.

## evidence validate and evidence import

```bash
"$ARCHCTL_BIN" --root R evidence validate --input F
"$ARCHCTL_BIN" --root R evidence import --input F [--out F]
```

`evidence validate` returns `{"status": "passed"|"unknown", "source_digest": "...", "findings": [...]}`. Exit 0 when the pins are current, 2 when they are stale, 3 for an invalid bundle. `evidence import` writes the normalized `archctl.evidence.v2` bundle and exits 2 for stale pins.

## briefcase export-evidence and export-intent

```bash
"$ARCHCTL_BIN" --root R briefcase export-evidence [--db PATH] [--briefcase BIN] [--source-root DIR] [--out F]
"$ARCHCTL_BIN" --root R briefcase export-intent [--out F]
```

`export-evidence` maps a retained Briefcase Python view to `archctl.evidence.v2` and prints the bundle. Exit 0 on success, 3 when Briefcase is missing or the mapping fails. The mapping keeps coverage `partial` when it cannot resolve an internal import.

`export-intent` returns `archctl.intent.v2` with `native_briefcase_format: false`. It is a normalized handoff, not a native Briefcase declaration.

## errors and output acknowledgements

An input error prints one object to stderr and exits 3:

```json
{"schema_version": "archctl.error.v2", "status": "error", "message": "..."}
```

A command with `--out` prints one acknowledgement to stdout:

```json
{"schema_version": "archctl.output.v2", "output": "/absolute/path", "status": "written"}
```

The acknowledgement `status` is `written` unless the written object has its own `status` field. The written object remains the source of truth.

## Related contracts

The single supported exchange contract family lives in `contracts/v2/`. They cover snapshots, evidence, impact, Guard, reconciliation, verification results, workflow results and intent handoff. The schemas and the runtime validators are both required; schema conformance alone does not establish freshness, coverage or authority.


## gate

```bash
"$ARCHCTL_BIN" --root R gate --baseline-ref FULL_SHA [--change .archctl/change.yaml] [--run]
```

`--baseline-ref` accepts a full 40- or 64-character commit hash. No branch/tag,
implicit baseline refresh, approval flag or snapshot-only evaluator mode exists.
Options: `--evidence E`, `--briefcase B`, repeatable `--source-root P`,
`--no-briefcase`, `--scope changed|all` (default changed), and `--out-dir D`.
`D` must be under `R/.archctl`; it is a parent for a fresh run, never an overwrite
of an earlier run. Global root/model options still precede the command.

Stdout is `archctl.gate-output.v2` with `status`, `baseline_sha` and `report`.
Input errors before run setup use `archctl.error.v2` on stderr. Errors after run
setup retain a report and return `status: error`. The process exits 0/1/2/3 for
passed/failed/unknown/error, consistent with the retained composite report.
`gate-summary.json` uses `archctl.gate.v2` and includes `gate_status` as a
compatibility alias for `status`. It records stage outcomes, evaluator digest,
source/model/contract identities, scope, acceptance, verification and findings.
See `contracts/v2/gate.schema.json`.
The adjacent `gate-summary.md` is the human handoff. Share it together with the
JSON and retained run artifacts; no separate review-packet assembly is needed.

Failure precedence: malformed input is error; a proven applicable policy or
required test failure is failed even when other stages are unknown; otherwise
all stages must pass. Missing optional relationships and unrelated drift are
retained as informational. Runtime/global coverage limitations remain explicit.
Without `--change`, the result is an architectural audit and makes no acceptance
claim; the acceptance stage is omitted rather than reported as passed. A default
changed-scope run with no delta remains unknown.

The low-level `guard check --baseline SNAPSHOT` remains supported, but the caller
must independently supply a trusted evaluator. It does not replace `gate`.

## change validate

```bash
"$ARCHCTL_BIN" change validate --input .archctl/change.yaml
```

Validates `archctl.change.v2` against current component, active decision, policy
and verification IDs. Emits `archctl.change-validation.v2`: `status`,
`change_revision`, `unknowns`. Unknown IDs, duplicate criteria, extra fields and
an empty final component scope are errors. Unmapped criteria and open questions
are unknown. Validation does not review task intent, compare actual changed paths
or execute tests. The gate performs those additional comparisons and execution.

`scope.components` is the candidate component scope. `scope.excluded_components`
subtracts from it; overlap is allowed, and the final set must be nonempty.
`scope.paths` is optional and uses repository-relative POSIX globs to include
reviewed non-component files. It cannot excuse a component outside scope. The
operator reviews the contract; the tool records its digest without authenticating
approval. See `change.schema.json` and the skill's intake reference for the complete format.

## Legacy authoring

The 0.4.0 CLI has no `model migrate` command and rejects `archctl.authoring.v1`.
To migrate an older model, run `archctl model migrate` from 0.3.0, review the
new file, then upgrade. Regenerate legacy evidence, change contracts and compiled
snapshots; ordinary commands accept only v2 exchanges.

The npm launcher also provides `setup`, `--runtime-path` and
`install-skill <agent-skills-directory>`; these provision the distribution and
are separate from architecture adoption.
