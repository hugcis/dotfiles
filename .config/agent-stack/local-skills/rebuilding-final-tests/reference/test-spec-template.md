# TEST_SPEC: <branch>

Location: `~/docs/<project>/test-specs/<branch>-TEST_SPEC.md`. Never commit it.

- Target and merge base: `<target>` at `<sha>`
- Changed production files: `<path>` ...
- Session suite (before): `<N>` test definitions, `<L>` lines of test code, over `<test paths>`
- Sources mined: code, PR description, commit messages, session tests, review threads

Each item has an id, a priority (`must` or `optional`) and a suggested level (`unit`,
`integration`, `e2e`). Describe observable behaviour through public entry points. Never name a
private helper, a mock or an internal data structure. The writer only sees this file and the
public API.

## Features

Observable behaviour of each public entry point the session added or changed (function,
class, CLI, config option, API route).

| id | priority | level | entry point | given / when / then |
| --- | --- | --- | --- | --- |
| F1 | must | unit | `pkg.mod.func(x, y)` | given ..., when ..., returns / raises / writes ... |

## Invariants

Properties that hold for every valid input: round trips, idempotence, ordering, determinism
under a seed, conservation, monotonicity. Name the input domain so a property test can draw it.

| id | priority | level | property | input domain |
| --- | --- | --- | --- | --- |
| I1 | must | unit | `load(dump(x)) == x` | any valid `Config` |

## Failure points

Boundary and malformed input, external failures (I/O, network, subprocess, timeouts),
concurrency and resource exhaustion. Each with the expected behaviour: which error, retry or
safe fallback.

| id | priority | level | trigger | expected behaviour |
| --- | --- | --- | --- | --- |
| P1 | must | unit | empty input list | raises `ValueError("no routes")` |

## Regressions

Every bug met during the session: caught by a session test, found in review, or fixed by a
commit. Always `must`. The trigger must be reproducible through the public API.

| id | trigger | symptom before the fix | fix commit |
| --- | --- | --- | --- |
| R1 | resume after a crash mid-write | finished routes rerun | `abc1234` |

## Exact contracts

Strings, flags, file formats and serialisation that callers rely on, and who relies on them.
Only list exactness that is itself the contract.

| id | priority | contract | relied on by |
| --- | --- | --- | --- |
| C1 | must | CLI exits 2 on bad config | the CI wrapper script |

## Dropped restored tests

Pre-existing tests restored from the merge base that then failed because behaviour changed
on purpose. Each one maps to the item that now carries its intent.

| test | why it fails now | replaced by |
| --- | --- | --- |
| `tests/test_config.py::test_default_timeout` | default raised 30 → 60 in the PR | F3 |

## Out of scope

What is deliberately not tested, and why (covered by untouched pre-existing tests, needs
hardware, logging-only).

## Coverage table (filled after the rebuild)

| item | tests |
| --- | --- |
| F1 | `tests/test_mod.py::test_func_returns_sorted_routes` |
