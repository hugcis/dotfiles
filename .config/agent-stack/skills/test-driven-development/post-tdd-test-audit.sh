#!/usr/bin/env bash
set -euo pipefail

base_ref="${1:-origin/main}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "post-tdd-test-audit: run inside a git worktree" >&2
  exit 2
fi

if ! git rev-parse --verify "$base_ref" >/dev/null 2>&1; then
  echo "post-tdd-test-audit: base ref '$base_ref' not found" >&2
  echo "usage: $0 [base-ref]" >&2
  exit 2
fi

cat <<'PROMPT'
Post-TDD test curation
======================
For each added/modified test below, answer:

  This test should still matter in six months because it protects ______ from regressing.

Keep:   durable behavior, public/API contract, domain invariant, safety/security property, real bug symptom.
Rework: useful signal but tied to source text, AST/file structure, temporary review feedback, or a catch-all artifact file.
Delete: transient development step, reviewer appeasement, removed scaffolding, duplicate coverage, exact text/file-change assertion.

Prefer moving durable checks into domain-specific test files over keeping stabilization/graveyard files.
PROMPT

printf '\nAdded/modified test candidates since %s:\n' "$base_ref"
git diff --name-status --diff-filter=AM "$base_ref"...HEAD -- \
  ':(glob)**/tests/**' \
  ':(glob)**/test_*.py' \
  ':(glob)**/*_test.py' \
  ':(glob)**/*.test.*' \
  ':(glob)**/*.spec.*' \
  || true

printf '\nTip: after reworking/deleting tests, run the focused suite that now owns the durable behavior.\n'
