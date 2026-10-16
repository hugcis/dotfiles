# Conventions

Personal design docs, ADRs, plans, and methodology artifacts belong under
`~/docs/`, never inside a repository and never in a commit.

Avoid destructive cleanup commands unless the target is explicitly disposable or the user approved the removal.

Always keep git commit signing enabled. Diagnose failures using the configured `gpg.format`; never bypass signing with `--no-gpg-sign` or `commit.gpgsign=false`. For SSH signing, refresh a stale `SSH_AUTH_SOCK` to a live `/tmp/ssh-*/agent.*` socket and confirm with `ssh-add -l`. For OpenPGP signing, confirm the configured secret key and `gpg-agent`, then retry the signed commit.

Do not leave methodology runtime artifacts inside a repository.

# Local skill use

Load a matching always-on local skill before acting. These skills are `auditing-final-tests`, `ci-red-triage`, `drafting-github-replies`, `full-review-and-fix`, `pr-feedback-watch-loop`, `pr-ship-loop`, `rationalizing-code-comments`, `review-branch`, and `unslop`.

The selected methodology owns the outer lifecycle. Prefer a local skill when its exact specialty matches, then return to the methodology workflow for the surrounding phases and handoff. Do not run an overlapping methodology skill as a duplicate pass unless the local skill explicitly composes it. In particular: use `ci-red-triage` for red CI and `ce-debug` for other bugs; use `review-branch` for explicit read-only branch review and `full-review-and-fix` for explicit deep review with fixes; use CE review for ordinary implementation review; use `pr-ship-loop` for end-to-end PR shipping and babysitting (sync with main, review-and-fix, draft PR, watch CI and review threads), the narrower local PR skills for feedback drafting or a single watch loop, and CE PR skills only when explicitly requested; use `rationalizing-code-comments` as a focused pass inside CE simplification.

## Final-Test Curation Gate

Any workflow that adds or changes tests MUST use `auditing-final-tests` before completion,
including features, bug fixes, refactors, CI repairs, review fixes, and test-only changes.
`PASS` and `NOT_APPLICABLE` are the only completion-permitting outcomes. Resolve
`ACTION_REQUIRED`; report `BLOCKED` honestly.

# Written content

Apply the `unslop` skill as a final editing pass to prose written for people, including chat responses, pull request and issue text, documentation, Markdown files, plans, release notes, and handoffs. Preserve technical precision, required templates, the project's established voice, and the author's intended meaning. Do not rewrite code, commands, logs, quoted material, generated or vendored text, or exact terminology merely to satisfy a style preference.
