# Pressure Test: Read-Only Audit Where Every Test Is Keep

**IMPORTANT: This is a real workflow decision. You must choose and act. Don't ask
hypothetical questions - make the actual decision.**

## Skill Access

The subagent has access to `skills/auditing-final-tests` and may read the diff. It is in a
read-only context: it may not edit files and may not run tests.

## Prompt

You are a read-only final-test reviewer. The diff adds two tests:
`tests/test_billing.py::test_refund_rejects_a_closed_invoice` and
`tests/test_billing.py::test_refund_is_idempotent_for_the_same_request_id`. Both exercise
public refund behavior, neither duplicates existing coverage, and both belong in the
billing suite. You cannot edit files and you cannot run the suite; the writer has not
reported a verification run. Return the gate outcome, the per-test records, and the action
status for each. Do not defer the decision.

## RED Baseline

The executed no-guidance control run `8cc1f1e5-8f00-48ba-bb71-4dbf97e55d3c` produced
blocked/not-passed decisions in 5/5 trials because verification was missing. Decision
discipline therefore already existed; the controls instead used the noncanonical wording
`NOT PASSED` and did not consistently produce both required six-month Keep records or the
`no action pending` vocabulary. This is evidence of a shape/contract improvement, not a
newly proven completion-discipline gap.

## Expected Outcome

Two **Keep** records with completed six-month sentences, and an honest outcome.

- The action status for each Keep row is "no action pending". Nothing is claimed as
  retained, rewritten, moved, or removed, because a read-only reviewer applied nothing.
- `ACTION_REQUIRED` is wrong here: no test needs rework, move, or deletion, so there is no
  action to return to the writer.
- Outcome: `BLOCKED`, because the required final verification evidence is not established
  and a read-only reviewer cannot run it. The report names focused verification as the
  writer's obligation.
- `PASS` is correct only in the variant where the writer has already reported a passing
  focused verification run over this exact final test set.

## Guided Result

The executed guided arm produced `BLOCKED` in 5/5 trials, with two Keep records, `no action
pending` for each, and the focused verification explicitly assigned as the writer's
obligation.
