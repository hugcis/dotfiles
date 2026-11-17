import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Pi's bash tool has no default timeout, so a foreground command can hold a
// session for hours. One rule: foreground bash is short. Every call gets a
// timeout of at most 10 minutes, and a call that asks for longer is blocked
// with instructions to detach it instead.
//
// Wide filesystem scans are NOT handled here. They live in the shared guard
// (hooks/policy.py, is_broad_scan), so Vibe and Pi apply one set of roots.
export const MAX_FOREGROUND_S = 600;

const UNITS: Record<string, number> = { "": 1, s: 1, m: 60, h: 3600, d: 86400 };

// Durations a command asks for inside itself: `timeout N`, `sleep N`.
function innerSeconds(command: string): number {
  let max = 0;
  for (const m of command.matchAll(
    /(?:^|[\s;|&(])(?:timeout(?:\s+-\S+)*|sleep)\s+(\d+(?:\.\d+)?)([smhd]?)(?=[\s;|&)]|$)/g,
  )) {
    max = Math.max(max, parseFloat(m[1]) * UNITS[m[2]]);
  }
  return max;
}

const DETACH_HELP =
  "Run long work detached and watch it with a monitor: submit it to the batch scheduler, or start it with " +
  "`nohup <cmd> > <log> 2>&1 &` (or the background-process tool), then use a monitor or a goal yield " +
  "that wakes you on completion. Poll briefly with short commands (queue status, tail -n 20 <log>).";

export function guardBash(input: { command?: unknown; timeout?: unknown }): {
  block: boolean;
  reason?: string;
  input: { command?: unknown; timeout: number };
} {
  const command = typeof input.command === "string" ? input.command : "";
  const asked =
    typeof input.timeout === "number" && Number.isFinite(input.timeout) && input.timeout > 0
      ? input.timeout
      : undefined;
  const out = { ...input, timeout: Math.min(asked ?? MAX_FOREGROUND_S, MAX_FOREGROUND_S) };

  const wanted = Math.max(asked ?? 0, innerSeconds(command));
  if (wanted > MAX_FOREGROUND_S) {
    return {
      block: true,
      input: out,
      reason: `Blocked: this foreground command asks for ${Math.round(wanted)} s; the limit is ${MAX_FOREGROUND_S} s. ${DETACH_HELP}`,
    };
  }
  return { block: false, input: out };
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", (event: any) => {
    if (event.toolName !== "bash") return;
    const verdict = guardBash(event.input ?? {});
    if (verdict.block) return { block: true, reason: verdict.reason };
    event.input.timeout = verdict.input.timeout;
  });
}
