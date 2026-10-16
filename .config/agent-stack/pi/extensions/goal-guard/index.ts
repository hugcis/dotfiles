import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
  activeGoal,
  ASK_BLOCKED_REASON,
  CONTINUE_TYPE,
  continuationPrompt,
  decide,
  type GuardCounters,
  type Yield,
} from "./policy.ts";

// pi-agent-goal's own continuation is opt-in and capped at 3 turns; this keeps
// an active goal running until complete_goal, an explicit goal_yield, or the
// user interrupts.
export default function (pi: ExtensionAPI) {
  let counters: GuardCounters = { idle: 0, sinceProgress: 0 };
  let pendingYield: Yield | undefined;
  let toolCalls = 0;
  let run = 0;
  let yieldRun = 0;

  const reset = () => {
    counters = { idle: 0, sinceProgress: 0 };
    pendingYield = undefined;
  };

  pi.on("session_start", reset);

  pi.on("input", (event) => {
    if (event.source !== "extension") reset();
  });

  // Any later run means a monitor, subagent, or the user woke the session, so an
  // event-yield is over; only the user's own input lifts a user-yield.
  pi.on("agent_start", () => {
    run++;
    if (pendingYield?.until === "event" && yieldRun < run) pendingYield = undefined;
  });

  pi.on("tool_execution_start", (event) => {
    if (!event.parentToolCallId) toolCalls++;
  });

  pi.on("tool_call", (event, ctx) => {
    if (event.toolName !== "ask_user") return;
    if (!activeGoal(ctx.sessionManager.getBranch())) return;
    return { block: true, reason: ASK_BLOCKED_REASON };
  });

  pi.registerTool({
    name: "goal_yield",
    label: "Goal yield",
    description:
      "Pause automatic goal continuation. until=\"event\": waiting on a job or monitor with nothing else to do; its notification resumes the goal. "
      + "until=\"user\": you need something only the user can give (credentials, a public action, budget, a scope change); ask in your message.",
    parameters: Type.Object({
      until: Type.Union([Type.Literal("event"), Type.Literal("user")]),
      reason: Type.String({ description: "One line: what you are waiting for." }),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const goal = activeGoal(ctx.sessionManager.getBranch());
      if (!goal) throw new Error("No active goal.");
      pendingYield = { goalId: goal.goalId, reason: params.reason, until: params.until };
      yieldRun = run;
      return {
        content: [{ type: "text", text: `Goal continuation paused until ${params.until}. End your turn with a short status.` }],
        details: pendingYield,
      };
    },
  });

  pi.on("agent_before_settle", (event, ctx) => {
    const goal = activeGoal(ctx.sessionManager.getBranch());
    const decision = decide(goal, event.outcome, pendingYield, toolCalls, counters);
    toolCalls = 0;
    if (!decision.continue) {
      if (goal) ctx.ui.setStatus("goal-guard", `goal paused: ${decision.reason}`);
      return;
    }
    ctx.ui.setStatus("goal-guard", undefined);
    return {
      entries: [
        ...event.entries,
        { type: "custom_message", customType: CONTINUE_TYPE, content: continuationPrompt(goal!), display: false },
      ],
      continue: true,
    };
  });
}
