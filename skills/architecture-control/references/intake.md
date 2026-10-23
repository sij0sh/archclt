# Intake and clarification

State the requested outcome in observable terms.
Separate explicit requirements, source-supported facts, proposed assumptions and material questions.

## Stop and ask

The operator holds authority and facts the tool cannot authenticate.
A guess becomes authority when it is written.
Ask before dependent work when an answer would do one of these:

| Trigger | Ask about | Cost of guessing |
|---|---|---|
| A new or changed rule, component, ADR or command | The intended constraint and its owner | A wrong rule is binding, and the gate cannot detect it |
| Scope beyond the current authorization | Include the consumer, or stop at its boundary | An edit the operator did not approve |
| A baseline move after an authority change, a migration, deletion or other hard-to-reverse step | Whether and when to proceed | A durable decision made by the agent |
| Sources disagree: code, ADR and stated intent | Which source is authority | A silent override of reviewed intent |
| Two defensible designs with different long-term costs | Which trade-off the operator accepts | A coin flip becomes architecture |
| A negative or complete claim rests on missing evidence | Narrow the claim, or obtain evidence | "No other consumers" when coverage is partial |

Do not ask for facts the repository already answers, approval already given,
or cosmetic choices. Proceed without asking when the change fits existing
components, ADRs and verification IDs; the gate, not a human stop, checks it.
State detected facts first.
Batch the material questions once, with your recommended answer and the cost of
being wrong.
Continue independent work while a dependent action waits.
Record the answer in the contract, ADR or model so the next session does not ask again.

For every acceptance criterion, read the assertions and identify a success case,
a relevant failure case and behavior that must remain unchanged.
Map it to existing reviewed verification IDs.
Unsupported mappings and unresolved questions remain unknown.
New command definitions follow [authoring](authoring.md).

## Record the interpretation

Write `.archctl/change.yaml` using `archctl.change.v2` and actual repository IDs:

```yaml
schema_version: archctl.change.v2
id: checkout-key
objective: Refactor checkout keys while preserving payment behavior
scope:
  components: [orders, payments, ledger]
  excluded_components: []
  paths: [checks/**]
acceptance:
  - id: AC-01
    requirement: Repeating checkout records one payment
    checks: [checkout-integration]
constraints:
  decisions: [ADR-001]
  policies: [payment-isolation]
open_questions: []
```

Distinguish editable scope, impacted consumers and verification scope.
`scope.components` is the candidate scope; `scope.excluded_components` subtracts
from it. Overlap is allowed, and the final set must be nonempty. V1 requires
affected components even when their files are unchanged. Impact does not
authorize edits to every consumer.
`scope.paths` covers reviewed non-component files such as tests/docs;
it cannot override component ownership or exclusions.
Unknown IDs are errors.

The contract records interpretation, not enduring architecture authority or new commands.
Keep approval external to its schema; there is no `approved: true` field.
Intake is settled when every edited path and affected consumer is accounted for,
criteria have supported check mappings, and material questions are resolved.
