# Changelog

## 0.4.1

- Remove the tracked agent notes, architecture overview, contributor guide and refactor report.
- Point the README, distribution manifest and distribution test at the retained docs and ADRs.
- No runtime, contract or workflow behavior changes.

## 0.4.0

- All public authoring and exchange contracts use one version, v2.
- Advisory context, memory, execution and context-config contracts move from v1 to v2.
- Existing memory records migrate once to `archctl.memory.v2`; statements and pins stay unchanged.
- Legacy `archctl.authoring.v1` input and `archctl model migrate` are removed from 0.4.0.
- Users migrate v1 authoring with 0.3.0 before upgrading. v1 records are rejected, never silently converted.
- Governed and advisory contract families remain separate; gate semantics and outcomes are unchanged.
- `pi-archctl` must accept only v2 contracts.

## 0.3.0

- Default agent workflow assembles task-specific architectural context without adoption.
- Attributable immutable rationale records, source freshness, aliases, conflict and replacement links.
- Provisional components, lexical source candidates and hypothetical import-cycle investigation.
- Verification and harness-result import independent of architecture approval.
- Separate advisory v1 contracts; governed v2 gate semantics preserved.
- Updated coding-agent skill, cold-start demo and decision-oriented regression tests.
- Python-source packaging tolerates optional npm/hosted-CI directories absent from an input archive.

## 0.2.0

First public distribution under `sij0sh/archclt`.

- Python package `archclt` and npm launcher `@archclt/archctl`; command `archctl`.
- One v2 contract family with strict defaults and explicit advisory obligations.
- One-way legacy authoring migration; regenerate legacy exchange artifacts.
- Portable, versioned architecture-control skill and external tool installation.
- Storefront retained as a development fixture; validation records become artifacts.
- Standard wheel/source distributions and release automation.

This release changes exchange contracts from the private prototypes. Review
model migration and choose a new baseline before upgrading adopted repositories.
