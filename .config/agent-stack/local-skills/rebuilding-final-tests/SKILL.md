---
name: rebuilding-final-tests
description: Use when the implementation of a branch or development phase is finished and the session added or changed tests, before auditing-final-tests, or when asked to rebuild, rewrite or reset a branch's tests from first principles.
---

# Rebuilding Final Tests

## Core Principle

Tests written during development helped write the code, not protect it. When the phase is done,
**every test the session wrote is deleted and rebuilt** from a spec of what the code must do, by
a writer who never saw the old tests. The rebuild must then prove it is smaller and not weaker.

Violating the letter of these rules is violating their spirit. A reviewer's approval, test
quality, a deadline or sunk effort never exempts a session test from deletion.

## Gate Outcomes

Return exactly one:

- `NOT_APPLICABLE`: the session created, edited, deleted or moved no test file, fixture,
  helper or test data; or the session suite counts at most 2 test definitions **and** at most
  40 lines (`size`, below), and the session created, edited, deleted or moved no fixture,
  helper or test data. Record the counts and go straight to `auditing-final-tests`.
- `REBUILT`: all pass criteria hold, the mutation check ran on every changed code file
  (`baseline` and `compare` exit 0), and every surviving mutant has a test.
- `REBUILT_WITH_GAPS`: all pass criteria hold except that some surviving mutants are accepted
  with a recorded reason, or the mutation check was unavailable or partial and the fallback
  below is recorded.
- `BLOCKED` in every other case. Examples: the new suite is not strictly smaller, kills fewer
  mutants, a restored or untouched test fails for an unclear reason, the suite cannot run, or
  the fallback was not done.

Every outcome except `BLOCKED` hands off to `auditing-final-tests`, which stays the
per-test gate. This skill never replaces it.

## Scope

The session is the diff against `git merge-base <target> HEAD` (target default
`origin/main`), or against an explicit start commit for multi-phase branches.

| What the session did | Action |
| --- | --- |
| Created a test, test file, fixture, helper, `conftest.py` or test data | Delete it |
| Edited anything under test paths that existed at the merge base | Restore the merge-base version, then run it |
| Deleted, moved or renamed anything under test paths that existed at the merge base | Restore it at its merge-base path, then run it. A deletion never counts as shrinking |
| Did not touch a pre-existing test | Keep it unchanged. Never delete it, even if it fails |

Restore even when the edit looks justified (for example, a default the PR changed on
purpose). A restored test that then fails **because behaviour changed on purpose** is
dropped, and what it protected becomes a spec item. A restored test that fails for any
other reason, and any untouched test that fails, is `BLOCKED` until diagnosed. It is
evidence of a regression, not a cleanup target.

## Workflow

Work in the branch's own worktree or a scratch copy. Keep `TEST_SPEC.md`, mutation results
and notes outside the repo: `~/docs/<project>/test-specs/<branch>-*`.

1. **Scope.** List session-created, edited, deleted and moved test files, and the changed
   production lines. Measure the session suite size (see Size).
2. **Mine** before deleting anything. Read the code, PR description, commit messages and the
   session tests. Write `TEST_SPEC.md` from `reference/test-spec-template.md`. Every bug a
   session test caught and every bug fixed in the session becomes a `must` regression item.
3. **Baseline.** With the session tests still present:
   `python3 <skill>/scripts/mutation_compare.py baseline --base <target> --tests <focused test paths> --out <spec dir>/<branch>-baseline.json`.
   Use the focused test paths of the touched package, never the whole monorepo. Keep the
   default budget (`--max-minutes 20`) or set `--max-mutants`; over budget the script draws one
   seeded sample and saves it, so compare runs the same mutants. If the session tests were
   already deleted, take the baseline in a scratch worktree at HEAD where they still exist.
   Pass `--test-glob` when test files do not follow `tests/`, `test_*.py` or `*_test.py`, so
   no production file is excluded by name. If one session test passes under plain pytest but
   fails under mutmut's harness, deselect it with `--pytest-args '--deselect <id>'` and report
   it: the baseline is then weaker by that test.
4. **Delete and restore.** Delete session-created test files, fixtures, helpers and test
   data. `git checkout <merge-base> -- <edited, deleted or moved test paths>`. Run the
   remaining suite and apply the restore rules above.
5. **Blind rewrite.** Generate the public API with
   `python3 <skill>/scripts/public_api_digest.py <package dir> --consumers <repo root> --out <spec dir>/<branch>-PUBLIC_API.md`.
   It lists what the package exports, what entry points name, what production code elsewhere
   imports, and the types their signatures need. Add a test helper module the package ships
   for callers with `--public <module>`. Never add a module just because a test imports it.
   Spawn a fresh subagent with no inherited context, using `reference/writer-brief.md`
   verbatim with its placeholders filled. It receives only `TEST_SPEC.md`, that digest, the
   repo's test conventions and fixtures that exist at the merge base, and the size budget.
   Never pass it deleted tests, fixtures or helpers, in whole or in part, private modules, git
   history, or your own summary of the old tests. A fixture the old suite had is rebuilt by the
   writer from the spec, or the item is reported back as untestable through the public API.
6. **Verify.** The new suite and the untouched tests pass; lint and type checks pass on the
   test files. Run
   `python3 <skill>/scripts/mutation_compare.py compare --baseline <spec dir>/<branch>-baseline.json --out <spec dir>/<branch>-compare.json`.
   Fill the coverage table: every `must` item → at least one test, every test → an item.
7. **Close survivors.** For each mutant the new suite misses, either translate it into an
   observable behaviour, add that as a spec item (or sharpen an existing one), and send only the
   new spec items back to the same blind writer; or record why it is acceptable (equivalent
   mutant, logging-only line). Never send the writer a mutant diff, file or line number: they
   expose the implementation. Re-run compare.
8. **Hand off** to `auditing-final-tests`, then report.

Do not change production code between baseline and compare: the script refuses (exit 2)
because the mutants would differ. Record any production bug the rebuild finds and fix it
after the compare, under `auditing-final-tests`.

## Pass Criteria

1. The new suite and untouched pre-existing tests pass, with lint and type checks.
2. The coverage table maps every `must` item to a test and every new test to an item.
3. **Mutation:** on the same mutant ids, the new suite kills at least as many as the
   baseline (`compare` exits 0). Every survivor has a test or a recorded reason.
4. **Size:** the new suite has strictly fewer test definitions **and** strictly fewer lines
   than the session suite. Not shrinking is `BLOCKED` until the suite is merged,
   parameterised or cut. Never accept it with a reason.

## Size

Use `mutation_compare.py size`. In each test file under the paths you give, it compares every
unit with the merge-base version of the file. A unit is a top-level statement (a test, fixture,
helper, constant or import) or a class method. A unit whose source is new or edited counts in
full: its lines, from decorator to last line, and one test if it is a test function. One
parameterised definition is one test. Untouched and restored units count zero, and blank lines
between units never count. Give the same paths both times: every test directory plus any
fixture, helper or data path the session touched. Non-Python test files count as whole files
and pattern-matched tests, and the output flags them as approximate.

```bash
S=<skill>/scripts/mutation_compare.py
python3 $S size --base <target> --paths <test paths> --rev worktree --out <spec dir>/<branch>-size-session.json   # step 1, before deleting
python3 $S size --base <target> --paths <test paths> --out <spec dir>/<branch>-size-new.json \
  --against <spec dir>/<branch>-size-session.json                                                                # step 6; exit 1 = BLOCKED
```

Use `--rev worktree` in step 1 so uncommitted session tests count. Pass the session size to the
blind writer as its budget, and let it run the `--against` command itself.

## Mutation Unavailable

`baseline` exits 3 when no engine supports the changed code files (the Rust and JS/TS hooks
are stubs), the changed lines produce no mutants, or mutmut cannot run. It also exits 3 with
status `partial` when some changed code files were mutated and others were not: compare still
runs, and its kill count must still not drop. For every file the mutation check did not
cover, compare line and branch coverage of the changed lines for both suites, and have an
independent reviewer subagent name a realistic bug the new suite would miss. The report says
**"mutation check unavailable"** (or "partial", naming the files). It never claims criterion 3
passed, and the outcome is at best `REBUILT_WITH_GAPS`. Coverage parity alone never stands in
for the mutation check when the script can run. "Too slow" is answered with `--max-mutants`
or `--max-minutes`, never by skipping.

## Red Flags

| Rationalization | Reality |
| --- | --- |
| "These session tests are already excellent, keep them" | No session test survives. Good ones are cheap to rebuild from the spec |
| "A reviewer already approved them" | Approval is not an exemption |
| "The edit to the old test is justified by the PR" | Restore it anyway; if it fails on purpose, drop it and move its intent to the spec |
| "Delete the old tests that fail now" | Untouched tests are never deleted; a failure is a regression signal |
| "Let the writer copy the old fixture, it saves an hour" | The writer stays blind. Fixtures carry the old suite's assumptions |
| "Give the writer the private module so it understands" | Public API only. Untestable items go back as spec gaps |
| "Mutation testing is slow, coverage is the same" | Changed lines only, with budget and seed. Otherwise report it unavailable |
| "Same size is fine, the new tests are better" | Strictly fewer tests and lines, or `BLOCKED` |
| "Fold these behaviours into one test to fit the budget" | One behaviour per test. A suite that cannot shrink without bundling is `BLOCKED` |

## Report

- Outcome, and the path to `TEST_SPEC.md`.
- Scope: changed production files and line ranges (printed by `baseline`), session tests
  deleted, pre-existing tests restored, restored tests dropped with the spec item that
  replaced each, and any test deselected from the baseline.
- Before and after: test definitions, lines of test code, mutants killed out of total (with
  seed if sampled), coverage of the changed lines.
- The coverage table, and the survivor list with each disposition.
- Then the `auditing-final-tests` outcome.
