---
name: full-review-and-fix
description: Conduct a thorough multi-model code review in parallel, apply only high-confidence behavior-preserving fixes, and verify the result. Use when the user explicitly asks for a full, deep, or thorough review-and-fix pass over a worktree, branch, commit range, diff, or named files; ordinary read-only review requests should not trigger it.
---

# Full Review and Fix

Review with `review-branch`, fix conservatively, and surface the decisions you must not
make. Preserve user changes and externally observable behavior.

## 1. Review

**REQUIRED SUB-SKILL:** Run `review-branch` steps 1-4 (scope, mode, dispatch, adjudicate)
exactly as written, with its `REVIEWERS.md` and `review-finding-schema.md`. Skip its
Report step; this skill reports after fixing. This skill adds one review mode, `postfix`,
defined in its own step 4.

An explicit "full" request still starts at `standard`: "Full" means complete coverage of
the relevant risks, not use of every reviewer.

Fixing adds three scope rules. Make fixes in the isolated worktree `review-branch` uses
for a target that is not checked out. Pasted code not mapped unambiguously to workspace
files is review-only. Fix generated output only through its documented generator.

## 2. Triage

Sort every adjudicated finding by `fix_eligibility.eligible`, classified with the schema
rules:

- `yes`: goes to step 3.
- `decision`: never fix. Report it under **Decisions needed** with its question, options,
  and recommendation.
- `no`: report as `remaining`, or `disputed` when reviewers disagree.

## 3. Fix Sequentially

Launch exactly one `coder-alt` with only the approved fix list, current code
context, local instructions, and verification plan. Recheck git status first. Never
overwrite concurrent/user changes or perform unrelated cleanup. Focused regression or
characterization tests are encouraged. Do not commit.

Run relevant focused tests plus formatter, linter, and type checks where practical. If a
check fails because of a fix, restore only that fix's own hunks, never reset whole files
or unrelated work, and leave the finding unresolved.

## 4. Verify and Stop

Re-run the review in `postfix` mode against the resulting diff: one correctness lane plus
at most one lane covering the other `axis` values of the fixed findings, using their
`REVIEWERS.md` sections. Validate those finding IDs rather than rediscovering polish.
`postfix` never launches the final-test audit lane; the gate below covers tests.
Apply at most one follow-up batch through the same single fixer: two fix cycles maximum.
Then stop even if additional opportunities remain.

After the final mutation wave, apply the **Final-test gate:** invoke `auditing-final-tests`
over the workflow's full change scope. Continue to reporting only
on `PASS` or `NOT_APPLICABLE`. Resolve `ACTION_REQUIRED`; report `BLOCKED` honestly. The
earlier read-only final-test reviewer does not replace this gate because later fixes may
add or alter tests. Gate Rework and Delete actions go through the same single fixer and
do not count against the two fix cycles; an action that needs a human choice stays
`ACTION_REQUIRED` and goes under **Decisions needed**.

## 5. Report

Use the `review-branch` step 5 report, including its **Decisions needed** section and its
review-yield counts, and mark every finding `fixed`, `decision needed`, `remaining`,
`disputed`, `rejected`, or `verification failed`. Add accepted findings that changed the final code
to the yield counts. Then summarize the edits, checks and results, and any check that
already failed before the fixes.
