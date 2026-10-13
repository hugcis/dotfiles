---
name: pr-feedback-watch-loop
description: Use when asked to repeatedly watch a PR, review thread, automated reviewer, CI check, or feedback loop until addressed, green, stopped, or blocked.
---

# PR Feedback Watch Loop

Use a scheduler or monitor as the controller. Each wake should do one bounded pass.

## Start the Loop

- Use `LoopCreate` for periodic review polling.
- Use `MonitorCreate` when a single long-running check command can notify on completion.
- Do not use raw shell sleep loops, `while sleep`, or ad hoc background polling.
- Record the PR, branch, commit, interval, max fires, and stop condition.
- Snapshot already-seen checks and feedback so old comments are not reprocessed.

## Wake Workflow

On each wake:

1. Fetch current PR/check/review state.
2. Identify only new or still-actionable feedback.
3. Route by type:
   - red check or failing job → use `ci-red-triage`
   - review comment or requested change → use `receiving-code-review`
   - response text needed → use `drafting-github-replies`
   - stale or conflicted branch → use `merging-main-resolving-conflicts`
   - completion claim → use `verification-before-completion`
4. Fix only validated issues that are in scope.
5. Run focused verification.
6. **Final-test gate:** Before this workflow completes, invoke `auditing-final-tests`
   over the workflow's full change scope. Continue only on `PASS` or `NOT_APPLICABLE`.
   Resolve `ACTION_REQUIRED`; report `BLOCKED` honestly.
7. Push only when requested or clearly part of the approved workflow.
8. Update loop state with what changed, what remains, and when to wake next.

## Stop Conditions

Stop or mark complete when checks are green and no actionable feedback remains, the user says to stop, the loop hits its max fires, or a human/product decision is needed. Do not delete a recurring loop after an unchanged wake; use the loop update mechanism.
