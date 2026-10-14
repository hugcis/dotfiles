export const COMMENT_VALUE_RULE =
  "Comments are allowed only when they bring actual value to the code by explaining non-obvious reasoning, constraints, risks, or workarounds.";

export type CommentBlock = {
  start_line: number;
  end_line: number;
  line_count: number;
};

export function isPythonPath(path: unknown): path is string {
  return typeof path === "string" && /\.pyi?$/i.test(path);
}

export function buildDiagnostic(path: string, results: CommentBlock[][]): string {
  const locations = results.flatMap((blocks, sourceIndex) =>
    blocks.map((block) => {
      const source = results.length > 1 ? `edit block ${sourceIndex + 1}, ` : "";
      return `- ${source}lines ${block.start_line}-${block.end_line} (${block.line_count} comment lines)`;
    }),
  );

  return [
    `COMMENT DISCIPLINE: cleanup required for ${path}`,
    ...locations,
    "",
    COMMENT_VALUE_RULE,
    "Do not narrate what the code does. Before continuing, remove the flagged comment or reduce it to 1-2 concise lines that explain why it is necessary.",
  ].join("\n");
}
