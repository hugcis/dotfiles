import assert from "node:assert/strict";
import { buildDiagnostic, isPythonPath } from "./policy.ts";

assert.equal(isPythonPath("src/example.py"), true);
assert.equal(isPythonPath("stubs/example.pyi"), true);
assert.equal(isPythonPath("src/example.ts"), false);

const diagnostic = buildDiagnostic("src/example.py", [
  [{ start_line: 2, end_line: 4, line_count: 3 }],
]);
assert.match(diagnostic, /cleanup required/);
assert.match(diagnostic, /actual value/);
assert.match(diagnostic, /why it is necessary/);
assert.match(diagnostic, /lines 2-4/);

console.log("extension helper tests passed");
