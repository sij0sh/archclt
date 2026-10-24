# Context without adoption: boundaries and migration

Archclt helps the coding agent recover consequential reasons, challenge their
assumptions and choose the smallest architecturally correct change. The agent
continues investigating while an unresolved question could materially change
the design or its verification, then implements and tests. The quantity of
investigation, generated context or code is not itself the objective.

## Runtime boundary

| Entry point | Runtime path | Required authority |
| --- | --- | --- |
| `context TASK` | CLI → context composition → Core memory/bindings and Atlas projection | Existing task authorization; no model/baseline |
| `context --changed` | Same path plus shared Git scope integration | Git revision identifies scope, not approval |
| `memory record/list/show` | CLI → Core immutable reason store/projection | Existing task authorization; no model/baseline |
| `verify run --command` | CLI → verification records → bounded process executor | Explicit caller-selected argument vector |
| `verify run --check` | Same verification path after resolving a model check | Model needed to resolve the explicit check ID |
| `status` | Scoped inspection of optional governed inputs plus core prerequisites | No adoption or task verdict |
| `gate`, `guard`, governed model/change/impact/observe | Explicit existing compatibility route | Existing reviewed-baseline and strict/selective rules |

Ordinary routes no longer import the gate, Guard, Observatory or Change Contract
parser. Shared Git discovery resides in `integrations/git.py`; the gate reuses
the same function. `cli_gate.changed_paths` and its internal Git alias remain
available to existing callers. No duplicate Git scope implementation is added.
Optional model compilation still supplies declared context and check suggestions;
it does not invoke baseline comparison, a policy verdict or command execution.

## What a returned reason means

The canonical native record remains `archctl.memory.v2`: statement, rationale,
origin, original references, scope, assumptions, relationships and source pins.
Existing record bytes and IDs are not rewritten by retrieval. Exact authoring
retries preserve pins; conflicting content requires a new ID with an appropriate
relationship. No proposed/accepted/reviewed state is added to native memory.

Context is a disposable projection. `freshness` compares source pins;
`applicability.status` remains `not_assessed`. An unchanged implementation can
have new requirements, and a changed implementation can still need the same
architectural reason. Neither case is reduced to a confidence or readiness score.
The lexical `score` orders retrieval candidates only.

Explicit relation traversal includes forward and reverse contradictions and
supersession through connected branches. The section limit still bounds full
record delivery. `memory_retrieval` counts direct/related records and omissions,
returns at most `--limit` omitted IDs and exposes whether that list is truncated.
Each stub has a real `archctl memory show ID` argument vector; `memory list`
recovers the complete inventory. Run these in the same repository, using global
`--root` when needed. Semantic disagreement without an explicit link still
requires the coding agent's investigation.

Markdown shows assumptions, scope, both directions of conflict, replacements and
full-record commands. A historical ADR's authored lifecycle is retained while its
current applicability and adoption remain unassessed.

Local references are checked for file presence only, including `artifact:` paths.
Unavailable or escaping local paths cannot become fresh support. Provider URIs
remain `not_checked`; a `case:` or `conversation:` string is preserved provenance,
not an invented fetch interface. The tool never reads outside the repository to
resolve a local reference. Malformed canonical memory remains an input error.

## Evidence and verification

Briefcase continues to own retained implementation evidence. Existing normalized
v2 bundles and the explicit Python import refresh remain supported. Context keeps
the producer, retained revision, source-pin digest, original evidence locations
and supplied bundle path. The normalized format does not carry arbitrary native
project/Case envelopes; context does not invent or join them. No new provider
analyzer, session parser or composition service is introduced.

An absent provider limits dependency claims. A failed refresh never falls back
to an old bundle. Unreadable optional ADRs or default evidence yield localized
diagnostics; malformed explicitly supplied evidence and corrupt native memory
remain errors. No missing data triggers automatic adoption or initialization.

Verification preserves actual outcomes independently of source applicability.
Passing stale checks stay historically passed with stale applicability. Harness
imports retain their original producer. Suggested model commands remain
unexecuted until explicitly selected by the caller; retrieved prose does not
authorize execution. Existing process bounds, exit codes and gate restrictions
continue to apply.

## Compatibility and rollout

| Surface | Migration |
| --- | --- |
| Native v2 memories/executions/config | None; canonical schemas and existing bytes stay intact |
| Context v2 consumers | Accept additive projection fields; updated schema keeps additions optional so earlier packets validate |
| `memory show/list` consumers | Ignore additive view diagnostics; use the canonical file for archival identity |
| `status` consumers | Existing status names and exit codes stay intact; read `status_scope`, `meaning` and `capabilities` before interpreting readiness |
| Explicit strict/selective gates | No policy, baseline, acceptance or verification semantics change |
| Existing v1 records | Existing 0.4.0 one-time migration still applies; this refactor does not restore runtime v1 support |
| Optional provider use | Omit refresh/evidence flags to use reasons and bounded local retrieval alone |

The planning document was written against installed v1 guidance without product
source. The supplied implementation already uses one public v2 version and permits
additive outputs (ADR-006). This refactor follows that current contract rather
than downgrading or migrating canonical records again.

Default help starts with context/memory/verify and labels explicit governed
commands separately. `status` next actions make governed repair conditional;
they do not direct every ordinary task to a gate. Removing dead governance or
replacing bounded local lookup requires evidence about real consumers and is a
separate change. This update adds neither a mandatory mode nor a new approval step.

Deterministic regression cases demonstrate retrieval, provenance, default-path
independence and preserved enforcement behavior. They do not establish reduced
decision cost or improved architecture across autonomous tasks. A controlled
agent evaluation and native Briefcase interoperability remain empirical work;
see the accompanying refactor validation report for what actually ran.
