---
name: rationalizing-code-comments
description: Use when code has too many comments, verbose inline explanations, AI-style commentary, or comments that explain how code works instead of why it exists.
---

# Rationalizing Code Comments

Comments should explain why, not how. Prefer clear code over narration.

## Workflow

1. Match the surrounding code's comment density and style.
2. Classify each added or changed comment:
   - delete: restates names, branches, loops, or obvious data flow
   - compress: contains useful context but is longer than needed
   - keep: explains a surprising reason, invariant, tradeoff, or external constraint
   - move: belongs in public API docs, module docs, or a higher-level design note
3. Delete comments that merely narrate implementation mechanics.
4. Compress necessary comments to the shortest useful why.
5. Verify the code still reads clearly without the removed text.

## Keep Comments For

- non-obvious invariants or safety constraints
- compatibility, ordering, or performance reasons that are not visible from code
- external protocols, formats, or contracts
- surprising tradeoffs or intentionally rejected simpler approaches
- public API behavior that maintainers need at the call site

## Smells

- Inline comments before every branch or loop.
- Comments that repeat function, variable, or test names.
- Historical narration without a current maintenance consequence.
- Apologies, TODOs without owners, or notes about how code was generated.
- Paragraphs where one sentence would preserve the reason.

## Examples

```python
# Bad: explains how.
# Iterate over users and add active ones to the result list.
for user in users:
    if user.active:
        result.append(user)
```

```python
# Better: no comment; make the code carry the how.
active_users = [user for user in users if user.active]
```

```python
# Bad: verbose why.
# We skip retries here because the downstream operation is not idempotent and a
# retry could create duplicate side effects in rare cases.
```

```python
# Better: compressed why.
# Do not retry: downstream side effects are not idempotent.
```
