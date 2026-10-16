export const GOAL_STATE_TYPE = "goal-state";
export const CONTINUE_TYPE = "goal-guard-continue";
export const MAX_IDLE_CONTINUES = 3;
export const MAX_CONTINUES_WITHOUT_PROGRESS = 30;

export type GoalSnapshot = { goalId: string; updatedAt: number; objective: string };
export type Yield = { goalId: string; reason: string; until: "user" | "event" };
export type GuardCounters = { idle: number; sinceProgress: number; lastUpdatedAt?: number };

type BranchEntry = { type: string; customType?: string; data?: unknown };

export function activeGoal(entries: BranchEntry[]): GoalSnapshot | null {
  let state: { goalId?: unknown; status?: unknown; updatedAt?: unknown; objective?: unknown } | undefined;
  for (const entry of entries) {
    if (entry.type === "custom" && entry.customType === GOAL_STATE_TYPE) {
      state = (entry.data as { state?: typeof state } | undefined)?.state ?? undefined;
    }
  }
  if (!state || state.status !== "active" || typeof state.goalId !== "string") return null;
  return { goalId: state.goalId, updatedAt: Number(state.updatedAt) || 0, objective: String(state.objective ?? "") };
}

export type Decision = { continue: true } | { continue: false; reason: string };

export function decide(
  goal: GoalSnapshot | null,
  outcome: string,
  pendingYield: Yield | undefined,
  toolCalls: number,
  counters: GuardCounters,
): Decision {
  if (!goal) return { continue: false, reason: "no active goal" };
  if (outcome !== "completed") return { continue: false, reason: `turn ${outcome}` };
  if (pendingYield?.goalId === goal.goalId) {
    return { continue: false, reason: `yielded until ${pendingYield.until}: ${pendingYield.reason}` };
  }

  const progressed = counters.lastUpdatedAt !== undefined && goal.updatedAt > counters.lastUpdatedAt;
  counters.lastUpdatedAt = goal.updatedAt;
  counters.sinceProgress = progressed ? 0 : counters.sinceProgress + 1;
  counters.idle = toolCalls === 0 && !progressed ? counters.idle + 1 : 0;

  if (counters.idle > MAX_IDLE_CONTINUES) {
    return { continue: false, reason: `${MAX_IDLE_CONTINUES} continuations in a row did nothing` };
  }
  if (counters.sinceProgress > MAX_CONTINUES_WITHOUT_PROGRESS) {
    return { continue: false, reason: `${MAX_CONTINUES_WITHOUT_PROGRESS} continuations without update_goal_progress` };
  }
  return { continue: true };
}

export function continuationPrompt(goal: GoalSnapshot): string {
  return [
    "Continue toward the active goal. A goal means: do not stop until it is done.",
    "Pick the next concrete step and do it now. Routine approvals inside the goal's scope are already granted.",
    "A failed smoke, an expired monitor, a finished sub-step, or a written handoff does not end the goal: diagnose, repair, continue.",
    "Call update_goal_progress when you finish a milestone.",
    "Waiting on a job or monitor with nothing else to do: call goal_yield with until=\"event\".",
    "Needing something only the user can give (credentials, a public action, budget, a scope change): call goal_yield with until=\"user\" and ask in your message.",
    "Done: call complete_goal with evidence.",
    "",
    `Objective: ${goal.objective}`,
  ].join("\n");
}

export const ASK_BLOCKED_REASON =
  "A goal is active, so routine approvals are already granted: decide and keep working. "
  + "If you need something only the user can give (credentials, a public action, budget, a scope change), "
  + "call goal_yield with until=\"user\" and put the question in your message.";
