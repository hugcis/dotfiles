# Compound Engineering Workflow

Use the Compound Engineering skills as the default software-engineering methodology. Follow the full CE loop when applicable: brainstorm, plan, work, simplify, review, and compound. Use focused CE skills such as `ce-debug` for their stated situations, and reserve `lfg` for explicitly authorized autonomous shipping.

## Knowledge retrieval and closure

Before durable planning or debugging in a documented area, resolve the artifact root and search its `CONCEPTS.md`, `solutions/README.md`, and `solutions/` contents. New durable plans and learnings record `prior_art` with the relevant paths or `none_found`. Do not treat historical plans or verification receipts as current instructions without checking their status and source revision.

New or updated durable Markdown artifacts use lifecycle metadata where their format permits it: `status`, `created`, `last_verified`, `source_ref`, and `supersedes`. If frontmatter is not supported, put the same information in a short opening status block. Do not rewrite historical evidence only to add metadata.

At the end of non-trivial work, record exactly one learning disposition: create or update a `solutions/` entry, cite an existing solution that remains correct, or state `no_new_reusable_learning` with a reason. Convert prevention items into tests, assertions, CI checks, or runbook steps whenever feasible; a document alone is not prevention.

## Context and review economy

Use `/compact` near a task boundary when the working context reaches roughly 150,000 to 200,000 tokens. Start a new session with a short handoff for unrelated work. Keep monitoring separate from implementation sessions and prefer completion or state-change notifications over status polling.

Default to one focused independent reviewer. Add review lanes only for distinct risks, and use lower-cost models for bounded reconnaissance and routine review. Record findings raised, findings accepted, and findings that changed the final code for deliberate review waves.

## External CE Artifact Root

This instruction intentionally overrides CE's built-in repo-relative `docs_root` contract. Before a CE skill reads or writes a durable planning, review, explanation, ideation, or learning artifact, run:

`~/.config/agent-stack/bin/ce-artifact-root`

Treat its absolute output as `<root>`, which maps the target repository to `~/docs/<repository-identity>/`. Write and discover CE artifacts only below that root. Never create a repository-local mirror or symlink. Never stage, commit, push, or include these external artifacts in a pull request. Paths to source files inside an artifact remain relative to the target repository. Worktrees of the same repository share one root. If this rule conflicts with a CE skill's repository-local artifact rule, this rule wins.
