# Archclt refactor: implementation and validation

This source update completes the missing parts of the context-first pivot in the
supplied Archclt 0.4.0 snapshot. A coding agent can retrieve and challenge durable
reasons, discover what a bounded response omitted, and proceed with task-authorized
implementation and verification. Ordinary work acquires no model, acceptance,
baseline or adoption prerequisite.

The source already implemented most of that default workflow. The refactor
therefore preserves those foundations and fixes the remaining coupling and
interpretation gaps instead of replacing the product. The supplied source uses
v2 contracts, superseding the installed v1 guidance on which part of the original
plan was based. Canonical records remain v2, and the new output fields follow the
existing additive compatibility rule in ADR-006.

## Delivered behavior

1. **Independent ordinary commands.** The CLI loads gate/Guard/Observatory/Change
   Contract code only on explicit compatibility routes. Shared Git scope lives
   in `integrations/git.py`, used by both `context --changed` and the existing
   gate. No second scope implementation or mandatory mode is added.
2. **Challengeable bounded retrieval.** Explicit contradictions and supersession
   are traversed in both directions through related branches. Reverse conflict
   links remain visible on delivered records. `memory_retrieval` counts matches,
   related records, returns and omissions; omitted-ID delivery is itself bounded
   and explicitly marked when truncated. Real `memory show` argument vectors
   and a complete-inventory command provide follow-up paths.
3. **Freshness separated from applicability.** Reason projections always leave
   semantic applicability `not_assessed`. Matching hashes do not establish that
   a reason applies; changed hashes do not erase it. ADR lifecycle status remains
   authored historical context, not adoption or current authority.
4. **Qualified supporting references.** Local artifact presence is reported
   separately from evidence verification. Missing/escaping local references are
   unavailable; provider references remain opaque and `not_checked`. Original
   strings are preserved. No fetch API, project identity or fresh observation
   is invented from a `case:` or `conversation:` label.
5. **Complete readable briefings.** Markdown includes assumptions, scope, forward
   and reverse conflicts, successors, reference limits and full-record fetch
   instructions. Memory inventory queries also search assumptions, IDs and scope.
6. **Evidence provenance retained.** Context exposes the normalized producer,
   retained revision, source-pin digest and supplied bundle path. Original
   evidence locations remain unchanged. The existing explicit Python import
   mapper remains the only native mapping route; no new analyzer is introduced.
7. **Localized optional-input failures.** Unreadable optional ADRs and default
   evidence produce gaps while usable reasons remain available. Explicit invalid
   evidence and corrupt canonical memory remain errors. A failed provider refresh
   preserves historical reasons without reusing an old evidence bundle.
8. **Scoped status.** Existing `ready`/`needs_model`/`needs_attention` values and
   exit codes retain their governed-input meaning. Additive scope, explanation
   and capability fields distinguish ordinary prerequisites and unassessed
   adoption. Next actions direct ordinary work to context and qualify governed
   repair instead of directing every task to a gate.

The immutable writer, actual verification outcomes, harness origins, explicit
registered-check behavior and strict/selective enforcement semantics remain
intact. All 16 original native memory files are byte-for-byte unchanged. One new
`agent_chosen` memory records this implemented design with source pins and real
repository references. No existing decision or policy was rewritten to clear a
finding.

## Plan disposition

| Package | Result |
| --- | --- |
| A1: Default dependency isolation | Removed eager governance imports; characterized no-model, invalid optional model and changed-path routes in fresh interpreters |
| A2: Relevant/challengeable rationale | Implemented relation closure, reverse challenges, bounded omissions, fetch routes and applicability diagnostics |
| A3: Low-friction immutable authoring | Retained the existing writer, retry/collision semantics and provenance; reused its native schema without another form or lifecycle |
| A4: Evidence by reference | Preserved native references and added source provenance; exercised normalized fixtures and failed refresh behavior; no unproven composition service |
| A5: Independent verification | Preserved actual command execution/import contracts and source applicability; existing negative and stale-result regressions pass |
| A6: Legacy governance isolation | Kept explicit semantics and compatibility exports; shared only Git discovery; model and policies remain unchanged |
| A7: Help and migration | Updated help, context/status/contract guides and added detailed boundary and migration notes |
| A8: Evaluation | Deterministic source/contract-generation/compatibility checks and demos executed; controlled autonomous-agent evaluation remains unmeasured |

See [boundary and migration notes](docs/context-pivot.md) for the runtime map,
field semantics, rollback behavior and consumer migration table.

## Validation actually executed

| Check | Result |
| --- | --- |
| Original archive: full unittest discovery | 185 tests: 171 passed, 14 skipped; one additional distribution `setUpClass` error |
| Refactored source: full unittest discovery | 199 tests: 185 passed, 14 skipped; the same distribution `setUpClass` error |
| Final focused retrieval/schema-generation/docs/boundary suite | 21 tests: 20 passed, one optional schema-validator skip |
| New regression cases | 14 passed, including fresh-process import isolation, one-record reverse conflict, branching omissions, full fetch, applicability, unreadable optional data and provider provenance |
| Context cold-start demo | Passed: reason recovered, stale pins visible, replacement history preserved, direct verification passed without adoption |
| Governed demo | Passed: valid change passed; forbidden dependency failed; stale evidence and changed authority stayed unknown |
| Node launcher tests | Two passed using a writable temporary directory; these cover checksum rejection and skill-copy behavior, not a rebuilt runtime wheel |
| Release validation preflight | Correctly stopped at missing `jsonschema`; no release build or installed-wheel smoke claimed |

Unittest does not count a failing class setup in its `Ran` total; the setup error
above is in addition to the listed executed tests. No test was removed or
downgraded to hide this error. The distribution test fails at the missing
`.github` directory in both original and updated source. The attachment also
omits root release inputs including `pyproject.toml`, `MANIFEST.in`, `LICENSE`,
`README.md` and package manifests. Their missing contents were not reconstructed
from assumptions.

The 14 skips comprise nine actual Briefcase interoperability cases, four JSON
Schema conformance cases requiring `jsonschema`, and one integration case needing
configured reviewed external tools. Schema regeneration/reproducibility and
native input validation ran; full third-party schema conformance did not.
Controlled end-to-end comparisons of decision cost, architectural quality and
technical debt have not been performed. These deterministic results establish
the specified behavior and compatibility, not measured architectural improvement.

Commands used include:

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -q
PYTHONPATH=src python3 -B -m unittest tests.test_context_pivot \
  tests.test_context_contracts tests.test_contract_versions \
  tests.test_docs tests.test_architecture -q
PYTHONPATH=src python3 -B scripts/demo_context.py
PYTHONPATH=src python3 -B scripts/demo.py
TMPDIR=<writable-temporary-directory> node --test npm/test/launcher.test.cjs
PYTHONPATH=src python3 -B scripts/validate.py
```

## Source bundle and application

The accompanying `archclt-refactored.tar.gz` is a source update, not a rebuilt
release. It contains the modified source, updated context schema, regression
cases, migration notes, this report, `archclt-refactor.patch` and the validation
record under `validation/refactor/`.

The old generated `build/` tree and `npm/runtime/` wheel/manifest are deliberately
excluded from the new archive. They describe the input snapshot and would silently
run old code if presented as the refactor. Their original identities remain in
the bundle's input manifest. The source patch does not delete generated files
from an existing checkout; remove or rebuild them through the normal release
process before using a distribution. The original input archive is unchanged.

With Python 3.11+ and PyYAML available, exercise the updated source directly:

```bash
PYTHONPATH=src python3 -m archctl context 'Describe the task' --paths src/example.py
PYTHONPATH=src python3 -m archctl memory list
```

For a full checkout, apply the patch at its root with `patch -p1`; review and
rebuild distributions using its restored release metadata and dev dependencies.
The patch is checked against an untouched extraction and applied to a separate
copy for byte comparison. Generated context, caches and local test output are
excluded from the archive except the explicitly retained validation artifacts.

Existing canonical records require no migration. Existing governed CI invocations
continue to mean what they meant before. Reverting the source patch restores the
previous derived behavior; no baseline tag or original memory needs rewriting.
