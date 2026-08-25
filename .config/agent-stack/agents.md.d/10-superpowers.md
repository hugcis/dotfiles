# Superpowers Skill Use

When a task matches an available skill's description, load that skill before acting,
including before clarifying questions, file exploration, planning, debugging, or edits.
Treat process skills such as `brainstorming`, `systematic-debugging`, `writing-plans`,
`test-driven-development`, and `verification-before-completion` as mandatory whenever
their trigger conditions apply.

## Final-Test Curation Gate

Any workflow that adds or changes tests MUST use `auditing-final-tests` before completion,
including features, bug fixes, refactors, CI repairs, review fixes, and test-only changes.
`PASS` and `NOT_APPLICABLE` are the only completion-permitting outcomes. Resolve
`ACTION_REQUIRED`; report `BLOCKED` honestly.
