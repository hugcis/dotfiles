---
name: review-branch
description: Multi-model code review of a branch, PR, commit range, worktree, diff, or files, with dedicated lanes for correctness, spec, standards, tests, performance, and architecture. Read-only by default; with an explicit request to fix, applies only high-confidence behavior-preserving fixes and re-verifies.
---

# Review Branch

Review broadly and report precisely. Read-only unless the user asked for fixes (step 5).
Never create commits or change branches in the user's checkout.

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

Capture the exact diff command/range, commit list, changed files, initial git status, and
applicable repository instructions. Trace generated, vendored, lock, and snapshot changes
to their canonical source. Discover intent from user context first, then a readily
identifiable linked PR, issue, or spec. Continue without a spec and say so.

## 2. Choose the Review Mode

Pick the smallest mode that matches the request and the diff. Escalate only when scope or
risk justifies the cost.

- `quick`: tiny or mechanical diffs; blockers and obvious regressions only.
- `standard`: the default when no `deep` trigger applies and the target can be reviewed
  as one unit, including an explicit request for a full review.
- `deep`: concrete security, concurrency, distributed-systems, or migration risk, broad
  API changes, or an explicit request for a deep review or the complete reviewer panel.
- `wide`: the target cannot be reviewed coherently as one unit. Shard by package or
  subsystem at roughly 2,000 changed lines, 25 files, or earlier for clearly independent
  areas. Include relevant cross-shard interfaces and write a shard map before dispatch.

"Full" means complete coverage of the relevant risks, not use of every reviewer.

## 3. Dispatch Read-Only Reviewers

Read [REVIEWERS.md](REVIEWERS.md). Give every reviewer the exact scope, selected mode,
shard map when present, commits, intent, standards sources, the Common Contract, and the
full `REVIEWERS.md` section for every axis its lane covers.
Require findings to follow [review-finding-schema.md](review-finding-schema.md). Give
read-only reviewers a bounded turn budget unless the caller already supplied one. Run at
most six reviewers concurrently, using waves when needed.

Lanes by mode:

- `quick`: one `reviewer-fast` covering blockers, regressions, and obvious test gaps,
  using the correctness and tests sections.
- `standard` with at most eight changed files and roughly 400 changed lines: one
  `reviewer-alt` covers correctness, spec, standards, simplification, comments, tests,
  and performance. Add `reviewer-alt-low` for architecture only when the diff adds new modules
  or abstractions.
- `standard` above that size: `reviewer-alt` for correctness, spec, standards,
  simplification, and comments; `reviewer-fast` for tests, edge cases, and performance;
  `reviewer-alt-low` for architecture.
- `deep`: the complete set below.
- `wide`: at most three risk-matched lanes per shard; do not repeat the complete set on
  every shard.

In `deep` mode, or when the user asks for it, launch a `reviewer-alt` final-test audit
lane when the scope adds or changes tests. Give it the latest CI or test-run results for
the changed tests when available.

The complete set is:

1. `reviewer-alt-xhigh`: correctness, contracts, errors, security, concurrency.
2. `reviewer-alt`: spec, standards, simplification, reuse, comments.
3. `reviewer-fast`: tests, edge cases, performance, operational risks.
4. `reviewer-alt`: final-test audit using `auditing-final-tests`.
5. `reviewer-alt`: architecture and thermo-nuclear maintainability.
6. `reviewer-primary`: independent architecture and thermo-nuclear review.

Two lanes compose a canonical skill instead of a summary:

- The final-test audit reviewer must receive the full canonical `auditing-final-tests`
  skill content, and must not restate or summarize its rubric.
- Every architecture reviewer must receive the full content of
  [thermo-nuclear.md](thermo-nuclear.md), pasted into the prompt.

Architecture reviewers must work independently and must not see each other's findings.
Drop the spec axis when no spec exists. If a named agent fails because its model is
unavailable, retry that lane once on another reviewer agent and name the substitution in
the report; stop only when no reviewer agent works.

## 4. Adjudicate

The coordinator must independently open every cited current file and verify the finding,
line numbers, and quoted source. Reject or correct findings that cannot be confirmed.
Deduplicate overlap without hiding material disagreement. Do not use majority vote;
adjudicate from code, intent, standards, and tests. Report unresolved disputes explicitly.

Keep every noteworthy validated finding, including uncertain concerns, with a confidence
score and finding ID. Suppress cosmetic noise. Convert each pending Rework or Delete
action from the final-test audit into a `final-test-audit` finding. Classify every
finding's `fix_eligibility.eligible` with the schema rules. Preserve the review axes so intent, correctness, and
maintainability do not mask each other.

## 5. Fix (only when asked)

Skip this step unless the user asked for fixes. Fix only findings with
`fix_eligibility.eligible: yes`; `decision` findings go under **Decisions needed**.
Launch one `coder-alt` with the approved list, in the worktree from step 1. It must not
overwrite concurrent changes or commit. Run the relevant tests and linters; revert only a
failing fix's own hunks. Re-review the result with one correctness lane plus one lane for
the other axes of the fixed findings. Two fix cycles at most, then stop.

## 6. Report

Lead with findings ordered by severity. Group them under:

- Correctness and Security
- Spec
- Standards
- Simplification and Comments
- Architecture and Maintainability
- Tests and Performance
- Final-Test Audit

Each finding must retain exact `path:line`, quote, severity, confidence, impact, evidence,
remedy, and fix eligibility. Mark disagreements and distinguish provable bugs from
plausible risks. State `No findings` for clean axes and `No spec available` when
applicable. Follow the findings with **Decisions needed**: one entry per `decision`
finding with its question, options, and recommendation.

End with the reviewed scope and commands, finding counts by severity and axis, the worst
confirmed issue, and residual risks or testing gaps. Include review-yield counts: reviewer
launches, findings raised, and findings accepted after adjudication. A failed or timed-out
reviewer counts as a launch and is reported.

Without a fix request, do not modify code even when a fix is obvious. With fixes, mark
every finding `fixed`, `decision needed`, `remaining`, `disputed`, `rejected`, or
`verification failed`, and list the checks run.
