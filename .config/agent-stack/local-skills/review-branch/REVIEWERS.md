# Reviewer Contracts

## Common Contract

Every reviewer is read-only. Inspect the complete assigned diff and enough surrounding
code to understand it. Read direct callers and callees when contracts or behavior depend
on them. Do not assume the diff is correct merely because tests pass.

Return every noteworthy finding, including uncertain ones, but avoid cosmetic noise.
Use `review-finding-schema.md` for each finding; only the final-test audit lane returns
gate records instead. The schema gives the coordinator stable
IDs, fix eligibility, and verification hooks for deduplication and postfix validation.

Line numbers must be exact current lines verified by opening the file, never diff offsets
or estimates. Cite additional declarations or call sites when they establish the contract.
Use `blocker`, `high`, `medium`, or `low` severity and 0-100% confidence. Explicitly say
`No findings` when appropriate. Do not edit files.

## Correctness, Contracts, and Security

Look for broken invariants, wrong results, incomplete state transitions, caller/callee
contract violations, swallowed errors, partial failures, unsafe fallback, races, resource
leaks, compatibility regressions, and malformed-data handling. Where relevant, inspect
authorization, injection, secrets, unsafe parsing, trust boundaries, and concurrency.
Separate provable bugs from plausible risks.

## Spec

Compare the implementation with the supplied issue, PR, or specification. Find missing or
partial requirements, wrong implementations, and unrequested scope. Quote the relevant
spec text. For missing behavior, cite the nearest code location where it belongs.

## Standards

Read applicable `AGENTS.md`, `CLAUDE.md`, contribution guides, architecture decisions, and
local conventions. Report documented violations with the exact source rule. Distinguish
hard requirements from judgement calls and skip checks already enforced mechanically.

## Simplification and Reuse

Seek canonical helpers, duplicate logic, needless abstraction, nesting, branching, dead
code, mixed abstraction levels, unclear names, and wasteful work. Preserve behavior.
Prefer direct readable code over fewer lines. Structural reframings belong to the
architecture lane; this lane covers local cleanups.

## Comments

Apply `rationalizing-code-comments`: comments should explain why, not how.
Delete comments that narrate the code or explain obvious how. Keep or compress comments
that explain why: surprising constraints,
invariants, external contracts, compatibility, safety, or performance reasons.

## Tests, Edge Cases, and Performance

Check whether tests exercise meaningful behavior, regressions, boundary values, failures,
and changed contracts rather than implementation trivia. Identify missing focused tests.
Inspect algorithmic regressions, repeated work, excess allocation/I/O, serialized
independent work, unbounded growth, and operational failure modes. Avoid speculative
micro-optimization.

## Final-Test Audit

Use `auditing-final-tests` as the canonical procedure, exactly as written; this contract
deliberately does not restate its rubric, classification, or record format.

This lane returns the gate's records and outcome in place of schema findings. This review
is read-only, so compose only the gate's four-outcome interface:

- Return the complete per-test records the skill requires, one per added or changed test.
- `ACTION_REQUIRED` when any test still needs rework, a move, or deletion. Those actions
  are required and not applied; they belong to the owning writer.
- `BLOCKED` when scope or current test identity cannot be established, or when the required
  verification evidence is missing.
- `PASS` only when every changed test is Keep with no pending action and the required
  verification evidence already exists.
- `NOT_APPLICABLE` when no test changed in scope.

## Architecture and Thermo-Nuclear Maintainability

Use `thermo-nuclear-code-quality-review` as the canonical procedure; this contract
deliberately does not restate its rules, questions, or remedies. Only these adaptations
apply:

- Review the assigned diff or shard, not "the current branch".
- Report findings as schema records, not PR comments. Its tone and phrasing examples
  apply to `remedy`. Its preference for fewer, high-conviction comments means dropping
  nits, not substantive findings the Common Contract asks for.
- Report its presumptive blockers as `high`. Reserve `blocker` for correctness, security,
  or data-loss failures so maintainability does not mask them.
- Leave its test-volume rules to the tests and final-test audit lanes.
- Recommend an ambitious restructuring only when the path and the invariants it preserves
  are concrete; otherwise report the smell with `fix_eligibility: no` and name what is
  missing.

When two architecture reviewers run, they must not see or react to each other's
conclusions.
