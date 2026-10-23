# Advisory context contracts

These contracts coexist with the unchanged governed `contracts/v2` family.

- `archctl.context.v1`: bounded task context with attributable reasons, evidence,
  hypothetical dependencies, check suggestions, execution outcomes and limitations.
  `assembled` describes packet generation; it is never an architectural pass.
- `archctl.memory.v1`: immutable rationale with origin, references, assumptions,
  optional component/path bindings, evidence pins and replacement/conflict links.
  Input may omit optional collections and revision. Recording materializes defaults.
- `archctl.execution.v1`: an actual command outcome and its input/environment scope.
  Origin identifies local execution or a harness report. Import never authenticates
  an external producer. Applicability is recalculated separately against current files.
- `archctl.context-config.v1`: optional component bindings, purpose and old-ID aliases.
  This is advisory configuration and does not enter a governed model snapshot.

Regenerate with `PYTHONPATH=src python3 scripts/generate_context_schemas.py`.
Runtime parsing additionally checks identities, paths, revision digests, references,
supersession cycles, returncode consistency and freshness. The packet's memory
revision identifies the full stored record; its rationale can be an excerpt.

The coding agent supplies semantic interpretation and conversation references.
Retrieval is lexical plus explicit scope and graph relationships. The tool does not
invent missing conversations or treat repeated inferences as additional evidence.
