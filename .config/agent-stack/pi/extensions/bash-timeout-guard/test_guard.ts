import { test } from "node:test";
import assert from "node:assert/strict";
import { guardBash, MAX_FOREGROUND_S } from "./index.ts";

const blocked = (command: string, timeout?: number) => guardBash({ command, timeout }).block;

test("every foreground call gets a timeout, never above the cap", () => {
  assert.equal(guardBash({ command: "ls -la" }).input.timeout, MAX_FOREGROUND_S);
  assert.equal(guardBash({ command: "sleep 5", timeout: 30 }).input.timeout, 30);
  assert.equal(guardBash({ command: "true", timeout: 0 }).input.timeout, MAX_FOREGROUND_S);
  assert.equal(guardBash({ command: "true", timeout: 9000 }).input.timeout, MAX_FOREGROUND_S);
});

test("long foreground work is blocked and told to detach", () => {
  assert.equal(blocked("make all", 3600), true);
  assert.match(guardBash({ command: "make", timeout: 3600 }).reason!, /monitor/);
  assert.equal(blocked("timeout 1800 prek run --all-files"), true);
  assert.equal(blocked("run-job --overlap bash t.sh", 1500), true);
  assert.equal(blocked("sleep 3600; queue-status"), true);
  assert.equal(blocked("sleep 2h"), true);
});

test("detached starts return immediately and stay allowed", () => {
  assert.equal(blocked("nohup python long.py > log 2>&1 &"), false);
  assert.equal(blocked("submit-job --time=04:00:00 job.batch"), false);
  assert.equal(blocked("timeout 300 pytest -q tests/x.py"), false);
  assert.equal(blocked("ls -la"), false);
});

test("wide scans are left to the shared policy guard", () => {
  // policy.py owns these; duplicating them here would mean two sets of roots.
  assert.equal(blocked("find / -name x"), false);
  assert.equal(blocked("du -sh ~"), false);
});
