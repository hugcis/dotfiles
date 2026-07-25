---
name: review-branch
description: Perform a thorough read-only multi-model code review with dedicated agents for standards, spec compliance, soundness, tests, performance, and architecture. Use when the user asks to review a branch, PR, commit range, worktree, diff, or code changes without requesting edits or fixes.
---

# Review Branch

Review broadly and report precisely. This skill is strictly read-only: never edit files,
apply fixes, create commits, or change branches in the user's checkout.

## 1. Resolve the Scope

Honor an explicit target and base exactly. Targets may be a branch, PR, commit/range,
worktree, diff, or file set. For a branch comparison, use a three-dot diff against the
merge-base. Respect stacked branches: their parent branch, not `main`, is the base.

If no target is supplied:

- A dirty worktree means staged, unstaged, and relevant untracked changes only.
- A clean worktree means the current branch against its merge-base with the inferred
  upstream/default branch.
- Ask one short question when target or base is ambiguous.

For a target not checked out, use an isolated git worktree; never switch the user's
checkout. Pasted code not mapped to workspace files may be reviewed without citations to
workspace line numbers, but identify that limitation.

Capture the exact diff command/range, commit list, changed files, and applicable repository
instructions. Discover intent from user context first, then a readily identifiable linked
PR, issue, or spec. Continue without a spec and explicitly omit the Spec reviewer.

## 2. Size the Review

Review the complete target when coherent. Shard by package or subsystem at roughly 2,000
changed lines, 25 files, or earlier for clearly independent areas. Include relevant
cross-shard interfaces. Run at most ten subagents concurrently, using waves when needed.

## 3. Dispatch Dedicated Reviewers

Read [REVIEWERS.md](REVIEWERS.md). Give every reviewer the exact scope, commits, intent,
standards sources, and common output contract. Launch in one parallel dispatch per wave:

1. `reviewer-alt`: documented standards and local conventions.
2. `reviewer-alt`: spec compliance and scope, only when a spec exists.
3. `reviewer-alt-xhigh`: soundness, contracts, errors, security, concurrency.
4. `reviewer-fast`: tests, edge cases, performance, operational risks.
5. `reviewer-alt`: architecture and thermo-nuclear maintainability.
6. `reviewer-primary`: independent architecture and thermo-nuclear review.

Architecture reviewers must work independently and must not see each other's findings. If
the named agents are unavailable, stop and ask the user to restart your agent harness; do not
silently substitute models.

## 4. Adjudicate

The coordinator must independently open every cited current file and verify the finding,
line numbers, and quoted source. Reject or correct findings that cannot be confirmed.
Deduplicate overlap without hiding material disagreement. Do not use majority vote;
adjudicate from code, intent, standards, and tests. Report unresolved disputes explicitly.

Keep every noteworthy validated finding, including uncertain concerns, with a confidence
score. Suppress cosmetic noise. Preserve the review axes so intent, correctness, and
maintainability do not mask each other.

## 5. Report

Lead with findings ordered by severity. Group them under:

- Soundness and Security
- Spec
- Architecture and Maintainability
- Tests and Performance
- Standards

Each finding must retain exact `path:line`, quote, severity, confidence, impact, evidence,
and recommendation. Mark disagreements and distinguish provable bugs from plausible risks.
State `No findings` for clean axes and `No spec available` when applicable.

End with the reviewed scope and commands, finding counts by severity and axis, the worst
confirmed issue, and residual risks or testing gaps. Do not modify code even when a fix is
obvious; offer `full-review-and-fix` as a separate follow-up when useful.
