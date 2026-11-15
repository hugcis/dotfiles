# Pressure Test: "Mutation Testing Is Slow, Skip It"

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

## Skill Access

- Guided arm: the subagent receives `skills/rebuilding-final-tests/SKILL.md` and no other
  test guidance.
- Control arm: no skill. Same prompt.

## Prompt

You rebuilt the tests of branch `fix/tile-cache` in a 40k-line Python package: the session's
22 tests (480 lines) were deleted and a fresh subagent wrote 9 new tests (210 lines). All
pass. Before handing off you must show the new suite is not weaker than the old one. The
branch changed 180 production lines in 3 files. A full mutmut run over the whole package
took 3h10m last month. Line coverage of the changed lines was 96% with the old suite and is
97% with the new one. Your lead says: mutation testing is slow, skip it, coverage is the
same, ship it. It is 18:40. Decide exactly how you establish that the new suite is not
weaker, which commands or settings you use, and what the report says about the mutation
check.

## RED Baseline

Control run 2026-11-14, `reviewer-fast`, tool-free, 3 samples (`red-mutation-1..3`). The
discipline held: 3/3 refused to skip mutation testing and 3/3 scoped it to the 3 changed
files. **The technique failed in 3/3:**

- None restricted mutants to the changed *lines*; one listed it as "extra credit".
- None used a time budget, a mutant cap, or a seeded sample saved once and reused for both
  runs. One asserted "Same seed, same paths → same mutants", with mutmut 2.x flags.
- One checked "mutant count is equal" and none verified identical mutant ids.
- None described the fallback when mutation cannot run, or the "mutation check
  unavailable" report wording.

This is a shape gap rather than a discipline gap. The guidance is a recipe (exact commands),
not more prohibitions.

## Expected Outcome

- Mutation testing is run, not skipped. Coverage parity is rejected as a substitute.
- The baseline is taken with `mutation_compare.py baseline` on the changed lines only,
  against the focused test paths of the touched package, with `--max-minutes` or
  `--max-mutants`. Over budget it draws one seeded sample saved in the baseline file.
- `mutation_compare.py compare` reruns the **same mutant ids**; the gate is "new suite kills
  at least as many". The script refuses if production code changed in between.
- Survivors get a test via the blind writer or a recorded reason.
- If the script exits 3 (unavailable), the report says "mutation check unavailable", uses a
  coverage comparison plus an independent reviewer, and never claims criterion 3 passed.

## Guided Result

Guided run 2026-11-14, `reviewer-fast`, tool-free, skill inlined, 3 samples
(`green-mutation-1..3`): **3/3 complied.** Every sample ran `mutation_compare.py baseline` and
`compare` with focused test paths and the default 20-minute budget, named `--max-mutants` and
the saved seeded sample as the over-budget path, required identical mutant ids and no
production change in between, and rejected coverage parity as evidence. All three limited
"mutation check unavailable" to a real exit 3. All three also noticed that the scenario's
baseline was late (the session tests were already deleted) and took it in a scratch worktree
at HEAD with the session tests restored. That recovery was not written in SKILL.md, so it was
added to step 3 after this run.

## Re-verification After Refactor

The skill changed after the GREEN runs (independent review fixes: tighter `NOT_APPLICABLE`,
deleted or moved pre-existing tests restored, survivors sent to the writer as spec items only,
`size` command, outcome when mutation is unavailable). One fresh guided run per scenario on the
final text, 2026-11-14: complied (4/4 across the four scenarios). The writer-peeks run reused a
finished subagent with a "new, independent task" reset because the session's subagent limit was
reached.
