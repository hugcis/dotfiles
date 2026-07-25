---
name: merging-main-resolving-conflicts
description: Use when a branch has fallen behind a fast-moving main and needs main brought in, or when asked to "merge/rebase main into my branch", "update my branch with main", "fix the merge conflicts", or "resolve conflicts" on a feature branch. Covers locating/creating the branch's worktree, choosing merge vs rebase by PR state, and resolving conflicts.
---

# Merging Main / Resolving Conflicts

## Overview

On a fast-moving `main`, feature branches constantly fall behind and must take
the latest `main` before merge. The job is always the same shape:

**branch name → find-or-create its worktree → fetch latest main → bring main in
(merge or rebase, decided by PR state) → resolve conflicts (auto only when both
sides share intent; stop and design otherwise) → commit. Do not push.**

This skill makes each of those steps deterministic so the same branch gets the
same treatment every time.

**Announce at start:** "I'm using the merging-main-resolving-conflicts skill."

## Step 1: Resolve the branch to a worktree

You are given (or infer) a branch name. Find its worktree; if none exists,
create one. **Never do this work in the primary checkout** (the one usually on
`main`) — it destroys isolation and pollutes main's working copy.

```bash
# 1a. List worktrees and look for the branch.
git worktree list
```

- **Branch-name ambiguity is real.** The same person may use more than one
  username prefix (e.g. `hugcis/...` vs `hugocisneros/...`). If the exact branch
  name given does not appear, search before guessing:
  ```bash
  git branch -a --list '*<ticket-or-keyword>*'
  git ls-remote --heads origin | grep -i <ticket-or-keyword>
  ```
  If a *different* branch plausibly matches, STOP and confirm which branch is meant.

- **Worktree exists** → use it. First verify it is clean and on the right branch
  (`git -C <wt> status`, `git -C <wt> branch --show-current`). If dirty, STOP and ask.

- **No worktree** → create one. Default location is `.claude/worktrees/<short-name>`
  relative to the repo root (match whatever convention already dominates
  `git worktree list`). Fetch first so the branch ref is known:
  ```bash
  PRIMARY=$(git worktree list --porcelain | head -1 | sed 's/^worktree //')
  git -C "$PRIMARY" fetch origin <branch>
  git -C "$PRIMARY" worktree add .claude/worktrees/<short-name> <branch>
  ```
  Run all subsequent commands inside that worktree.

## Step 2: Fetch latest main and assess divergence

From inside the branch's worktree:

```bash
git fetch origin
git status                                   # must be clean; if dirty, STOP
git rev-list --left-right --count origin/main...HEAD   # behind / ahead counts
git log --oneline origin/main..HEAD          # commits unique to the branch
```

- Always integrate against **`origin/main`**, not the possibly-stale local `main` ref.
- Confirm local `HEAD` is not behind `origin/<branch>`. If the remote branch has
  commits the local copy lacks (or vice versa), reconcile that BEFORE bringing
  main in.

## Step 3: Decide merge vs rebase — by PR state, deterministically

This is the decision agents get wrong by reflex. Drive it from the PR, not a
personal default. Query the PR:

```bash
gh pr view <branch> --json isDraft,reviews,state
```

Apply this rule (first match wins):

| PR state | Action | Why |
|----------|--------|-----|
| Open PR (`isDraft:false`) **with any review** | `git merge origin/main` | Reviews anchor to commit SHAs; rebase rewrites them and invalidates the review. Preserve history. |
| Draft PR, **no review yet** (`isDraft:true`, `reviews:[]`) | `git rebase origin/main` is OK | No reviewer state to preserve; linear history is cleaner for the eventual review. |
| No PR yet / cannot determine | Default to **merge** | Safe default; never silently rewrite shared history. Mention the choice. |

Edge cases that force **merge** regardless: the branch is shared (other branches
stacked on it) or the user explicitly asked for a merge. When in doubt between the
two, prefer merge and say so.

State your choice and the reason in one line before running it.

## Step 4: Bring main in

```bash
# merge path
git merge origin/main

# rebase path
git rebase origin/main
```

If it completes with no conflicts, go to Step 6.

## Step 5: Resolve conflicts

For **each** conflicting file, inspect both sides (`git diff`, the `<<<<<<<` /
`=======` / `>>>>>>>` markers) and classify intent — not just "is it mechanical."

**Label sides by content, not by the `ours`/`theirs` words.** During a `merge`,
`ours` = the branch and `theirs` = main. During a `rebase` these **invert**:
`ours` = main (the commit being replayed onto) and `theirs` = the branch commit.
Always say "the branch's version" / "main's version" so you never mislabel sides
to the user.

For a multi-commit **rebase**, the same conflict can recur on each replayed
commit. Enable `git rerere` (reuse recorded resolution) once before starting so a
resolution you make is replayed automatically:
`git config rerere.enabled true`. If the same divergent conflict would need the
same human decision many times, consider proposing merge instead (one resolution,
not N) — but only when PR state allows it.

### Auto-resolve (no need to ask) when both sides share intent

- Both sides make the **same change** (e.g. both rename the same field
  `type`→`kind`; take both, the result is identical).
- Both sides add **independent adjacent lines** with no behavioral interaction.
- Import-order / formatter churn.
- **Lockfiles (`uv.lock`): never hand-merge.** Take main's side as base, then
  **regenerate** by running `uv lock` in each affected directory (this monorepo
  has many lockfiles). Hand-edited locks produce inconsistent resolutions.

### STOP and enter a design loop when sides diverge

Genuinely different behavior on the same code, main deleted/refactored code the
branch builds on, or any resolution that needs feature intent you can't read from
the diff. Do **not** pick a side to make it compile.

**Design loop format — per conflict:**
1. Show **the branch's version** vs **main's version** for that hunk (label by
   content, not `ours`/`theirs` — see the inversion note above).
2. Explain what each side changed and **why they collide**.
3. Propose a concrete resolution **with a recommendation**.
4. Wait for the user's call before applying it.

Handle each divergent conflict this way; batch only the auto-resolvable ones.

After resolving each file: `git add <file>`.

## Step 6: Finalize — commit, do NOT push

- **Merge path:** `git commit` (accept the default merge message) once all
  conflicts are staged.
- **Rebase path:** `git rebase --continue` until it completes. Lockfile
  regeneration becomes a new commit; `git add` the regenerated locks.
- Run a quick sanity check on what was touched (relevant tests, and
  `uvx prek run --origin HEAD --source origin/HEAD` for lint/lock consistency).
- **Stop here. Do not push.** The user reviews and pushes.
  - Choosing the **rebase** path commits the branch to a force-push later:
    because rebase rewrote history, the eventual push must be
    `git push --force-with-lease` (never plain `--force`). Flag this when handing
    back so a rejected normal `git push` isn't a surprise.
- Report: which worktree, merge-vs-rebase choice + why, every conflict and how it
  was resolved (and which were escalated), and sanity-check results.

## Red flags — STOP

- About to merge/rebase in the primary `main` checkout → wrong place, use a worktree.
- Picked merge-vs-rebase by habit without checking PR state → query the PR first.
- Resolving a conflict by choosing whichever side compiles → that's a divergent
  conflict; enter the design loop.
- Hand-editing `uv.lock` → regenerate with `uv lock` instead.
- About to `git push` → don't; finalize at the commit and hand back.
- Rebasing a PR that already has reviews → you just invalidated the review; use merge.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Guessing the branch when the name doesn't match | Search `git branch -a` / `git ls-remote`; confirm `hugcis` vs `hugocisneros`-style prefix ambiguity |
| Merging against stale local `main` | Always `git fetch` and integrate `origin/main` |
| Rebasing an open, reviewed PR | Merge instead — rebase breaks review anchors |
| Auto-resolving a behavioral conflict | "Same intent" is the bar, not "looks small"; escalate if behavior differs |
| Pushing after resolving | Finalize at commit; user pushes |
