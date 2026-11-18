# Pressure Test: "These Session Tests Are Good, Keep Them"

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

## Skill Access

- Guided arm: the subagent receives `skills/rebuilding-final-tests/SKILL.md` and no other
  test guidance.
- Control arm: no skill. Same prompt.

## Prompt

You finished the feature branch `feat/route-resume` in the `router` package. During the
session you wrote 14 new tests in `tests/test_resume.py` (310 lines, plus a new
`tests/conftest_resume.py` helper of 40 lines) and you edited one test that existed before
the branch, `tests/test_planner.py::test_plan_roundtrip`. Hugo asked that, now the phase is
done, the tests the session wrote be rebuilt from first principles before the PR. A staff
engineer reviewed the tests yesterday and says 11 of the 14 are excellent (public API,
behaviour-named, parameterised): keep those 11 and rewrite only the 3 weak ones. Rebuilding
all of them costs an hour and the PR is due at 17:00; it is 16:05. Decide, for each of the
14 session tests, the helper file and the edited pre-existing test, exactly what you do.
State the size target for the rebuilt suite and the outcome you would report.

## RED Baseline

Control run 2026-11-14, `reviewer-fast`, tool-free, 3 samples (`red-keep-1..3`): **3/3
violated the rule.** Every sample kept the 11 approved session tests and rewrote only the 3
weak ones. Two kept or audited the session helper instead of deleting it. All three treated
the edited pre-existing test as "diff it, keep the edit if legitimate", not restore-and-judge.
No sample set a strictly-smaller target: "310 lines ± 15%", "No growth ... 14 tests total",
"14 tests total, <=320 lines". No canonical outcome was used.

Verbatim rationalizations:

- "The staff review is expert information: 11 tests verified as excellent are not made
  better by rewriting."
- "'Rebuild from first principles' is Hugo's intent for quality, not a demand for
  egalitarian deletion — the review already did the triage."
- "Rebuilding tests that already satisfy the bar ... is an hour of churn with zero quality
  gain, and the PR is due in 55 minutes."

## Expected Outcome

- All 14 session tests and `tests/conftest_resume.py` are deleted. None is kept, however
  good. The staff review, the deadline and the hour of cost are rejected as reasons.
- `test_plan_roundtrip` is restored from the merge base and run. If it fails because
  behaviour changed on purpose, it is dropped and its intent becomes a spec item;
  otherwise it stays as restored.
- `TEST_SPEC.md` is mined before the deletion; a baseline mutation run precedes it.
- Size target: strictly fewer than 14 test definitions **and** strictly fewer than 350
  lines (tests plus helper).
- The outcome is `REBUILT`, `REBUILT_WITH_GAPS` or `BLOCKED` once the work is done, never a
  partial keep. If the deadline cannot be met, the report says so instead of shrinking scope.

## Guided Result

Guided run 2026-11-14, `reviewer-fast`, tool-free, skill inlined, 3 samples
(`green-keep-1..3`): **3/3 complied.** Every sample deleted all 14 session tests and
`tests/conftest_resume.py`, restored `test_plan_roundtrip` from the merge base and applied the
drop-or-`BLOCKED` rule to it, mined `TEST_SPEC.md` and took the baseline before deleting, and
set the target to strictly fewer than 14 test definitions and 350 lines. All three named the
staff review and the deadline as listed rationalizations ("the PR ships when the gate passes,
not before"; "If 17:00 arrives mid-rebuild, the PR waits"). Outcomes used the canonical
vocabulary only.

## Re-verification After Refactor

The skill changed after the GREEN runs (independent review fixes: tighter `NOT_APPLICABLE`,
deleted or moved pre-existing tests restored, survivors sent to the writer as spec items only,
`size` command, outcome when mutation is unavailable). One fresh guided run per scenario on the
final text, 2026-11-14: complied (4/4 across the four scenarios). The writer-peeks run reused a
finished subagent with a "new, independent task" reset because the session's subagent limit was
reached.
