# Superpowers Skill Use

When a task matches an available skill's description, load that skill before acting,
including before clarifying questions, file exploration, planning, debugging, or edits.
Treat process skills such as `brainstorming`, `systematic-debugging`, `writing-plans`,
`test-driven-development`, and `verification-before-completion` as mandatory whenever
their trigger conditions apply.

# Conventions

Personal design docs, ADRs, plans, and Superpowers specs belong under `~/docs/`,
never inside a repository and never in a commit.

Avoid destructive cleanup commands unless the target is explicitly disposable or the user approved the removal.

Do not leave Superpowers runtime artifacts inside a repository.
