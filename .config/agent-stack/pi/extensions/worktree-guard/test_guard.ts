import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { primaryCheckoutRoot } from "./index.ts";

const git = (cwd: string, ...args: string[]) => execFileSync("git", args, { cwd, stdio: "ignore" });
const root = mkdtempSync(join(tmpdir(), "worktree-guard-"));

const scratch = join(root, "scratch");
mkdirSync(scratch);
git(scratch, "init", "-q");
assert.equal(primaryCheckoutRoot(join(scratch, "a.txt")), undefined);

git(scratch, "remote", "add", "origin", "https://example.invalid/repo.git");
mkdirSync(join(scratch, "src"));
assert.equal(primaryCheckoutRoot(join(scratch, "src", "a.py")), scratch);

git(scratch, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "init");
const linked = join(root, "linked");
git(scratch, "worktree", "add", "-q", "-b", "feature", linked);
assert.equal(primaryCheckoutRoot(join(linked, "a.py")), undefined);

assert.equal(primaryCheckoutRoot(join(root, "outside.txt")), undefined);

console.log("worktree-guard tests passed");
