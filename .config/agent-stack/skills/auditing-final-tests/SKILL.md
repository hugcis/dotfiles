---
name: auditing-final-tests
description: Use when finishing any workflow whose scope includes added or changed tests, including features, bug fixes, refactors, CI repairs, review fixes, and test-only changes.
---

# Auditing and Curating Final Tests

## Core Principle

The final test suite is **durable product documentation, not a transcript of implementation**.

For every added or changed test, complete:

> This test should still matter in six months because it protects ___ from regressing.

Passing tests, increased coverage, an earlier review, or development usefulness do not
satisfy this gate.

## Gate Outcomes

Return exactly one outcome:

- `NOT_APPLICABLE`: no tests were added or changed in scope.
- `PASS`: every changed test was audited, all curation actions were applied, and focused verification passed.
- `ACTION_REQUIRED`: at least one test must be reworked, moved, or deleted.
- `BLOCKED`: scope cannot be established or required verification cannot be performed.

`PASS` and `NOT_APPLICABLE` are the only completion-permitting outcomes for a writable workflow.

A read-only audit whose every changed test is **Keep** has no pending action, so it never
returns `ACTION_REQUIRED`. Return `PASS` only when the required final verification evidence
is already established and the record names who ran the exact commands and their results;
otherwise return `BLOCKED`. A read-only reviewer cannot run the verification itself, so that
evidence stays the owning writer's obligation and the parent workflow still verifies it
independently before completion.

## Required Record

Record this for **every added or changed test**:

| Field | Required content |
| --- | --- |
| File and test name | Path plus test name or parameterized definition |
| Durability statement | The completed six-month sentence |
| Classification | Keep, Rework, or Delete |
| Reason | Durable guarantee or test smell |
| Action | **Keep**: no action pending. Pending **Rework**/**Delete** in read-only: required — not applied. Applied **Rework**/**Delete** in writable: applied as retained, rewritten, moved, or removed |

Distinct test definitions require distinct records. One parameterized definition is one test.

## Classification

- **Keep:** protects durable behavior, a public contract, a distinct boundary or invariant, a safety/security property, or the actual bug symptom.
- **Rework:** valuable but coupled to source text, AST shape, filenames, private structure, temporary feedback, implementation details, duplicate examples, or the wrong suite or policy layer.
- **Delete:** proves only scaffolding, a transient checkpoint, reviewer appeasement, removed infrastructure, duplicate coverage, or an exact change without a lasting contract.

Keep exact strings, paths, flags, messages, serialization, and protocol details when exactness is itself the documented contract. Keep a precise regression when its symptom would be hard to diagnose from broader coverage.

Classify only from supplied evidence. Never infer an unseen implementation or body from a test name. A stated exact documented flag or string is **Keep** absent concrete evidence of non-contract coupling.

## Context and Curation

Read each changed test with its neighboring suite. Ask what the package owns and whether the test would survive a harmless implementation refactor.

- Merge duplicates unless each protects a distinct boundary.
- Parameterize repeated examples without hiding intent.
- Prefer properties or invariants when examples represent a general law.
- Exercise public behavior instead of private helpers when possible.
- Move durable checks into the relevant domain suite.
- Move repository-wide policy to policy, lint, or release checks.
- Extract durable coverage from stabilization or graveyard files, then remove the artifact.

A test can help during RED-GREEN development and still be wrong for the final suite.

## Gate Workflow

Never fabricate exact existing or proposed future destination paths or test names. Two
identity rules follow, and they carry different outcomes:

- **Unknown proposed destination:** describe it by ownership or domain and mark it
  unverified. An unverified destination does not block.
- **Unresolvable current identity:** when the exact path or test name of a changed test
  cannot be established, mark the identity unresolved and return `BLOCKED`.

1. Resolve the caller's exact diff or file scope and enumerate changed tests.
2. Return `NOT_APPLICABLE` when none changed.
3. Produce the required record for each changed test.
4. In a writable context, apply every Rework and Delete action.
5. In a read-only context, return any Rework/Delete findings as `ACTION_REQUIRED` to the
   owning writer.
   In read-only reports, action status must say required and not applied. Never claim
   retained, rewritten, moved, or removed as completed until a writer applied it.
6. **Reinspect** the final diff because curation can change the test set.
7. Repeat until the audit reaches a **fixed point** with no unresolved action.
8. Run focused verification plus relevant lint, type, or compile checks when test files or imports changed.
9. Return `PASS` only after the final changed-test set is fully audited and verification succeeds.

The parent workflow owns this gate after all delegated mutation waves. Child reports and audits performed before the last mutation are evidence, not completion.

## Report

Return the outcome, scope, complete per-test records, tests kept/reworked/deleted, verification commands and results, and residual risks. Never convert `ACTION_REQUIRED` or `BLOCKED` into a success claim because a deadline, green CI, coverage, or prior approval makes curation inconvenient.

Do not propose or present merge, ship, deploy, or human override as an alternate completion
path. A bypass decision is outside the gate, so report only the non-passing outcome and
required actions.
