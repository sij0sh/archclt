# Design judgment

Use this reference before writing a model or an obligation.
It tests whether a boundary is worth declaring and how strong the declaration
should be.
For a governed implementation, return to [change](change.md).
For a bootstrap, use [adoption](adoption.md).

## Where a boundary goes

A component owns a reason to change.
Draw the boundary where the owner, failure mode or rate of change differs.
The directory tree is a hint; behavior and ownership are the test.

Apply the deletion test:
if deleting the component would remove no complexity, it is a pass-through.
Merge it into its caller.
A module that only forwards calls adds a seam without adding leverage.

Group code that changes together and is verified together.
Split when one part can fail without the other, or when one part needs a
different check.
Keep the interface small and the implementation hidden.
Code that reaches through another component's state has crossed the boundary
without a contract.

A permission map is a maintenance cost.
Declare the fewest edges that express the constraints you enforce.
An optional relationship freezes an accepted edge; it does not describe every
possible call.

Declare an interface when a second consumer needs the same seam, or when a test
must cross it.
One implementation does not justify an interface.
Use the project's own names; a fuzzy term is a question for the operator.

When the choice is contested or expensive to undo, present two decompositions
with their trade-offs, then recommend one of the two.

## What to declare

Declare what you intend to keep and what you intend to prevent.
Prefer the weakest sufficient mechanism:

1. A test assertion for behavior one consumer must preserve.
2. A required verification command for a check every affected change must run.
3. A forbidden dependency for a direction that must not exist.
4. An optional relationship for an edge you accept but do not require.
5. ADR prose for a choice no current mechanism can enforce.

A test assertion is cheaper and more precise than a policy.
A policy is cheaper than a custom mechanism.
A declaration nothing can observe or execute is prose, not enforcement.
Archctl observes Python imports and runs reviewed commands.

Write an ADR when the choice is hard to reverse, surprising without context,
and the result of a real trade-off.
Otherwise record nothing.
An ADR that restates the code adds maintenance without adding intent.
Keep each decision under one ID and supersede it through review.

`required: true` is a promise that the edge continues to exist.
Make that promise only when you would defend it in review.
A permitted dependency is not required to persist.
A forbidden dependency is a hard guardrail; use it for the direction that must
never appear, not for every direction you dislike.

When a finding appears, fix the code or review the intent.
Add a declaration only when it states a constraint you intend to enforce.

## When to stop

Stop when the model covers the current change and the next reviewed change.
Add a component when a real change needs its ownership.
Add a relationship when an edge becomes consequential.
Add an ADR when a reviewer would otherwise re-litigate the choice.

Record nothing when the choice is easy to reverse, unsurprising, or forced by
the language or framework.
A smaller model with clear ownership beats a complete map nobody maintains.
