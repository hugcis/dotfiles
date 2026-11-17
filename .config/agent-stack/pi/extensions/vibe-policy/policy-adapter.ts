import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";

export type Verdict = {
  decision?: string;
  reason?: string;
  system_message?: string;
  hook_specific_output?: {
    tool_input?: Record<string, unknown>;
    additional_context?: string;
  };
};

// Why a verdict is absent, so the caller can tell "policy said nothing" from
// "policy never answered".
export type Outcome =
  | { status: "verdict"; verdict: Verdict }
  | { status: "allow" }
  | { status: "error"; detail: string };

export const POLICY_PATH = join(homedir(), ".config/agent-stack/hooks/policy.py");
export const POLICY_TIMEOUT_MS = 10_000;

export function runPolicy(payload: unknown, opts: { policyPath?: string } = {}): Outcome {
  let res;
  try {
    res = spawnSync("python3", [opts.policyPath ?? POLICY_PATH], {
      input: JSON.stringify(payload),
      encoding: "utf8",
      timeout: POLICY_TIMEOUT_MS,
    });
  } catch (err) {
    return { status: "error", detail: `could not run policy.py: ${String(err)}` };
  }
  if (res.error) {
    const timedOut = (res.error as NodeJS.ErrnoException).code === "ETIMEDOUT";
    return {
      status: "error",
      detail: timedOut ? `policy.py timed out after ${POLICY_TIMEOUT_MS} ms` : String(res.error.message),
    };
  }
  if (res.signal) return { status: "error", detail: `policy.py killed by ${res.signal}` };
  if (res.status !== 0) {
    return { status: "error", detail: `policy.py exited ${res.status}: ${(res.stderr ?? "").trim()}` };
  }
  const out = (res.stdout ?? "").trim();
  if (!out) return { status: "allow" };
  try {
    return { status: "verdict", verdict: JSON.parse(out) as Verdict };
  } catch {
    return { status: "error", detail: `policy.py printed non-JSON: ${out.slice(0, 200)}` };
  }
}

export function failClosedReason(command: string, detail: string): string {
  return (
    `The policy guard could not check this command, so it is blocked ` +
    `(${detail}). Fix the guard (\`python3 ${POLICY_PATH} < payload.json\`) or run a narrower command. ` +
    `Command: ${command.slice(0, 200)}`
  );
}

// Pi tool id -> policy tool_name. Only listed tools invoke policy.py.
export const PRE_TOOL_MAP: Record<string, string> = {
  bash: "bash",
  edit: "edit",
  write: "write_file",
};

export const POST_TOOL_MAP: Record<string, string> = {
  bash: "bash",
  edit: "edit",
  write: "write_file",
  read: "read_file",
  grep: "grep",
};
