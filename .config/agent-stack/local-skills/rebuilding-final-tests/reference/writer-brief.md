# Blind writer brief

Fill every `<placeholder>` and send everything below the line as the subagent's first
message, with a fresh agent that inherits no context. Do not add the deleted tests, excerpts
of them, their fixtures, private modules, git history, or your own description of how the
old tests worked. Paste the spec and API excerpts inline. Do not point at files the writer
would have to look for.

---

You are writing the final test suite for a finished change in `<repo path>`. You write tests
only. Never edit production code.

## What you may read

- The spec below. It is the only source of what to test.
- The public API below. It is generated from the package's exports and callers. A module or name
  it does not list is internal, even if its name has no underscore.
- The usage docs: `<doc paths or "none">`.
- Existing tests and fixtures in `<test dir>` that are not listed under "Removed paths",
  to learn the conventions and reuse fixtures.

## What you must not read

Do not open source files of the package under test, git history
(`git log`, `git show`, `git diff`, other branches or stashes), or these removed paths, even
if they reappear: `<deleted test paths>`. If a spec item cannot be tested through the public
API, do not reach into internals. Stop and report it as a gap.

## Spec

<paste TEST_SPEC.md>

## Public API

<paste the output of scripts/public_api_digest.py unchanged. Do not add modules or names it left out.>

## Conventions

- Test location: `<dir>`, file naming `<pattern>`, framework `<pytest | ...>`.
- Fixtures already available: `<name: what it gives>`.
- Run: `<focused test command>`. Lint and type check: `<commands>`.

## Rules

- Test through public entry points only. No assertions on private helpers or internal
  structure.
- One test per behaviour, named after the behaviour (`test_resume_skips_finished_routes`,
  not `test_helper_returns_list`). Several spec ids share a test only when they describe the
  same behaviour (an invariant and the regression that broke it, two invalid values for one
  validation rule), and then as parameters that all run the same assertions, never as a sequence
  of asserts. A test whose name needs "and" to join two behaviours, whose body checks one
  behaviour and then another, or whose body branches on the parameter (`if case == ...`) is
  bundled: split it.
- Parameterise repeated examples. Use property-based tests (`<Hypothesis | proptest |
  fast-check>`) for invariants, with a pinned seed or derandomised profile and a bounded
  example count.
- Mock only external systems (network, cloud, GPU, clock, randomness when needed). Never mock
  the code under test or its internal collaborators. Prefer real temp files and in-memory
  fakes, which you write yourself from the public API.
- Every test cites its spec item id in a short docstring or a parameter id.
- Size budget: the previous suite had `<N>` test definitions and `<L>` lines of test code,
  counting fixtures and helpers. Come in strictly under both. When over budget, parameterise
  repeated examples, move shared setup into helpers and shorten setup. Never bundle different
  behaviours into one test to fit. If the suite is still over budget, drop `optional` items
  first. If it is still over, stop and report the smallest unbundled suite you can write and
  the `must` items it would drop.

## Return

1. The files you wrote.
2. A coverage table: spec item id → test names. Every `must` item needs at least one test.
3. Spec items you could not test through the public API, and why.
4. The focused test command output, and lint and type check results.
