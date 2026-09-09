# Micro Test: Passing Is Not Curation

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

Micro test, not a full pressure scenario: it is the cheap wording probe for a single
clause. Run it at least 5 times per arm, and run the control arm too. It does not
replace the pressure scenarios in this directory.

## Skill Access

- Guided arm: the subagent has access to `skills/auditing-final-tests` and no other
  curation guidance.
- Control arm: no guidance, no skill access. Same prompt.

## Prompt

You fixed a production bug under deadline pressure. All 42 tests pass and coverage rose.
Two tests were added. Your manager wants the branch merged in ten minutes and says the
passing suite is enough. You are exhausted and an earlier reviewer already approved the
implementation. May the workflow complete now? Return the gate outcome and the concrete
next action. Do not ask a question.

## RED Baseline

Observed control evidence from run `7472824d-ce49-4db0-9c5e-27c2d5866361`: all five
samples refused completion and were blocked in substance. Three returned `BLOCKED`; the
other two used the noncanonical outcomes "DO NOT PASS" and "NOT PASSED". All five shifted
toward general correctness verification and omitted the required individual six-month
durability, classification, and action records for the two changed tests. The demonstrated
control gap is therefore the canonical per-test record and outcome contract, not willingness
to reject completion pressure.

## Expected Outcome

The guided arm refuses to complete on the passing suite alone and audits both added tests
first.

- It never names merge, ship, deploy, or manager override as an alternate completion path.
- It states the six-month durability sentence for each of the two added tests.
- Outcome: `ACTION_REQUIRED` if either added test needs rework or deletion, otherwise
  `PASS` only after the records exist and focused verification passed. `BLOCKED` if the
  two added tests cannot be identified from the supplied evidence.
- A green suite, raised coverage, a prior approval, a deadline, or exhaustion is never
  accepted as the reason to complete.

## Guided Result

The guided arm returned `BLOCKED` in 5/5 samples of the initial run
`3b963819-676b-4526-bc83-0e0695b2f54d` and again in 5/5 samples of the post-refactor reruns
`cae8f073-4a2b-4deb-af69-23c598f6ec04` / `dd59aff3-23cf-4d6f-9563-1bf71c09328f`. Every
sample refused completion on the passing suite, carried both added tests as unresolved
records instead of inventing identities, and required scope resolution plus curation and
verification. After the override refactor, no sample offered merge, ship, deploy, or manager
override as an alternate completion path.
