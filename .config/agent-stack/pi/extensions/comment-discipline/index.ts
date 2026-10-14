import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  isEditToolResult,
  isWriteToolResult,
  type EditToolInput,
  type ExtensionAPI,
  type WriteToolInput,
} from "@earendil-works/pi-coding-agent";
import {
  buildDiagnostic,
  COMMENT_VALUE_RULE,
  isPythonPath,
  type CommentBlock,
} from "./policy.ts";

const ANALYZER_PATH = fileURLToPath(new URL("./analyze_comments.py", import.meta.url));
const PYTHON_POLICY = `${COMMENT_VALUE_RULE} Prefer self-explanatory code and do not narrate what the code does. Keep valuable comments concise.`;

type AnalysisResult = { results: CommentBlock[][] };

function analyzeSources(sources: string[], signal?: AbortSignal): Promise<CommentBlock[][]> {
  return new Promise((resolve, reject) => {
    const child = spawn("python3", [ANALYZER_PATH], {
      stdio: ["pipe", "pipe", "pipe"],
      signal,
    });
    let stdout = "";
    let stderr = "";

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", reject);
    child.stdin.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`comment analyzer exited ${code}: ${stderr.trim()}`));
        return;
      }
      try {
        const parsed = JSON.parse(stdout) as AnalysisResult;
        resolve(parsed.results);
      } catch (error) {
        reject(new Error(`invalid comment analyzer output: ${String(error)}`));
      }
    });

    child.stdin.end(JSON.stringify({ sources }));
  });
}

export default function commentDiscipline(pi: ExtensionAPI) {
  pi.on("before_agent_start", (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n${PYTHON_POLICY}`,
  }));

  pi.on("tool_result", async (event, ctx) => {
    if (event.isError || (!isEditToolResult(event) && !isWriteToolResult(event))) {
      return undefined;
    }

    const input = event.input as unknown as EditToolInput | WriteToolInput;
    if (!isPythonPath(input.path)) return undefined;

    const sources = isEditToolResult(event)
      ? (input as EditToolInput).edits.map((edit) => edit.newText)
      : [(input as WriteToolInput).content];
    if (!sources.some((source) => source.includes("#"))) return undefined;

    try {
      const results = await analyzeSources(sources, ctx.signal);
      if (!results.some((blocks) => blocks.length > 0)) return undefined;

      const diagnostic = buildDiagnostic(input.path, results);
      if (ctx.hasUI) ctx.ui.notify(diagnostic, "warning");
      return {
        content: [{ type: "text" as const, text: diagnostic }, ...event.content],
      };
    } catch (error) {
      if (ctx.signal?.aborted) return undefined;
      console.error(`[comment-discipline] ${String(error)}`);
      if (ctx.hasUI) {
        ctx.ui.notify("Python comment-discipline check failed; the edit was not blocked.", "warning");
      }
      return undefined;
    }
  });
}
