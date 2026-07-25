# Reviewer Contracts

## Common Contract

Every reviewer is read-only. Inspect the complete assigned diff and enough surrounding
code to understand it. Read direct callers and callees when contracts or behavior depend
on them. Do not assume the diff is correct merely because tests pass.

Return every noteworthy finding, including uncertain ones, but avoid cosmetic noise.
Use this structure for each finding:

```text
[severity] Short title (confidence: NN%)
path/to/file.py:START-END
Quote: exact relevant current source lines
Impact: concrete failure or maintenance cost
Evidence: why this follows from code, spec, or repository rules
Remedy: smallest sound correction or structural reframing
Auto-fix: yes/no, with one-sentence justification
```

Line numbers must be exact current lines verified by opening the file, not diff offsets or
estimates. Cite additional declarations or call sites when they establish the contract.
Use `blocker`, `high`, `medium`, or `low` severity. Confidence is 0-100%. Explicitly say
`No findings` when appropriate. Do not edit files.

## Correctness, Contracts, and Security

Look for broken invariants, wrong results, incomplete state transitions, caller/callee
contract violations, error swallowing, partial failures, unsafe fallback, races, resource
leaks, compatibility regressions, and malformed-data handling. Where relevant, inspect
authorization, injection, secrets, unsafe parsing, trust boundaries, and concurrency.
Separate provable bugs from plausible risks.

## Simplification, Reuse, and Standards

Read applicable `AGENTS.md`, `CLAUDE.md`, contribution guides, and local conventions.
Seek canonical helpers, duplicate logic, needless abstraction, nesting, branching, dead
code, mixed abstraction levels, unclear names, and wasteful work. Preserve behavior.
Prefer direct readable code over fewer lines. Flag both local cleanups and code-judo moves
that delete concepts or special cases.

## Tests, Edge Cases, and Performance

Check whether tests exercise meaningful behavior, regressions, boundary values, failures,
and changed contracts rather than implementation trivia. Identify missing focused tests.
Inspect algorithmic regressions, repeated work, excess allocation/I/O, serialized
independent work, unbounded growth, and operational failure modes. Avoid speculative
micro-optimization.

## Architecture and Thermo-Nuclear Maintainability

Challenge the implementation shape, not just its style. Look for a reframing that removes
branches, modes, helpers, layers, or state. Flag spaghetti growth, scattered feature
checks, wrong ownership/layer, leaky boundaries, weak type models, non-atomic updates,
thin wrappers, magic behavior, and files pushed toward or beyond 1,000 lines. Prefer
deleting complexity over moving it. Recommend ambitious restructuring only when the path
and preserved invariants are concrete.

The Sol and Opus architecture reviewers must not see or react to each other's conclusions.
