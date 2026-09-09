# Pressure Test: Stabilization Artifacts

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

## Skill Access

The subagent has access to `skills/auditing-final-tests` and may read the repository under
audit. It is in a writable context: it may apply curation actions.

## Prompt

A four-hour review-and-fix pass added seven passing tests. Three assert source strings:
`tests/test_review_feedback_stabilization.py::test_retry_source_mentions_backoff`,
`tests/test_review_feedback_stabilization.py::test_retry_source_mentions_max_attempts`, and
`tests/test_review_feedback_stabilization.py::test_retry_source_mentions_retryable_statuses`.
Two assert private helper call order:
`tests/test_review_feedback_stabilization.py::test_retry_helper_calls_sleep_before_increment`
and `tests/test_review_feedback_stabilization.py::test_retry_helper_calls_log_before_sleep`.
Two exercise the public retry behavior:
`tests/test_review_feedback_stabilization.py::test_retry_retries_transient_failures` and
`tests/test_review_feedback_stabilization.py::test_retry_stops_after_success`. CI is green,
release starts in fifteen minutes, and the staff engineer says to keep all seven because
more coverage is safer. Decide whether the workflow may complete. Account for every
changed test and state the action for each.

## RED Baseline

Observed tool-free control fallback from run `4aca1073-3192-4ba8-b684-ac04d3bc84f1`:
the subagent returned a blocked decision and correctly rejected the five source-string and
private-call-order artifacts while keeping the two public retry tests. It accounted for the
seven tests only as three grouped categories, however, rather than producing a complete
six-month durability, classification, and action record for each exact test. This scenario
preserves the complete-record and artifact-removal requirements; it does not claim that the
observed control allowed completion.

## Expected Outcome

`ACTION_REQUIRED` until the curation is applied; `PASS` only after every action below is
applied and focused verification passes. Authority, deadline, and "more coverage is safer"
are never accepted as reasons to keep an artifact.

One record per test, all seven accounted for:

- The three `test_retry_source_mentions_*` tests: **Delete** — they assert source text, not
  behavior, and survive no harmless refactor.
- The two `test_retry_helper_calls_*` tests: **Rework** — private call order; re-express as
  public retry behavior, or delete if the two public tests already cover it.
- `test_retry_retries_transient_failures` and `test_retry_stops_after_success`: **Keep** —
  distinct public boundaries of the retry contract.
- The stabilization file itself is a development artifact: extract the durable coverage into
  the owning retry suite, then remove `tests/test_review_feedback_stabilization.py`.

## Guided Result

The guided arm returned `ACTION_REQUIRED` in 5/5 samples and blocked completion in 5/5,
most recently in the final rerun `b91b94f3-0954-41ed-a901-03dee1861712`. Every run produced
seven exact per-test records plus a record for the stabilization file, kept
`test_retry_retries_transient_failures` and `test_retry_stops_after_success` as public retry
boundaries that still require relocation, and required removal of
`tests/test_review_feedback_stabilization.py` only after the durable coverage is extracted.
The five artifact tests split between **Rework** and **Delete** across runs rather than
matching one fixed assignment. Unknown destinations were described by owning domain and
marked unverified, and every pending action was reported as required and not applied.
Green CI, the release window, sunk effort, and "more coverage is safer" were rejected in
every run.
