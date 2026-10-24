# Architectural context and learning

Archclt supplies reasons, relationships, source candidates and check outcomes.
The coding agent interprets them, chooses an implementation and records
consequential reasoning within the user's existing task authorization. No
adoption, architecture approval, baseline, owner declaration or task YAML is required.

## Start a task

```bash
archctl context 'Reuse API batching for worker concurrency' \
  --paths src/api/batching.py src/worker/jobs.py
archctl context 'Create an event worker' --paths src/events/worker.py
archctl context 'Change the response shape' --changed
```

JSON is the default. `--format markdown` produces a readable briefing. `--out`
writes a **new** file under `.archctl/`; it cannot overwrite source or earlier
packets. Global `--root` and `--model-dir` precede the command. `--model-dir`
moves the governed model and its ADRs only; advisory `architecture/context.yaml`
and `architecture/memory/` remain repository-level.

The packet includes scoped components, possible consumers, rationale excerpts,
source candidates with hashes, proposed dependencies, check suggestions, prior
execution outcomes, concerns and explicit limitations. `assembled` and exit 0
mean packet generation succeeded; they make no architectural acceptance claim.

Source discovery is a bounded file inventory and lexical retrieval, not a new
dependency analyzer or an embedded LLM. Task words, explicit paths, component
scope and graph relations determine retrieval. The coding agent supplies semantic
interpretation and can issue a narrower query or follow returned references.
Default section limit is 8; `--limit` accepts 1–50. Totals report omitted matches.
Reason retrieval follows explicit contradiction and supersession links in both
directions, including related branches. `memory_retrieval` reports direct matches,
related records, returned/omitted counts and a bounded list of omitted IDs with
`memory show` argument vectors. If that list is also truncated, `memory list`
retrieves the complete inventory. A small packet is not evidence of agreement.
Each delivered reason carries its full-record path and fetch command; excerpts
are disposable projections, not canonical records to re-import.
Source search considers at most 400 files and the first 32 KiB of each, returning
small excerpts. Inventory is limited to 4000 files; truncation stays visible.

## Source and conversation evidence

Existing `.archctl/evidence.json` is consumed when present. Supply another
normalized v2 bundle with `--evidence`. With a compatible Briefcase installation:

```bash
archctl context 'Reuse batching for workers' \
  --paths src/api/batching.py src/worker/jobs.py \
  --refresh-evidence --source-root src
```

This reuses the existing Python import mapper and Briefcase public operations.
It does not expand mapping to other languages, runtime traces or session APIs.
A failed refresh is reported as a limitation and never falls back to an older
bundle. Native interoperability must be tested against a real compatible binary.
The packet preserves the normalized producer name/version, retained source
revision and source-pin digest. `source.evidence_path` locates a supplied bundle;
it is null for an in-memory refresh or absent evidence. Evidence locations retain
their original provider strings. The packet does not invent a project identity
or a provider fetch API absent from the normalized input.

Pass `--reference conversation:...` or `--reference case:...` for original context
retrieved by the agent. References are opaque provenance, not automatically
fetched conversations. Preserve user statements separately from interpretations.
Unavailable conversations cannot be reconstructed as remembered fact.

Existing models and standalone ADRs contribute rationale. Decision rows include
`supersedes` and `superseded_by` links. When more matching decisions exist than
the section limit, the packet reports the omission and includes an explicit
limitation. An invalid optional model limits context rather than preventing it.
Malformed explicitly supplied evidence and malformed memory records remain input
errors.

## Components and planned dependencies

Unbound source/planned files receive provisional IDs grouped by directory.
Optional `architecture/context.yaml` overrides stabilize identities:

```yaml
schema_version: archctl.context-config.v2
components:
  - id: worker-runtime
    paths: [src/worker/**]
    aliases: [old-worker]
    purpose: Execute background jobs with bounded concurrency
```

This file does not enter a governed snapshot. Prefer sparse overrides. Generated
IDs are path-derived; aliases preserve retrieval across important renames.
Overlapping bindings are reported; ambiguous dependency endpoints are rejected.

```bash
archctl context 'Reuse API batching in the worker' \
  --paths src/worker/jobs.py src/api/batching.py \
  --dependency src/worker/jobs.py src/api/batching.py
```

Endpoints can be IDs, aliases or bound file paths. The proposed import is
hypothetical. An observed return path supports a potential cycle; absence of a
return path never proves acyclicity. Relevant declared constraints are included.
Affected consumers are investigation candidates; an edit is not automatically
required. No permission map needs updating merely to investigate a new edge.

## Preserve a reason

Create `.archctl/reason.json` from the session:

```json
{
  "schema_version": "archctl.memory.v2",
  "id": "worker-batching-lifetime",
  "statement": "Extract pure batching before sharing it with workers",
  "rationale": "The API helper holds request state; concurrent jobs have a different lifetime.",
  "origin": "agent_chosen",
  "references": ["conversation:task-17/message-8", "case:batching-investigation"],
  "paths": ["src/api/batching.py", "src/worker/jobs.py"],
  "topics": ["batching", "concurrency"],
  "assumptions": ["Jobs may overlap within one worker process"]
}
```

```bash
archctl memory record --input .archctl/reason.json
archctl memory list concurrency
archctl memory show worker-batching-lifetime
```

The record is stored under `architecture/memory/<id>.json`, with pins for existing
bound files. Origins are `observed`, `user_stated`, `agent_inferred`, `agent_chosen`.
The agent should automatically capture reasons expensive to forget, rather than
facts regenerable from source. No approval lifecycle is involved.

Records are immutable. Identical retries keep original pins. Use a new ID and
`supersedes: [old-id]` for a revised choice or `contradicts: [other-id]` for an
unresolved conflict. A record may have multiple successors; all are reported in
`superseded_by_ids`. Referenced records must exist and remain readable.
Freshness describes changed implementation inputs, not the truth of user intent.
Every reason projection reports `applicability.status: not_assessed`, even with
matching source hashes. Changed hashes also leave the reason available for
reassessment. ADR lifecycle status is authored context and does not establish
current applicability or governance adoption.
`reference_checks` reports local artifact presence as `available`/`unavailable`
and opaque provider references as `not_checked`. Presence verifies neither the
original bytes nor the claim. No remote reference is silently fetched. Markdown
includes assumptions, scope, forward/reverse conflict links and full-record fetch
instructions as well as rationale.
Repeated inferences never become user statements. Semantic contradiction analysis
belongs to the agent; the tool tracks explicit links and changed inputs.

0.4.0 stores records as `archctl.memory.v2`. To migrate records written by 0.3.0,
run `PYTHONPATH=src python3 scripts/migrate_memory_v2.py architecture/memory`
from the 0.4.0 source archive. The script changes only `schema_version` and the
content revision; it verifies the old revision first. The installed runtime rejects
v1 records instead of rewriting them.

The retrieval additions remain within the additive v2 output policy. Native
memory, execution and governed input schemas are unchanged. See the
[migration and boundary notes](context-pivot.md) for compatibility details.

## Execute or import checks

```bash
archctl verify run --task 'Worker concurrency regression' \
  --paths 'src/worker/**' tests/test_worker.py \
  --command '["python3", "-m", "unittest", "tests.test_worker"]'
archctl verify run --task 'Existing contract' --check payment-contract
archctl verify import --input .archctl/harness-result.json
```

Commands are argument vectors chosen by the agent under ordinary task permissions.
Retrieved prose never triggers execution. `--check` selects an existing model
command without baseline comparison. Missing architectural evidence does not
prevent useful checks. Timeouts are 1–300 seconds, returned streams are bounded
to 64 KiB each, and POSIX process groups are terminated on timeout. This is an
executor, not a security sandbox.

Execution outcome stays `passed`, `failed`, `unknown` or `not_executed`.
Applicability to current inputs is separate: `current`, `stale` or `unverified`.
A command that passes while changing its recorded inputs cannot attest the
resulting code. Results retain command, working directory, environment label,
timestamp, source pins and actual output. No test result proves assertion adequacy.

Without paths, the bounded source inventory is pinned. With paths/globs, only
that scope is pinned. Dependencies, hidden files and external resources remain
outside the claim. Imported `archctl.execution.v2` records retain declared origin
and references; importing does not authenticate the producer.

Exit 0 means a successful command with current recorded inputs, 1 a failed command,
2 unresolved outcome/applicability, and 3 invalid input. Generated records stay in
`.archctl/executions/`. Source commands and harness import use the schemas under
`contracts/context/v2/`.

## Optional governed workflow

Existing `init`, `model`, `status`, `impact`, `guard`, `observe`, and `gate` retain
their v2 meanings. Choose them when reviewed architectural acceptance is needed.
`status` describes that optional workflow, not whether context-first work can
proceed. Memories and context overrides never approve or weaken a v2 gate.
