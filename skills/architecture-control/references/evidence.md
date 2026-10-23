# Evidence and read-only assessment

For ordinary implementation, start with `archctl context '<task>' --paths ...`.
It consumes optional evidence without adoption and can refresh supported imports
with `--refresh-evidence --source-root src`. Rationale and original conversation
references come from the coding agent and retained memory. Read the actual source
before inferring lifecycle or reuse suitability. Run useful checks independently
through ordinary project tooling or `verify run`; evidence gaps limit claims.

The reviewed-baseline procedures below apply only to optional governed workflows.

Use Briefcase for retained evidence and live files for current bytes.
Reuse relevant fresh Cases rather than repeating discovery.
Keep observed behavior, reviewed declarations and proposed changes distinct.

Read-only explanations need no initialization, Change Contract or passing gate.
A missing model calls for a supported explanation, not automatic adoption.
Enter [adoption](adoption.md) deliberately or [change](change.md) for governed implementation.

## Assess an existing model

Run `"$ARCHCTL_BIN" --root <repo> status --format json` for input readiness.
Use explicit paths with `impact` for ownership, consumers and governing ADRs.
An absent or stale bundle limits architectural claims, not all investigation.
For an optional readiness/drift summary, run
`"$ARCHCTL_BIN" --root <repo> status --drift`.
Its repository-wide summary is not a task verdict. It treats every non-passed
reconciliation finding as unresolved; the composite gate can classify optional
or unrelated findings as informational.

## Produce governed evidence

Briefcase owns source analysis; archctl maps its supported assertions.
Native mapping covers Briefcase 0.1.0 Python imports, not other languages or runtime behavior.
Use the reviewed external producer:

```bash
"$ARCHCTL_BIN" briefcase export-evidence --out .archctl/evidence.json
"$ARCHCTL_BIN" evidence validate --input .archctl/evidence.json
"$ARCHCTL_BIN" impact '<task>' --evidence .archctl/evidence.json --paths <paths...>
```

For drift assessment, use `"$ARCHCTL_BIN" reconcile --evidence .archctl/evidence.json --format json`.
Preserve source revisions, file hashes, inventories, producer identity,
assertion references and coverage gaps.
Static absence supports a conclusion only inside explicitly complete supported scope.
Test suggestions and passing commands create no runtime observations.

The composite gate exports fresh evidence when Briefcase is available;
otherwise it checks a pinned bundle and its freshness.
Let it export unless supplying a separately prepared bundle with `--evidence`.
A failed fresh export cannot fall back to an older bundle.
Missing or inadequate evidence stays unknown; the demo exporter is not a substitute.
Keep unsupported dependencies and skipped native interoperability checks visible.
Global coverage gaps can block the gate because not every gap is localized to a component.
