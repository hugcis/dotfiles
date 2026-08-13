# Reviewer Contracts

## Common Contract

Every reviewer is read-only. Inspect the full assigned diff and enough surrounding code to
understand it. Read direct callers and callees when behavior or contracts depend on them.
Do not assume code is correct merely because tests pass.

Return every noteworthy finding, including uncertain ones, but avoid cosmetic noise.
Use `../full-review-and-fix/review-finding-schema.md` for each finding. The schema gives
the coordinator stable IDs, fix guidance, and verification hooks for deduplication.

Line numbers must be exact current lines verified by opening the file, never diff offsets
or estimates. Cite declarations and call sites when they establish the contract. Use
`blocker`, `high`, `medium`, or `low` severity and 0-100% confidence. Explicitly say
`No findings` when appropriate. Do not edit files.

## Standards

Read applicable `AGENTS.md`, `CLAUDE.md`, contribution guides, architecture decisions, and
local conventions. Report documented violations with the exact source rule. Distinguish
hard requirements from judgement calls and skip checks already enforced mechanically.

## Spec

Compare the implementation with the supplied issue, PR, or specification. Find missing or
partial requirements, wrong implementations, and unrequested scope. Quote the relevant
spec text. For missing behavior, cite the nearest code location where it belongs.

## Soundness and Security

Look for broken invariants, wrong results, incomplete state transitions, caller/callee
contract violations, swallowed errors, partial failure, races, leaks, malformed-data
handling, and compatibility regressions. Where relevant, inspect authorization, injection,
secrets, unsafe parsing, trust boundaries, and concurrency. Separate provable bugs from
plausible risks.

## Comments

Apply `rationalizing-code-comments`: comments should explain why, not how.
Delete comments that narrate the code or explain obvious how. Keep or compress comments
that explain why: surprising constraints,
invariants, external contracts, compatibility, safety, or performance reasons.

## Tests, Edge Cases, and Performance

Assess whether tests cover meaningful behavior, regressions, boundaries, and failures.
Identify missing focused tests. Inspect algorithmic regressions, repeated work, excess
allocation or I/O, serialized independent work, unbounded growth, and operational risks.
Avoid speculative micro-optimization.

## Architecture and Thermo-Nuclear Maintainability

Challenge the implementation shape. Seek reframings that remove branches, modes, helpers,
layers, or state. Flag spaghetti growth, scattered feature checks, wrong ownership, leaky
boundaries, weak type models, non-atomic updates, thin wrappers, magic behavior, duplicate
canonical logic, and files pushed toward or beyond 1,000 lines. Prefer deleting complexity
over moving it. Recommend ambitious restructuring only when the path and preserved
invariants are concrete.

The Sol and Opus architecture reviewers must not see or react to each other's conclusions.
