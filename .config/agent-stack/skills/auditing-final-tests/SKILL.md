---
name: auditing-final-tests
description: Use when finishing a feature, bugfix, refactor, or review where tests were added or changed, especially after TDD, debugging, or temporary regression guards.
---

# Auditing Final Tests

## Overview

TDD creates useful development guards. Final tests should be intentional behavior, contract, or policy guards that fit the context where they live.

## Workflow

1. Scope each added or changed test.
2. Identify context for each test file: package, module, feature area, suite purpose, and neighboring tests.
3. Classify each test as behavior, contract, integration, policy, regression, or scaffolding.
4. Keep tests that protect guarantees in context; raise or remove temporary checkpoints.
5. Verify the cleaned suite.

## Context Fit Check

Ask these before editing:

- What is this test file or suite responsible for?
- Would this belong here after an implementation refactor?
- Is this package behavior or wider repo policy?
- Is there a higher-level suite, checker, lint rule, or release check where this belongs?
- If no proper home exists, is this worth creating one, or should it be reported instead of kept locally?

## Test Rationalization

Final tests should prove durable behavior, not record the implementation journey. Prefer
one meaningful test of logic or contract over many development artifacts that mirror TDD
steps.

- Merge duplicate variants when they prove the same rule; keep separate cases only when
  each protects a distinct boundary or invariant.
- Replace implementation-coupled assertions with public behavior checks.
- Delete tests that only prove scaffolding, temporary review feedback, or obvious language
  and framework behavior.
- Raise low-level step checks into a domain-level regression when the exact symptom is
  still worth protecting.
- Keep exact regression tests when the specific input, message, or protocol detail is the
  durable behavior.

A final suite should be meaningfully testing logic the product relies on, not proving every
intermediate step taken while developing it.

## Smells

- Many exact filenames, paths, package names, timestamps, hashes, or constants.
- Negative assertions against one old implementation detail.
- Tests for dependency hygiene or import boundaries inside a behavior-focused package suite.
- Multiple tests with the same setup and only one arbitrary value changed.
- Tests that reach into private helpers when a public contract can be exercised.
- Tests that would fail after a harmless refactor.

## Refactoring Moves

- Replace one-off move guards with generic invariants.
- Replace exact path checks with "resource loads under the expected fixture root."
- Parameterize repeated cases that exercise the same rule.
- Use property/invariant tests when examples are samples of a broader law.
- Delete scaffolding once broader behavior covers the risk.
- Move policy checks to the policy layer instead of hiding them in a leaf package.

## Keep Specific Tests When

- The exact string, path, CLI flag, or error message is a documented/public contract.
- The test captures a regression that would be hard to diagnose from a broader failure.
- The specificity is the behavior, such as shell quoting, serialization format, or wire protocol.
- The test sits in a suite whose purpose is exactly that policy.

## Final Questions

- If this failed six months from now, would the failure be useful?
- Is the test at the same abstraction level as the code it guards?
- Could a maintainer understand why this guarantee matters from the test name and assertions?
- Did TDD leave behind a development checkpoint that should now be raised, moved, or deleted?

## Avoid

- Treating every TDD test as sacred final coverage.
- Deleting valuable regression tests just because they started as scaffolding.
- Hiding intent behind clever parameterization.
- Keeping local package tests for cross-repo policy because no better home exists.
- Generalizing so far the original risk is no longer covered.
