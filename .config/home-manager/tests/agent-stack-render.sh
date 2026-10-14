#!/usr/bin/env bash
# Usage: agent-stack-render.sh <path-to-scripts/agent-stack-render>   (python3 on PATH)
#
# The render wrapper runs on every hm switch, so it must skip machines
# without an agent-stack profile and never fail the switch.
set -uo pipefail
script=$1
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
fail=0
expect() {
  if [[ "$2" == *"$3"* ]]; then echo "ok   $1"; else echo "FAIL $1"; echo "     got: $2"; fail=1; fi
}

stack=$t/stack
mkdir -p "$stack"
# Stub renderer: validation fails when the profile contains "broken";
# rendering writes a marker next to itself.
cat > "$stack/render.py" <<'EOF'
import pathlib, sys
here = pathlib.Path(__file__).parent
if sys.argv[1:2] == ["validate"]:
    if "broken" in (here / "profile.yaml").read_text():
        sys.exit("profile.yaml: broken")
    print("agent-stack render validation: ok")
else:
    (here / "rendered").write_text("yes")
    print("rendered 9 agents to 4 harnesses")
EOF

out=$(bash "$script" "$stack" 2>&1); code=$?
expect "no profile: skips" "$out" "no profile.yaml"
expect "no profile: exit 0" "exit=$code" "exit=0"
[[ ! -e "$stack/rendered" ]] && echo "ok   no profile: nothing rendered" || { echo "FAIL no profile: rendered"; fail=1; }

echo "broken: true" > "$stack/profile.yaml"
out=$(bash "$script" "$stack" 2>&1); code=$?
expect "invalid profile: warns" "$out" "WARNING"
expect "invalid profile: shows the validation error" "$out" "profile.yaml: broken"
expect "invalid profile: exit 0" "exit=$code" "exit=0"
[[ ! -e "$stack/rendered" ]] && echo "ok   invalid profile: nothing rendered" || { echo "FAIL invalid profile: rendered"; fail=1; }

echo "ok: true" > "$stack/profile.yaml"
out=$(bash "$script" "$stack" 2>&1); code=$?
expect "valid profile: renders" "$out" "rendered 9 agents"
expect "valid profile: exit 0" "exit=$code" "exit=0"
[[ -e "$stack/rendered" ]] && echo "ok   valid profile: render ran" || { echo "FAIL valid profile: render did not run"; fail=1; }
exit $fail
