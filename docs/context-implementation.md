# Context-first implementation notes

Version: 0.4.0 source update. October 23, 2026.

## Implemented

- Task context without model adoption, approval baseline or a maintained task contract.
- Lexical and path/component retrieval of bounded source candidates and rationale.
- Existing ADR rationale, including standalone ADRs without a complete governed model.
- Decision lifecycle links, active-before-replaced ordering, and explicit limits when
  matching decisions are omitted.
- One shared exclusion policy for source inventory and evidence pins.
- Automatic provisional bindings; sparse stable-ID/path/purpose overrides and rename aliases.
- Reverse consumer/workflow impact with explanatory paths and no implied edit requirement.
- Hypothetical import analysis, supported return paths and declared constraint references.
- Immutable attributable memory, source pins, explicit conflicts and supersession history,
  including every successor when a record has more than one.
- Task-authorized verification and harness import using the shared bounded executor.
- Execution outcomes separated from applicability to current inputs.
- Updated default agent skill and advisories at the shared v2 contract version, with gate compatibility.
- Removed v1 authoring input and migrated persisted memory records to v2.
- Cold-start demo and regressions covering missing context, stale/conflicting memory,
  greenfield work, aliases, reuse retrieval, cycles, verification and input integrity.

## Deliberate limits

The existing coding agent supplies semantic judgment and writes consequential
reasons as part of task completion. No second LLM or autonomous background memory
service is introduced. Conversation references must be supplied from actual
accessible context; the tool cannot fetch arbitrary prior conversations.

Native Briefcase mapping remains Python imports. Other supported file extensions
can participate in inventories and source retrieval, not dependency guarantees.
The normalized bundle must use identities consistent with the available bindings.
Retrieval is bounded lexical selection and scope, not semantic search or proof
that the best reusable abstraction has been found. Assumptions and conflicts
require agent interpretation. Relevant unreturned records can be fetched by ID.

Checks retain observed outcomes and scoped inputs; they do not prove test adequacy,
security isolation, runtime performance or production build identity. Optional
governed commands retain their old restrictions. No gate is silently weakened.

## Packaging and validation

The release source includes the npm launcher, hosted CI and release workflows.
Python wheel/source packaging tests build real artifacts, and `npm test` covers the
launcher. The distribution regression copies optional npm and hosted-CI assets when
present so a Python-only source archive remains testable.

Run the full suite and both demos. Native interoperability and schema conformance
must report explicit skips if the matching binary or optional validator is absent.
Full controlled agent evaluations against Briefcase-only and gate-based workflows
remain a separate empirical exercise; deterministic tests do not establish a
measured reduction in technical debt.

See [the validation record](validation-0.4.0.md) for the executed checks and skips.
