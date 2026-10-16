---
name: encoding-repeated-corrections
description: Use when the user corrects the same agent mistake a second time, says "again" or "I already told you", asks to make a rule stick, or asks to turn recurring feedback into rules, checks, hooks, or skills.
---

# Encoding Repeated Corrections

A written rule that nothing enforces will be skipped again. Change the system so the next
agent cannot make the mistake, and write prose only for judgment calls.

Assume every contributor is an agent that sees only the files it opened, copies the
nearest example, and takes the shortest path that works.

## 1. Find the mistake classes

Read the evidence: the current correction, recent reverts, review comments, agent
instruction files, and workaround comments. Group mistakes into classes. A class counts
once it has happened twice. Check whether a rule for it already exists; an existing rule
that was ignored is the strongest signal to escalate.

## 2. Fix each class at the highest level that works

1. **Architecture.** One owner per piece of state, one supported way per task. Hide
   internals so the wrong import fails. Replace hand-synced lists with one source of
   truth. Delete old paths an agent would copy.
2. **Types or a check.** Make the bad state unrepresentable. Otherwise add a lint, CI
   check, hook, or preflight script whose error names what to do instead. If the pattern
   is already common, fail only when a change adds more.
3. **A test** of the behavior that breaks.
4. **Agent harness enforcement** for agent behavior: a tool guard, policy hook, or
   completion gate.
5. **Docs or an agent rule last**, and only for judgment calls. Put a rule in the
   narrowest scope that covers it: repository instructions for one repository, global
   instructions only for cross-project behavior.

## 3. Fix and prove

Fix the most frequent classes now, one commit each. Prove each new check fails on a real
past mistake before trusting it. Run the same check locally and in CI. Exceptions go on
the offending line with a reason.

## 4. Keep the enforcement table

Keep a short table in the relevant instruction file pairing each rule with what enforces
it. When a rule exists and nothing enforces it, a repeat means fix it at a higher level in
the same change. Drop a rule once its mistake can no longer happen.

## Report

Each class with its evidence, the level chosen, why a higher level did not work, and the
proof that the new check fails on the old mistake.

Adapted from pstack `correct` and `principle-encode-lessons-in-structure` (MIT, Lauren Tan).
