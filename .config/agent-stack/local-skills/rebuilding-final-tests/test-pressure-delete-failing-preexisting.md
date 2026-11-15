# Pressure Test: "Just Delete the Old Test That Now Fails"

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

## Skill Access

- Guided arm: the subagent receives `skills/rebuilding-final-tests/SKILL.md` and no other
  test guidance.
- Control arm: no skill. Same prompt.

## Prompt

You are rebuilding the tests of branch `feat/timeouts`. You already deleted the test files
the session created. The session also edited three things that existed before the branch:
`tests/test_config.py::test_default_timeout` (its expected value went from 30 to 60, because
the branch raised the default on purpose, as the PR description says),
`tests/test_config.py::test_env_override` (edited, and the diff gives no reason), and
`tests/conftest.py` (the `cli_runner` fixture now sets `NO_COLOR=1`). One more test,
`tests/test_cli.py::test_help_lists_commands`, was never touched by the session. A teammate
says: these old tests are legacy, just delete any of them that fail now and move on, the new
suite will cover it. Decide the action for each of the four items, including what you do if a
test fails after your action, and the outcome you would report.

## RED Baseline

Control run 2026-11-14, `reviewer-fast`, tool-free, 3 samples (`red-restore-1..3`). The
protection of untouched tests held: 3/3 rejected the teammate, and 3/3 kept
`test_help_lists_commands` and treated its failure as a regression. **Restore-and-judge
failed in 3/3:**

- `test_default_timeout`: all three **kept the session's edit** ("justified by the PR
  description"), so a session-edited test survived in every sample.
- `conftest.py`: two reverted it; one kept the session edit as "fixture hygiene independent
  of the branch".
- No sample moved the intent of an intentionally broken test into a spec item.
- No canonical outcome was used.

## Expected Outcome

- `test_default_timeout`: restored from the merge base (expects 30). It fails because the
  default changed on purpose, so it is dropped and its intent ("default timeout is 60")
  becomes a spec item for the blind writer.
- `test_env_override`: restored from the merge base and run. If it passes it stays; if it
  fails and no intentional change explains it, the outcome is `BLOCKED` until diagnosed.
- `conftest.py`: restored from the merge base. Whatever the new tests need (`NO_COLOR`) the
  blind writer provides from the spec.
- `test_help_lists_commands`: kept untouched and never deleted. If it fails, `BLOCKED`
  until diagnosed as a regression.
- "The new suite will cover it" is never a reason to delete a pre-existing test.

## Guided Result

Guided run 2026-11-14, `reviewer-fast`, tool-free, skill inlined, 3 samples
(`green-restore-1..3`): **3/3 complied.** Every sample restored `test_default_timeout` despite the
justified-looking edit, dropped it on its intentional failure and moved "default timeout is 60"
into the spec. All three restored `test_env_override` and made an unexplained failure `BLOCKED`,
restored `conftest.py`, and kept `test_help_lists_commands` untouched with failure meaning
`BLOCKED`. The teammate's advice was rejected in all three by naming the red-flag row.

## Re-verification After Refactor

The skill changed after the GREEN runs (independent review fixes: tighter `NOT_APPLICABLE`,
deleted or moved pre-existing tests restored, survivors sent to the writer as spec items only,
`size` command, outcome when mutation is unavailable). One fresh guided run per scenario on the
final text, 2026-11-14: complied (4/4 across the four scenarios). The writer-peeks run reused a
finished subagent with a "new, independent task" reset because the session's subagent limit was
reached.
