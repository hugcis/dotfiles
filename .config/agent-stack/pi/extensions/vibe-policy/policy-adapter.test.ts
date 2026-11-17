import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  runPolicy,
  runShipCheckGate,
  failClosedReason,
  POLICY_PATH,
  PRE_TOOL_MAP,
  POST_TOOL_MAP,
} from "./policy-adapter.ts";

// The stack's own hook, not whatever is installed on this host.
const STACK_POLICY = fileURLToPath(new URL("../../../hooks/policy.py", import.meta.url));

// Site roots the suite controls, so it does not depend on this machine's
// policy.local.json.
const site = mkdtempSync(join(tmpdir(), "vibe-policy-"));
writeFileSync(
  join(site, "policy.local.json"),
  JSON.stringify({ broad_roots: ["/srv/data"], repo_roots: ["/home/dev/repo"] }),
);
process.env.AGENT_STACK_POLICY_LOCAL = join(site, "policy.local.json");

const preTool = (command: string, cwd = "/home/dev/repo") =>
  runPolicy(
    { hook_event_name: "pre_tool", tool_name: "bash", tool_input: { command }, cwd },
    { policyPath: STACK_POLICY },
  );

test("the adapter points at the stack's own hook", () => {
  assert.match(POLICY_PATH, /\.config\/agent-stack\/hooks\/policy\.py$/);
});

test("destructive bash is blocked", () => {
  const outcome = preTool("rm -rf /home/dev/repo");
  assert.equal(outcome.status, "verdict");
  assert.equal(outcome.status === "verdict" && outcome.verdict.decision, "deny");
});

test("benign bash yields an explicit allow, not an error", () => {
  assert.equal(preTool("ls -la", "/tmp").status, "allow");
});

test("a missing policy.py is an error outcome, not a silent allow", () => {
  const outcome = runPolicy(
    { hook_event_name: "pre_tool", tool_name: "bash", tool_input: { command: "rm -rf x" } },
    { policyPath: "/nonexistent/policy.py" },
  );
  assert.equal(outcome.status, "error");
});

test("an unserialisable payload is an error outcome, not a silent allow", () => {
  const circular: Record<string, unknown> = {};
  circular.self = circular;
  assert.equal(runPolicy(circular, { policyPath: STACK_POLICY }).status, "error");
});

test("the fail-closed reason names the failure and the command", () => {
  const reason = failClosedReason("rm -rf build", "policy.py timed out after 10000 ms");
  assert.match(reason, /blocked/i);
  assert.match(reason, /timed out/);
  assert.match(reason, /rm -rf build/);
});

test("an ordinary command also fails closed, with no allow-list to dodge", () => {
  // The review found a pattern allow-list here was itself bypassable.
  for (const command of ["git status", "ls", "pytest -q", "definitely-not-matched"]) {
    const reason = failClosedReason(command, "policy.py exited 1");
    assert.match(reason, /blocked/i);
    assert.ok(reason.includes(command));
  }
});

test("Pi tool ids map to policy tool names", () => {
  assert.equal(PRE_TOOL_MAP.bash, "bash");
  assert.equal(PRE_TOOL_MAP.write, "write_file");
  assert.equal(PRE_TOOL_MAP.edit, "edit");
  assert.equal(POST_TOOL_MAP.read, "read_file");
  assert.equal(POST_TOOL_MAP.grep, "grep");
});

test("ship-check gate verdicts are exposed to Pi", () => {
  const gate = join(site, "ship-gate.py");
  writeFileSync(gate, "#!/usr/bin/env python3\nprint('{\\\"decision\\\":\\\"deny\\\",\\\"reason\\\":\\\"no ci\\\"}')\n");
  const outcome = runShipCheckGate({ tool_input: { command: "git push" } }, { gatePath: gate });
  assert.equal(outcome.status, "verdict");
  assert.equal(outcome.status === "verdict" && outcome.verdict.reason, "no ci");
});

test("ship-check gate failures are fail-closed errors", () => {
  const outcome = runShipCheckGate({ tool_input: { command: "git push" } }, { gatePath: "/nonexistent/ship_check_gate.py" });
  assert.equal(outcome.status, "error");
});
