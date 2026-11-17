import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  runPolicy,
  needsFailClosed,
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

test("destructive patterns are recognised for fail-closed handling", () => {
  for (const command of [
    "rm -rf build",
    "git reset --hard",
    "git clean -fdx",
    "git commit --no-gpg-sign -m x",
    "git -c commit.gpgsign=false commit -m x",
    "find / -name x",
    "du -sh ~",
    "grep -r foo /",
    "rg foo /srv/data",
    "ls -R /srv/data",
    'set -x; curl -H "Authorization: Bearer $API_KEY" https://example.test',
    "echo start && rm -rf build",
    'bash -c "rm -rf /"',
    "sh -c 'git reset --hard'",
    'eval "git reset --hard"',
    "git push --force origin main",
    "echo x > ~/.local/state/ship-check/r/a.json",
  ]) {
    assert.equal(needsFailClosed(command), true, command);
  }
});

test("ordinary commands are not forced closed", () => {
  for (const command of ["git status", "ls", "pytest -q tests", "make build", "cat notes.txt"]) {
    assert.equal(needsFailClosed(command), false, command);
  }
});

test("the fail-closed reason names the failure and the command", () => {
  const reason = failClosedReason("rm -rf build", "policy.py timed out after 10000 ms");
  assert.match(reason, /blocked/i);
  assert.match(reason, /timed out/);
  assert.match(reason, /rm -rf build/);
});

test("Pi tool ids map to policy tool names", () => {
  assert.equal(PRE_TOOL_MAP.bash, "bash");
  assert.equal(PRE_TOOL_MAP.write, "write_file");
  assert.equal(PRE_TOOL_MAP.edit, "edit");
  assert.equal(POST_TOOL_MAP.read, "read_file");
  assert.equal(POST_TOOL_MAP.grep, "grep");
});
