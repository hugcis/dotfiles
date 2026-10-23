# Review Finding Schema

Use one record per noteworthy finding. The coordinator deduplicates records and
classifies each one for fixing, even in a read-only review.

```yaml
id: axis-short-slug
severity: blocker | high | medium | low
confidence: 0-100
axis: correctness | spec | standards | simplification | comments | tests | final-test-audit | architecture | performance
location:
  path: path/to/file.ext
  start_line: 1
  end_line: 1
title: Short title
quote: Exact current source lines or empty when not file-local
impact: Concrete failure, risk, or maintenance cost
evidence: Why this follows from code, spec, tests, or repository rules
remedy: Smallest sound correction or structural reframing
fix_eligibility:
  eligible: yes | decision | no
  reason: One sentence explaining the classification
  question: For `decision` only, the choice the user must make, its options, and a recommendation
verification: Focused command or inspection that would prove the fix
```

## Fix Eligibility Rules

- `yes` only when all are true:
  - confidence is at least 90% and the coordinator independently confirms it;
  - the change preserves externally observable behavior and clear invariants;
  - the scope is contained, including only necessary adjacent callers, helpers, or tests;
  - focused verification can provide meaningful evidence;
  - the remedy is not disputed.

  Evidence-backed structural refactors qualify only when they meet every condition.
- `decision`: a behavioral bug, product or API choice, migration, or ambiguous design
  choice that needs a human. Fill `question`.
- `no`: speculative, disputed, or too broad to fix safely.

## Coordinator Use

Normalize equivalent findings to one record. Keep rejected and deferred records
in the report with their reason so later review rounds do not rediscover the same
issue. Postfix validation should reference finding `id` values instead of asking
reviewers to re-review the entire diff.
