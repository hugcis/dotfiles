# Compound Engineering Workflow

Use the Compound Engineering skills as the default software-engineering methodology. Follow the full CE loop when applicable: brainstorm, plan, work, simplify, review, and compound. Use focused CE skills such as `ce-debug` for their stated situations, and reserve `lfg` for explicitly authorized autonomous shipping.

## External CE Artifact Root

This instruction intentionally overrides CE's built-in repo-relative `docs_root` contract. Before a CE skill reads or writes a durable planning, review, explanation, ideation, or learning artifact, run:

`~/.config/agent-stack/bin/ce-artifact-root`

Treat its absolute output as `<root>`, which maps the target repository to `~/docs/<repository-identity>/`. Write and discover CE artifacts only below that root. Never create a repository-local mirror or symlink. Never stage, commit, push, or include these external artifacts in a pull request. Paths to source files inside an artifact remain relative to the target repository. Worktrees of the same repository share one root. If this rule conflicts with a CE skill's repository-local artifact rule, this rule wins.
