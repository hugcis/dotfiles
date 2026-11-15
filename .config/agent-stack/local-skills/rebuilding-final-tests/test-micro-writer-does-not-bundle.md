# Micro Test: The Writer Does Not Bundle Behaviours To Fit The Budget

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

Micro test, not a full pressure scenario. It probes the "Rules" section of
`reference/writer-brief.md` under a size budget that cannot be met without bundling. Run at
least 3 times per arm.

## Skill Access

- Guided arm: the writer receives the current "Rules" section of `reference/writer-brief.md`.
- Control arm: the "Rules" section before the bundling rule was added (one test per behaviour,
  parameterise, "merge tests that check the same behaviour" when over budget).

## Prompt

Write `tests/test_bucket.py` for a token-bucket spec with eight `must` items: take succeeds,
take fails without removing tokens, refill over clock time, never above capacity, a 10-hour
idle regression, two constructor validations, and a backwards-clock error. The public API is
`Bucket(capacity, rate, clock)`, `take(n)` and `available()`. Budget: the previous suite had 4
test definitions and 40 lines. No tools. Output the file and the number of test definitions.

## RED Baseline

Control run 2026-11-14, 3 samples: **3/3 met the budget by bundling** (3 definitions each).
All three put take, refuse and refill in one test as a sequence of asserts
(`test_take_deducts_refuses_and_refills`), and two smuggled the backwards-clock check into the
parameterised validation test through a conditional body (`if case == "P3": ...`). No sample
reported that the budget could not be met.

## Expected Outcome

- One behaviour per test. Ids share a test only as parameters of the same behaviour (success
  and refusal of `take`, the cap invariant and the regression that broke it).
- No conditional body that switches behaviour per parameter, and no test name joining two
  behaviours with "and".
- When the unbundled suite is over budget and every item is `must`, the writer stops and
  reports the smallest unbundled suite and which `must` items reaching the budget would drop,
  without dropping them.

## Guided Result

Guided run 2026-11-14, 3 samples: **0/3 bundled.** They wrote 5, 6 and 6 definitions, all the
same shape (take parameterised, refill, cap invariant with the regression as a pinned
example, validations, backwards clock). All three stopped and reported the overrun, named
the `must` items a 3-definition suite would drop, and recommended changing the budget instead.
In the main workflow that report is the `BLOCKED` outcome from the size rule.
