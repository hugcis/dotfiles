# Conventions

Personal design docs, ADRs, plans, and Superpowers specs belong under `~/docs/`,
never inside a repository and never in a commit.

Avoid destructive cleanup commands unless the target is explicitly disposable or the user approved the removal.

Always keep git commit signing enabled. If SSH signing fails, assume `SSH_AUTH_SOCK` points to a stale or expired agent socket; do not bypass signing with `--no-gpg-sign` or `commit.gpgsign=false`. Refresh `SSH_AUTH_SOCK` to a live `/tmp/ssh-*/agent.*` socket, confirm with `ssh-add -l`, and retry the signed commit.

Do not leave Superpowers runtime artifacts inside a repository.
