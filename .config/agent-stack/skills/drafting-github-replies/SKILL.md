---
name: drafting-github-replies
description: Use when preparing a response to GitHub review comments, issue comments, PR threads, or automated review findings.
---

# Drafting GitHub Replies

Prepare text for a human to send. Do not send it yourself.

## Rules

- Never post, submit, edit, or resolve GitHub comments, reviews, or threads.
- Do not run `gh pr comment`, `gh pr review`, or `gh api` calls that create or update comments, reviews, replies, or thread state.
- Produce a copy-pasteable draft instead.
- State what changed, what was verified, and what remains uncertain.
- If feedback is not accepted, explain the technical reason without performative agreement.
- Do not add tool attribution or co-author trailers.

## Draft Shape

```text
Thanks — addressed in the latest update.

Changed:
- ...

Verified:
- ...

Notes:
- ...
```

For multiple comments, group by topic and mark each as addressed, deferred, or not accepted. If no reply is needed, say so and include the evidence.
