import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runPolicy,
  runShipCheckGate,
  needsFailClosed,
  failClosedReason,
  PRE_TOOL_MAP,
  POST_TOOL_MAP,
} from "./policy-adapter.ts";

// Thin adapter: forwards Pi tool events to the shared policy engine
// (~/.config/agent-stack/hooks/policy.py), the same guard Vibe runs as a
// [[hooks]] command.
//
// Event mapping:
//   tool_call   -> pre_tool   (deny via {block}, or rewrite event.input)
//   tool_result -> post_tool  (redact via replaced content, or append context)
//
// A policy error blocks destructive-looking bash and allows everything else:
// the guard's whole value is the destructive cases, and nudges are not worth
// a stalled session.

// Pull the plain text out of a tool-result content array.
function contentText(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content
    .map((b) =>
      b && typeof b === "object" && (b as any).type === "text" ? String((b as any).text ?? "") : "",
    )
    .join("");
}

export default function (pi: ExtensionAPI) {
  // --- pre_tool: deny or rewrite ---------------------------------------
  pi.on("tool_call", async (event: any) => {
    const toolName = PRE_TOOL_MAP[event.toolName];
    if (!toolName) return;

    const command = typeof event.input?.command === "string" ? event.input.command : "";
    const outcome = runPolicy({
      hook_event_name: "pre_tool",
      tool_name: toolName,
      tool_input: event.input,
      cwd: process.cwd(),
    });

    if (outcome.status === "error") {
      if (toolName === "bash" && needsFailClosed(command)) {
        return { block: true, reason: failClosedReason(command, outcome.detail) };
      }
      return;
    }
    if (outcome.status === "verdict") {
      const verdict = outcome.verdict;
      if (verdict.decision === "deny") {
        return { block: true, reason: verdict.reason ?? "Blocked by the agent-stack policy guard." };
      }

      // Rewrite: policy.py may return a patched tool_input. Mutate in place
      // (Pi honors mutations to event.input; return only controls blocking).
      const rewritten = verdict.hook_specific_output?.tool_input;
      if (rewritten && typeof rewritten === "object") {
        for (const k of Object.keys(event.input)) delete event.input[k];
        Object.assign(event.input, rewritten);
      }
    }

    if (toolName === "bash") {
      const gate = runShipCheckGate({
        tool_name: "bash",
        tool_input: event.input,
        cwd: process.cwd(),
      });
      if (gate.status === "error") {
        return { block: true, reason: `ship-check gate failed closed: ${gate.detail}` };
      }
      if (gate.status === "verdict" && gate.verdict.decision === "deny") {
        return { block: true, reason: gate.verdict.reason ?? "Blocked by the ship-check gate." };
      }
    }
    // Soft pre_tool system_message nudges are dropped here: a blocking hook
    // has no advisory-only channel (same choice as the opencode plugin).
  });

  // --- post_tool: redact or append context -----------------------------
  pi.on("tool_result", async (event: any) => {
    const toolName = POST_TOOL_MAP[event.toolName];
    if (!toolName) return;

    const outcome = runPolicy({
      hook_event_name: "post_tool",
      tool_name: toolName,
      tool_input: event.input,
      tool_output_text: contentText(event.content),
      cwd: process.cwd(),
    });
    if (outcome.status !== "verdict") return;
    const verdict = outcome.verdict;

    // Redaction reuses the deny channel: reason holds the redacted text.
    if (verdict.decision === "deny" && verdict.reason) {
      return { content: [{ type: "text", text: verdict.reason }] };
    }

    const extra = verdict.hook_specific_output?.additional_context ?? verdict.system_message;
    if (extra) {
      return {
        content: [
          ...(Array.isArray(event.content) ? event.content : []),
          { type: "text", text: `\n\n${extra}` },
        ],
      };
    }
  });
}
