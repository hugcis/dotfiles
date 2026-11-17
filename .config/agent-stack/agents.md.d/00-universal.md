# Conventions

Plans, design notes and other working documents go in `~/docs/<repository>/`, never in a repository or a commit.

Never add AI or tool attribution to commits, PRs or comments.

Keep commit signing on. If signing fails, fix the signer (`gpg.format` says which); never bypass it.

When delegating well-specified work (exploration, search, mechanical edits), use the fast slot (`coder-fast`, `reviewer-fast`). Use the stronger slots for ambiguous design, a second debugging attempt, and security or concurrency review.

# Enforced by checks

These are not suggestions: a guard blocks the action, and its message says what to do instead.

| Rule | Enforced by |
|---|---|
| No destructive git or `rm` on shared or unapproved targets | `policy.py` pre-tool hook |
| No signing bypass (`--no-gpg-sign`, `commit.gpgsign=false`) | `policy.py` pre-tool hook |
| No home-wide scans or unbounded long commands | `policy.py` pre-tool hook, Pi `bash-timeout-guard` |
| No edits in a primary checkout | Pi `worktree-guard` |
| No AI attribution, no working docs staged, PR size justified | `ship-check` on push and PR creation |
