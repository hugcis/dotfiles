---
name: full-review-and-fix
description: Conduct a thorough multi-model code review in parallel, apply only high-confidence behavior-preserving fixes, and verify the result. Use when the user explicitly asks for a full, deep, or thorough review-and-fix pass over a worktree, branch, commit range, diff, or named files; ordinary read-only review requests should not trigger it.
---

# Full Review and Fix

Review broadly, fix conservatively. Preserve user changes and externally observable behavior.

## 1. Resolve the Scope

Honor an explicit target exactly. It may be a worktree, branch, commit/range, diff,
or file set. If none is given:

- A dirty worktree means staged, unstaged, and relevant untracked changes only.
- A clean worktree means the current branch against its merge-base with the
  inferred upstream/default branch.
- Ask one short question when the target or base is ambiguous.

For a target not currently checked out, create or reuse an isolated git worktree;
never switch the user's checkout. Pasted code not mapped unambiguously to workspace
files is review-only.

Capture the exact diff command/range, commit list, changed files, initial git status,
and applicable repository instructions. Discover intent from the user's prompt first,
then a readily identifiable PR, issue, or spec. Continue without a spec, but say so.
Trace generated, vendored, lock, and snapshot changes to canonical source; never edit
generated output directly without the documented generator.

## 2. Choose Review Mode

Pick the smallest mode that matches the user's request and the diff. Escalate only when
scope or risk justifies the cost.

- `quick`: tiny or mechanical diffs; one reviewer for blockers and obvious regressions.
- `standard`: ordinary feature or bugfix; correctness, tests, and simplification axes.
- `deep`: explicit full/deep/thorough request; use the complete reviewer set below.
- `wide`: large or multi-subsystem target; shard first, then run bounded waves.
- `postfix`: validate accepted finding IDs after a fix pass; do not rediscover polish.

Use `deep` when the user explicitly asks for full review-and-fix. Use `wide` only when
the target cannot be reviewed coherently as one unit.

## 3. Size and Shard the Review

Review the whole target when coherent. Shard by package or subsystem at roughly 2,000
changed lines, 25 files, or earlier when independent subsystems are obvious. Keep each
shard self-contained and include cross-shard interfaces where relevant. Run at most ten
subagents concurrently, using waves when needed. For `wide` mode, create a shard map
before dispatching reviewers.

## 4. Dispatch Read-Only Reviewers

Read [REVIEWERS.md](REVIEWERS.md). In one parallel dispatch per wave, launch:

1. `reviewer-alt-xhigh`: correctness, contracts, errors, security, concurrency.
2. `reviewer-alt`: simplification, reuse, standards, legibility.
3. `reviewer-fast`: tests, edge cases, performance, operational risks.
4. `reviewer-alt`: final-test audit using `auditing-final-tests`.
5. `reviewer-alt`: architecture and thermo-nuclear maintainability.
6. `reviewer-primary`: independent architecture and thermo-nuclear review.

Give every reviewer the exact scope, selected mode, shard map when present,
spec/context, applicable standards, and common contract from `REVIEWERS.md`. Require
findings to follow `review-finding-schema.md`. The final-test audit reviewer must receive
the full `auditing-final-tests` skill content or an exact summary of its workflow and
context-fit checks. Architecture reviewers must work independently. If these agents are
unavailable, stop and ask the user to restart your agent harness; do not silently
substitute models.

## 5. Adjudicate

The coordinator must independently open the cited current code and verify each finding.
Deduplicate overlap without hiding disagreement. Do not use majority vote. Resolve
conflicts from code, intent, standards, and tests; report material unresolved disputes.

Normalize reviewer output using `review-finding-schema.md`. Report every noteworthy
validated finding with severity, confidence, and finding ID. A finding is eligible for
automatic fixing only when all are true:

- confidence is at least 90% and the coordinator independently confirms it;
- the change preserves externally observable behavior and clear invariants;
- the scope is contained, including only necessary adjacent callers, helpers, or tests;
- focused verification can provide meaningful evidence;
- the recommendation is not disputed.

Do not auto-fix behavioral bugs, ambiguous design choices, API changes, migrations, or
product decisions. Report them for approval. Evidence-backed structural refactors are
allowed when they satisfy every condition above.

## 6. Fix Sequentially

Launch exactly one `coder-alt` with only the approved fix list, current code
context, local instructions, and verification plan. Recheck git status first. Never
overwrite concurrent/user changes or perform unrelated cleanup. Focused regression or
characterization tests are encouraged. Do not commit.

Run relevant focused tests plus formatter, linter, and type checks where practical. If a
check fails because of a fix, restore only that fix's own hunks, never reset whole files
or unrelated work, and leave the finding unresolved.

## 7. Verify and Stop

Re-run correctness plus only the reviewer roles whose finding IDs were fixed, against
the resulting diff. Apply at most one follow-up batch through the same single fixer: two
fix cycles maximum. Then stop even if additional opportunities remain.

## 8. Report

Lead with findings ordered by severity. For each, retain confidence, exact citations,
and mark `fixed`, `remaining`, `disputed`, or `verification failed`. Then summarize the
edits, checks and results, scope reviewed, and any residual risks or missing spec.
