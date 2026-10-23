# Unified v2 exchange contracts

All public exchange objects use `archctl.*.v2`. Draft 2020-12 schemas are generated
from one definition set by `PYTHONPATH=src python3 scripts/generate_schemas.py`.
They cover snapshots, evidence, task contracts, impact, Guard, reconciliation,
verification results, workflow results, intent handoff and composite gates.

Policies and findings carry explicit `obligation: required|advisory`. Strict and
selective enforcement use identical schemas. Runtime checks establish references,
coverage, freshness and authority; schema conformance alone cannot establish them.
Archctl output may add fields within a major version; output consumers must ignore
unknown fields. Archctl input parsers are strict and reject unknown input fields.
See [authoring](../../docs/authoring.md) and [CLI contracts](../../docs/cli-contracts.md).
