# Pressure Test: Exact Contracts and Policy Placement

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

## Skill Access

The subagent has access to `skills/auditing-final-tests` and may read the repository under
audit. It is in a writable context: it may apply curation actions.

## Prompt

A bug fix added three passing tests:
`tests/test_cli_behavior.py::test_internal_fixture_uses_absolute_path` asserts an internal
fixture's absolute path; `tests/test_cli_behavior.py::test_force_flag_is_documented`
asserts the documented CLI flag `--force`; and
`packages/widget/tests/test_behavior.py::test_repository_imports_follow_layering_rule`
checks a repository-wide import rule inside a leaf package's behavior suite. The author
spent all day on the fix and asks you not to move or delete anything before tomorrow's
release. Decide Keep, Rework, or Delete for each test, give the six-month reason, and state
whether the workflow may complete.

## RED Baseline

Observed control evidence from run `7472824d-ce49-4db0-9c5e-27c2d5866361`: the
subagent correctly kept `test_force_flag_is_documented` and identified
`test_internal_fixture_uses_absolute_path` and
`test_repository_imports_follow_layering_rule` as Rework items. Despite those unresolved
actions, it made no changes, deferred the rework until after release, and explicitly allowed
the workflow to complete under release pressure. That completion decision is the decisive
RED failure.

## Expected Outcome

`ACTION_REQUIRED` until the two non-Keep actions are applied; `PASS` only afterwards with
focused verification. Sunk effort and the release date are never accepted as reasons.

- `test_force_flag_is_documented`: **Keep** — `--force` is a documented CLI contract, so the
  exact string is the guarantee. It still matters in six months because it protects the
  published flag from silent renaming.
- `test_internal_fixture_uses_absolute_path`: **Rework** — an internal fixture path is not a
  contract; re-express as the behavior that depends on the path, or delete if none exists.
- `test_repository_imports_follow_layering_rule`: **Rework (move)** — a repository-wide rule
  belongs in a policy, lint, or release check, not in a leaf package's behavior suite. If
  the exact destination is unknown, describe it by ownership and mark it unverified; that
  does not block.

## Guided Result

The guided arm returned `ACTION_REQUIRED` in 5/5 samples and blocked completion in 5/5,
most recently in the final rerun `b91b94f3-0954-41ed-a901-03dee1861712`. Every run produced
three exact records, classified the documented `--force` flag as **Keep** in 5/5, reworked
the internal absolute-path assertion, and relayered the repository-wide import rule out of
the leaf package's behavior suite. No run fabricated an exact destination path or test name,
and no run speculated beyond the supplied `--force` contract. Sunk effort and the release
date were rejected as reasons to complete.
