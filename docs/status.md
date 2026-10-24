# Support status

The 0.4.0 release makes context, architectural memory and task-authorized
verification the normal agent workflow. These use advisory v2 contracts. The
optional model/impact/guard/gate/observe workflow also uses v2. The two contract
families remain independent.

Supported: Python 3.11+, bounded source inventories and lexical retrieval, optional
model/standalone ADR rationale, provisional components and rename aliases, memory
capture with provenance and explicit conflict/replacement links, hypothetical
imports, scoped execution records and harness import. Tests target Linux; macOS
and Windows process behavior requires platform validation for this update.

Briefcase remains the external source evidence producer. Native mapping covers
the documented Python imports only. Other source file extensions can be retrieved
without implying dependency coverage. Dynamic imports, production runtime coverage,
trace collection, hosted approval and graph UI remain outside the implementation.

The coding agent supplies semantic interpretation and original conversation
references. Retrieval does not access unprovided chat history. Source freshness,
unknowns, missing observations and unexecuted checks remain explicit.
`status` retains legacy governed-input readiness and exit codes while reporting
independent core prerequisites and explicitly declining to infer adoption. Start
ordinary tasks with `context`; no readiness or acceptance step is required.
Reason retrieval exposes bounded omissions and fetch commands, checks local
reference presence separately from provider verification, and leaves semantic
applicability to the coding agent even when source hashes match. See
[migration and boundary notes](context-pivot.md).

The npm launcher and hosted release workflows are part of the release source.
`npm test` covers the launcher; hosted workflows run in GitHub Actions. Read
[implementation notes](context-implementation.md) for scope and evaluation limits.
