# Post-TDD Test Curation

Use this before committing or calling a TDD session complete.

**Core principle:** the final test suite is durable product documentation, not a transcript of how the implementation evolved.

## Quick audit

```bash
skills/test-driven-development/post-tdd-test-audit.sh [base-ref]
```

If running from another directory, invoke the script by absolute path. The script only lists candidate test files and prints the review prompts; it does not modify anything.

## Decision test

For every added or changed test, write one sentence:

> This test should still matter in six months because it protects ___ from regressing.

If you cannot fill the blank with a user-visible behavior, public/API contract, domain invariant, security/safety property, or historically important bug symptom, do not keep the test as-is.

## Keep / rework / delete

| Decision | Use when |
|---|---|
| **Keep** | It protects durable behavior, a public interface, an important edge case, or the actual bug symptom. |
| **Rework** | It is valuable but names temporary review feedback, asserts source text/AST shape, checks implementation structure, or lives in a catch-all artifact file. Move or rewrite it as behavior coverage. |
| **Delete** | It only proves a transient development step, reviewer appeasement, removed scaffolding, duplicated coverage, or "we changed this exact text/file" without a lasting contract. |

## Placement rule

Prefer domain-relevant test files over stabilization/graveyard files. A file like `test_review_feedback_stabilization.py` is usually a temporary development artifact; extract any durable behavior tests into the nearest domain test and delete the artifact if nothing durable remains.

## Completion rule

After deleting or reworking tests:
1. Run the focused tests that should still cover the behavior.
2. Run the relevant lint/type/compile check if test files or imports changed.
3. In the final summary, report tests kept, reworked, or deleted and why.
