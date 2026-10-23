# Briefcase integration boundary

## Compatible release

Archclt 0.2.0 maps Briefcase 0.1.0 Python imports. Download its reviewed native
archive and checksums from https://github.com/sij0sh/briefcase-release/releases/tag/v0.1.0.
Install outside source checkouts and set `BRIEFCASE_BIN` to the absolute executable.
Linux/macOS x64 and ARM64 have native build lanes. The producer needs Python 3.11+
for Python analysis. Other Briefcase language capabilities do not expand Archclt's
Python import enforcement scope.


## V1 supported coverage

Native mapping is limited to Briefcase 0.1.0 Python import assertions. It does
not claim non-Python or runtime coverage. A fresh local gate exports evidence
when the binary is available, or validates a supplied pinned bundle. Missing,
stale, partial or insufficient evidence remains unknown for required decisions.
A failed export does not fall back silently. Native interoperability tests must
be reported as not executed when the actual binary is unavailable.


## Status

V1 has a strict normalized exchange and a native mapper for **Briefcase 0.1.0 Python imports**. The mapper is tested against the real Briefcase CLI, including a mapped bundle that passes Guard. Compatibility is verified only for the Python import scope; other providers and relationship kinds remain unmapped.

`archctl.evidence.v2` is the interchange format this project accepts. `archctl.intent.v2` is a normalized intent handoff. Both contracts have self-contained JSON Schemas under `contracts/v2/`. The runtime additionally checks cross-references, freshness, scope and authority semantics. A `selective` model emits `archctl.intent.v2` and reports the same Python-only support profile; the evidence format does not change.

## Native Python mapper

```bash
"$ARCHCTL_BIN" --root <repository> briefcase export-evidence \
  --db .briefcase/briefcase.db \
  --out .archctl/evidence.json
```

The command runs Briefcase's public JSON commands. It does not read Briefcase's database directly.

- `scan` captures the retained source view.
- `inspect-external` returns the retained SHA256 for each component file.
- `neighbors` returns retained `IMPORTS` assertions.
- `unresolved` plus `explain` classify every unresolved import from a component source file.

The mapper emits a `source.files` pin for every file in the declared component paths. It accepts `exact_retained_bytes` and `ambiguous_retained_matches` only when the retained digest equals the current file bytes. A stale, missing or changed file produces a gap, not a silent pin.

Only regular `.py` component files are analyzed for imports. Every other matched component file, including data or documentation matched by a component glob, produces an explicit coverage gap and keeps coverage `partial`. A retained pin proves byte identity, not dependency analysis. Files outside the declared component paths do not create component gaps.

An edge is emitted only when both files have exactly one component binding and Briefcase retained the import assertion. Briefcase also reports Python package-initialization imports, such as `archctl.atlas.impact` importing `archctl` and `archctl.atlas`. Bind the root package file to its own component rather than to a feature module; otherwise these real initialization edges look like feature dependencies.

Every unresolved import from a component file is expanded to its retained source span. If the literal target could match a component module, the mapper reports a gap and keeps coverage `partial`. Unresolved external or standard-library imports are outside the declared component relationship scope. Coverage stays `partial` when capture text is incomplete, a component has no files, any component file lacks a matching retained digest, or an internal import is unresolved. Otherwise the bundle may claim complete static coverage for the declared components and `imports` kind.

## Scoped evidence preparation

Use `briefcase prepare-evidence` when the reviewed component-only projection
procedure is needed. It orchestrates existing external tools. It is not another
mapper, a gate, or a fix for Briefcase's full-tree capture limit.

```bash
"$ARCHCTL_BIN" --root "$APP" briefcase prepare-evidence \
  --archctl "$ARCHCTL_BIN" --briefcase "$BRIEFCASE_BIN" \
  --source-root src --out-dir .archctl/prepared/change-02
```

Supply absolute paths to independently reviewed installations outside source
checkouts. Keep release and artifact pins with the project's local toolchain record; see `docs/releasing.md`. The command removes
candidate Python import paths and database overrides from external-tool
subprocesses. It does not authenticate an installation or sandbox its execution.
The recorded executable hashes identify launchers, not all runtime dependencies.

Use the reviewed installation for preparation and export. `ARCHCTL_BIN` and
`BRIEFCASE_BIN` supply defaults; explicit flags override them. A candidate
checkout or unreviewed wheel cannot supply governed evidence.

Preparation requires a Git worktree root and explicit import-resolution roots.
Use the directory containing the Python package, such as `src`, not the package
itself. Every component file must be below a supplied root.
The helper supports regular `.py` component files only.
Missing scopes, symlinks and ambiguous component bindings are input errors.
It does not add non-Python support or change the native mapper's behavior.

Each attempt requires a new output directory. Inside the application, use
`.archctl/`. The helper builds a detached sparse worktree at the current full
HEAD SHA. It copies current component and authoring bytes into that projection.
The manifest records additions, edits and deletions against HEAD as a dirty
overlay. HEAD is source identity, not the architecture baseline.
Application source, HEAD, index and Git configuration remain unchanged.
Temporary worktrees are removed after success or failure.

The pinned external exporter scans the projection with an explicit fresh
database. The helper checks the complete exported component inventory against
the full application. It rechecks authoring, source inventories, HEAD, tool
executables and exported bytes before publishing `evidence.json`.
It never repairs mismatched pins or falls back to `.archctl/evidence.json`.

The directory retains `manifest.json`, external command output and raw
`producer-status.json`. The manifest includes the exact producing publication's
diagnostics, source/view identities, file hashes, dirty overlay, tool paths and
executable hashes, source roots, omitted HEAD-tracked paths and elapsed time.
Untracked non-component files are not inventoried. Producer unresolved and
unsupported diagnostics remain visible even when normalized component import
coverage is complete. Manifest preparation version 1 is local diagnostic data,
not a new evidence exchange or an approval record.

Success returns an `archctl.output.v2` acknowledgement with `output` and
`manifest` paths. The manifest says `prepared`, `gate: not_executed` and
`approval: not_assessed`. Failure exits 3 and may retain `export.json` and an
error manifest for diagnosis. Only a successful attempt publishes
`evidence.json`. Reusing an output directory is an error and does not alter the
previous attempt.

Supply the fresh bundle explicitly to the independent gate with `--evidence`.
Run verification in the full application, never in the projection.
Python import coverage is limited to the retained declared component files.
Tests, benchmark fixtures, TypeScript, dynamic imports, installed dependencies
and runtime structure remain outside this structural guarantee.

## Evidence exchange

```json
{
  "schema_version": "archctl.evidence.v2",
  "producer": {"name": "briefcase-mapper", "version": "1"},
  "source": {
    "revision": "retained-source-view-id",
    "files": {
      "src/orders/api.py": "<64 lowercase SHA256 characters>",
      "src/payments/service.py": "<64 lowercase SHA256 characters>"
    }
  },
  "coverage": {
    "analysis": "static",
    "status": "partial",
    "components": ["orders", "payments"],
    "relationship_kinds": ["imports"],
    "gaps": ["Dynamic imports unresolved"]
  },
  "evidence": [
    {
      "id": "source-edge-1",
      "kind": "static",
      "location": "case:/retained-case/slice/0",
      "description": "Pinned source import evidence"
    }
  ],
  "edges": [
    {
      "id": "orders-payments-observed",
      "source": "orders",
      "target": "payments",
      "kind": "imports",
      "origin": "static",
      "evidence_refs": ["source-edge-1"]
    }
  ]
}
```

The angle-bracket digests above are explanatory placeholders and are intentionally not valid evidence. Use actual SHA256 values, never copy these placeholders into a fixture.

The source revision is the exporter's retained view identity, not necessarily a Git SHA. `files` pins the local bytes and is required even if the revision is a commit. Include every source file inside the components advertised as covered, plus relevant configuration/test inputs needed for your verification provenance. Missing, modified, deleted and newly unpinned component files cause unknown results.

Static and runtime bundles are imported separately. Runtime evidence must be `partial`; observations from one execution do not establish complete static coverage. Every edge must reference existing evidence with a matching origin. Derived assertions may supplement an edge, but cannot alone establish a static or runtime relationship. Declarations are not accepted as observed source evidence.

`coverage.status: complete` is a producer assertion limited to its declared components and relationship kinds. It is not a universal repository guarantee. The producer is part of the trusted analysis chain. If there are known gaps, preserve them and use `partial`. A successful response or a retained case with no edges does not by itself justify complete coverage.

## Native mapper responsibilities

The implemented mapper follows these rules. Future providers or relationship kinds must preserve them:

1. Pin the retained Briefcase source/case identity and preserve its file hashes.
2. Resolve Briefcase source entities into the approved component IDs using explicit bindings. Reject ambiguous matches.
3. Map supported relationship semantics individually; do not conflate imports, runtime calls, data writes and test associations.
4. Carry Briefcase evidence/derived distinctions into evidence items. Preserve original provenance URIs as locations.
5. Convert coverage diagnostics and unresolved internal relationships into explicit gaps. Never infer completeness from a successful API status.
6. Feed the normalized bundle through `evidence validate` and test stale/current/malformed cases against the real engine.
7. Keep Briefcase as the evidence owner. Guard owns its own CI decision.

The development fixture exporter is intentionally confined to `tests/fixtures/evidence.py` and the generated demo fixture. Product modules do not import it. It is not a second general-purpose source analyzer.

## Runtime handoff

Use `observe import --input <mapped-runtime-bundle>` for already normalized, scoped observations. Environment and trace identity should be retained in the producer's provenance locations/descriptions; do not assert that a current source hash proves a production binary was built from it. The collector must establish that correspondence.

`observe run` emits executed verification results and an empty `runtime_observations` list. It never derives spans from exit code 0. An OpenTelemetry collector/export mapper and span-to-component binding are later integrations.

## Impact contract

`archctl.impact.v2` records the compiled model revision, candidate source revision/digest, changed paths, affected components with evidence references, relevant decisions, declared verification obligations, and unknowns. A `selective` model emits `archctl.impact.v2`, which adds each obligation, its `required_by` reasons and categorized `unknown_details`. Its digest allows Guard and a reviewer to identify the exact analysis used.

Guard constructs impact fresh inside the CLI; it does not trust an arbitrary user-edited impact JSON as proof. The external file is useful for agents, review and downstream tools. Current evidence and explicit paths are supported; comparison of two retained Briefcase graph views is a later extension.
