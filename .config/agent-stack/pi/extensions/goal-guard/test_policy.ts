import assert from "node:assert/strict";
import { activeGoal, decide, MAX_IDLE_CONTINUES, type GuardCounters } from "./policy.ts";

const goalEntry = (status: string, updatedAt: number) => ({
  type: "custom",
  customType: "goal-state",
  data: { state: { goalId: "g1", status, updatedAt, objective: "ship it" } },
});

assert.equal(activeGoal([goalEntry("active", 1), goalEntry("complete", 2)]), null);
const goal = activeGoal([goalEntry("active", 1)]);
assert.ok(goal);

const fresh = (): GuardCounters => ({ idle: 0, sinceProgress: 0 });

assert.deepEqual(decide(goal, "completed", undefined, 5, fresh()), { continue: true });
assert.equal(decide(null, "completed", undefined, 5, fresh()).continue, false);
assert.equal(decide(goal, "aborted", undefined, 5, fresh()).continue, false);
assert.equal(
  decide(goal, "completed", { goalId: "g1", reason: "need token", until: "user" }, 5, fresh()).continue,
  false,
);

const stuck = fresh();
const decisions = Array.from({ length: MAX_IDLE_CONTINUES + 1 }, () => decide(goal, "completed", undefined, 0, stuck));
assert.ok(decisions.slice(0, -1).every((d) => d.continue));
assert.equal(decisions.at(-1)!.continue, false);

const working = fresh();
for (let i = 0; i < MAX_IDLE_CONTINUES + 5; i++) {
  assert.equal(decide({ ...goal, updatedAt: i }, "completed", undefined, 0, working).continue, true);
}

console.log("goal-guard policy tests passed");
