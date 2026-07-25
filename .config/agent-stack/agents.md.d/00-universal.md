# Superpowers Skill Use

When a task matches an available skill's description, load that skill before acting,
including before clarifying questions, file exploration, planning, debugging, or edits.
Treat process skills such as `brainstorming`, `systematic-debugging`, `writing-plans`,
`test-driven-development`, and `verification-before-completion` as mandatory whenever
their trigger conditions apply.

# Conventions

Personal design docs, ADRs, plans, and Superpowers specs belong under `~/docs/`,
never inside a repository and never in a commit.

Prefer `vtrash` over `rm -rf` when clearing generated output directories or run
artifacts. Use destructive removal only when `vtrash` is unavailable or the target
is an explicitly disposable temporary path.

Do not leave Superpowers runtime artifacts inside a repository.
