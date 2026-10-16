import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// A primary checkout has a `.git` directory; linked worktrees have a `.git`
// file. Only repositories with a remote count, so scratch repos stay editable.
export function primaryCheckoutRoot(file: string): string | undefined {
  let dir = dirname(resolve(file));
  while (true) {
    const git = `${dir}/.git`;
    if (existsSync(git)) {
      if (!statSync(git).isDirectory()) return undefined;
      const config = `${git}/config`;
      return existsSync(config) && readFileSync(config, "utf8").includes("[remote ") ? dir : undefined;
    }
    const parent = dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", (event, ctx) => {
    if (event.toolName !== "edit" && event.toolName !== "write") return;
    const path = (event.input as { path?: unknown }).path;
    if (typeof path !== "string") return;
    const root = primaryCheckoutRoot(resolve(ctx.cwd, path));
    if (!root) return;
    return {
      block: true,
      reason: `${root} is a primary checkout. Create a new branch and worktree first (git -C ${root} worktree add -b <branch> <path>), then edit there.`,
    };
  });
}
