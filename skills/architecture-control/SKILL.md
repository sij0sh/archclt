---
name: architecture-control
description: Use Archclt and Briefcase to investigate architecture, reuse code, scale a component, build new features or repositories, recover prior design reasons, check downstream impact, and preserve consequential architectural learning. Also supports explicitly requested governed gates.
---

# Architectural context and learning

Use Briefcase for grounded source relationships and retained references. Use
Archclt to connect the task to reasons, assumptions, consumers and useful checks.
Make design decisions within the user's existing task authorization.

## Default workflow

1. Obtain `archctl context '<task>' --paths <planned paths>` before consequential
   design or implementation. Use `--changed` when Git scope is more useful. No
   model, baseline, task YAML or architecture approval is required.
2. Read relevant rationale and follow source/Case references. Treat provisional
   boundaries, inferred reasons and reuse candidates as hypotheses. Supply the
   user's current conversation context yourself; Archclt cannot retrieve a
   conversation it has never received. Preserve original references and origin.
3. Investigate lifecycle, state, failure, compatibility and resource assumptions
   before reusing code. Use `--dependency <source> <target>` for a proposed import.
   Missing evidence limits particular claims; continue useful investigation and
   checks within the authorized task.
4. Implement and verify using ordinary project commands or `archctl verify run`.
   Record actual outcomes and source scope. A passing mapped test does not prove
   every requirement. Recheck stale evidence before relying on it.
5. Automatically record only consequential new reasoning with `memory record`.
   Label it `observed`, `user_stated`, `agent_inferred` or `agent_chosen` honestly.
   Keep assumptions, source references and changed conditions. Use new IDs and
   supersedes/contradicts links; never rewrite old notes to hide disagreement.

Read [context operations](references/context.md) for executable examples and
record formats. Read [design judgment](references/design.md) when decomposing or
reusing code. Read [evidence](references/evidence.md) for native mapper limits.
Ask for clarification only when material user intent is actually unresolved,
not because a component or rationale changed. Do not create approval obligations
from an inferred convention. Current instructions govern over remembered context.

## Optional governed workflow

Use [governed change](references/change.md), [adoption](references/adoption.md)
and [authoring](references/authoring.md) only when the repository/user explicitly
chooses reviewed architectural acceptance. Their baseline and reviewed-command
requirements apply to v2 gates, not ordinary context/memory/verify operations.
For installation see [install](references/install.md); for existing gate reports
see [review](references/review.md).
