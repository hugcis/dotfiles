---
name: ci-red-triage
description: Use when a branch, PR, build, test job, or CI check is red/failing and the user asks to diagnose, explain, rerun, or fix it.
---

# CI Red Triage

Find the failing evidence before changing code. A red check name is a symptom, not a root cause.

## Workflow

1. Do not guess from check names.
2. Resolve the exact branch, PR, commit, check, and failing job.
3. Fetch the exact failing job log or the closest available failure artifact.
4. Classify the failure:
   - code regression in the current diff
   - test failure unrelated to the current diff
   - flaky or nondeterministic failure
   - infrastructure, checkout, dependency, or network failure
   - stale branch or merge-main needed
   - unknown because evidence is incomplete
   Before calling a failure flaky, check whether it is in code the diff touches. A failure
   in untouched code usually means a stale base: check `git merge-base --is-ancestor` against
   the current base. A flake earns at most one fresh run; an identical second failure is not
   a flake, so read the logs instead of retrying.
5. If it is a code regression, reproduce or narrow locally before fixing.
6. If it is external, stale, flaky, or unknown, report evidence and the next action instead of editing blindly.
7. After any fix, run focused verification and summarize the command output.
8. **Final-test gate:** Before this workflow completes, invoke `auditing-final-tests`
   over the workflow's full change scope. Continue only on `PASS` or `NOT_APPLICABLE`.
   Resolve `ACTION_REQUIRED`; report `BLOCKED` honestly.

## Output

Report:

- failing check/job and source of evidence
- classification and confidence
- root cause or missing evidence
- fix applied or recommended next action
- verification run and result

## Guardrails

Do not rerun, cancel, or restart jobs unless the user asked or the repo instructions allow it. Do not claim the branch is green from a partial check.
