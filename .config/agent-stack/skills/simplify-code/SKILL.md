---
name: simplify-code
description: Review the recently changed code for reuse, simplification, efficiency, and altitude cleanups, then apply the fixes. Quality only — it does not hunt for bugs. Use when the user asks to simplify, refine, tidy, clean up, or improve the readability/maintainability of code they just wrote or changed.
---

# Simplify Code

Refine recently modified code for clarity, consistency, and maintainability **while preserving exact
behavior**. This is a quality pass, not a bug hunt — if you spot a real bug, note it separately but do not
try to fix bugs here.

Prefer readable, explicit code over clever or overly compact code. Fewer lines is not the goal; clarity is.

## Workflow

1. **Scope the diff.** Look only at code changed in the current session / working tree, unless the user names
   a broader scope. Use `git diff` (and `git diff --staged`) to find what changed. Do not touch unrelated code.
2. **Read for opportunities** along these axes (in priority order):
   - **Reuse** — replace duplicated or reinvented logic with existing helpers/utilities already in the repo.
   - **Simplification** — cut needless complexity, nesting, dead code, and redundant abstractions; consolidate
     related logic; give variables/functions clearer names; drop comments that just restate the code.
   - **Efficiency** — remove obviously wasteful work (repeated computation, needless allocations/passes) when
     it doesn't hurt readability.
   - **Altitude** — keep each function at one level of abstraction; don't mix high-level flow with low-level detail.
3. **Apply the fixes** directly to the files (this skill edits, it doesn't just advise).
4. **Preserve behavior.** All original outputs, side effects, and edge cases must remain identical. If a change
   would alter behavior, don't make it — flag it instead.
5. **Verify.** Re-read the edited code; if the project has a fast check (formatter/linter/type-check/tests for
   the touched files), run it. Report what you ran and its result — never claim success without evidence.
6. **Summarize** only the significant changes (what and why), not cosmetic noise.

## Rules

- Preserve functionality above all — never change *what* the code does, only *how*.
- **Avoid nested ternaries.** Use `if`/`else` chains or a `switch`/match for multiple conditions.
- Match the surrounding code: its naming, idioms, comment density, and the project's documented standards
  (e.g. CLAUDE.md / AGENTS.md if present).
- Don't over-simplify: keep helpful abstractions, don't merge unrelated concerns into one function, don't
  produce dense one-liners that are hard to debug or extend.
- Stay in scope: recently changed code only, unless told otherwise.

## Project-specific standards (extend here)

<!-- Add your own conventions below. These take precedence over the generic rules above.
     Examples:
       - Prefer the `function` keyword over arrow functions for top-level functions.
       - Require explicit return-type annotations on exported functions.
       - Run `just fmt && just check` on touched files before finishing.
       - Forbid `try/catch` where a Result/Option-style pattern fits.
-->

_(none yet — add project or personal conventions here)_

## Custom checks (extend here)

<!-- Add extra passes you want this skill to always perform, e.g.:
       - Flag any function longer than N lines for a split.
       - Ensure new public APIs have doc comments.
       - Check that error messages include actionable context.
-->

_(none yet)_
