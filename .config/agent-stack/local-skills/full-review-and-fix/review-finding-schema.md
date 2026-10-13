# Review Finding Schema

Use one record per noteworthy finding. The coordinator deduplicates records and
decides which ones are safe to fix.

```yaml
id: axis-short-slug
severity: blocker | high | medium | low
confidence: 0-100
axis: correctness | tests | final-test-audit | simplification | architecture | performance | spec
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
  eligible: yes | no | unknown
  reason: One sentence explaining whether this is safe for an automatic fix pass
verification: Focused command or inspection that would prove the fix
```

## Fix Eligibility Rules

Use `eligible: yes` only when the finding is independently confirmed, at least
90% confidence, behavior-preserving, contained in scope, and meaningfully
verifiable. Use `unknown` for product, API, migration, or design choices that
need a human decision. Use `no` for speculative, disputed, or broad findings.

## Coordinator Use

Normalize equivalent findings to one record. Keep rejected and deferred records
in the report with their reason so later review rounds do not rediscover the same
issue. Postfix validation should reference finding `id` values instead of asking
reviewers to re-review the entire diff.
