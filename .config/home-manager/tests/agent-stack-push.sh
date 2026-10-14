#!/usr/bin/env bash
# Usage: agent-stack-push.sh <path-to-scripts/agent-stack-push>   (git, tar, python3 on PATH)
#
# Runs agent-stack-push against a fake host: an ssh stub that executes the
# remote command with HOME pointing at a separate directory. Covers what the
# script promises: committed snapshot only, tracked files written and
# deleted, machine-local files kept, drift detection, --force, and the
# remote render.
set -uo pipefail
script=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
fail=0
expect() {
  if [[ "$2" == *"$3"* ]]; then echo "ok   $1"; else echo "FAIL $1"; echo "     got: $2"; fail=1; fi
}
reject() {
  if [[ "$2" != *"$3"* ]]; then echo "ok   $1"; else echo "FAIL $1"; echo "     got: $2"; fail=1; fi
}
same() {
  if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1 ('$2' != '$3')"; fail=1; fi
}

export GIT_CONFIG_NOSYSTEM=1 GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.invalid \
  GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.invalid
L=$t/laptop R=$t/host
mkdir -p "$L/.config/agent-stack" "$R" "$t/bin"
# Absolute bash path: build sandboxes have no /usr/bin/env.
cat > "$t/bin/ssh" <<EOF
#!$BASH
shift
HOME="$R" exec bash -c "\$*"
EOF
chmod +x "$t/bin/ssh"
export PATH="$t/bin:$PATH"

cfg() { HOME="$L" git --git-dir="$L/.cfg" --work-tree="$L" "$@"; }
commit() { cfg add -f .config/agent-stack >/dev/null && cfg commit -q -m "$1"; cfg rev-parse HEAD; }
push() { HOME="$L" bash "$script" host "$@" 2>&1; echo "exit=$?"; }
s=$L/.config/agent-stack h=$R/.config/agent-stack

git init -q --bare "$L/.cfg"
cat > "$s/render.py" <<'EOF'
import pathlib, sys
here = pathlib.Path(__file__).parent
if sys.argv[1:2] == ["validate"]:
    if "broken" in (here / "profile.yaml").read_text():
        sys.exit("profile.yaml: broken")
else:
    (here / "rendered").write_text("yes")
    print("rendered 9 agents")
EOF
echo a1 > "$s/a.txt"; echo b1 > "$s/b.txt"; echo pin1 > "$s/methodologies.yaml"
c1=$(commit c1)

# The host starts at c1, as a checkout of its own dotfiles repo, plus files
# that only exist there.
git clone -q --bare "$L/.cfg" "$R/.cfg"
mkdir -p "$h"
(cd "$L" && git --git-dir="$L/.cfg" archive "$c1" .config/agent-stack) | tar -xf - -C "$R"
echo "ok: true" > "$h/profile.yaml"; echo local > "$h/local.md"

echo "== first push: base is the host repo's HEAD"
echo a2 > "$s/a.txt"; cfg rm -q .config/agent-stack/b.txt; echo c2 > "$s/c.txt"; echo pin2 > "$s/methodologies.yaml"
c2=$(commit c2)
out=$(push)
expect "first push succeeds" "$out" "exit=0"
same "tracked file updated" "$(cat "$h/a.txt")" "a2"
[[ ! -e "$h/b.txt" ]] && echo "ok   deleted file removed" || { echo "FAIL deleted file still there"; fail=1; }
same "new file added" "$(cat "$h/c.txt")" "c2"
same "profile.yaml kept" "$(cat "$h/profile.yaml")" "ok: true"
same "local-only file kept" "$(cat "$h/local.md")" "local"
same "rendered on the host" "$(cat "$h/rendered" 2>/dev/null)" "yes"
same "pushed revision recorded" "$(cat "$h/.pushed-rev")" "$c2"
expect "methodology change hinted" "$out" "methodology.py preflight"

echo "== drift: a file edited on the host stops the push"
echo edited-on-host > "$h/a.txt"
echo c3 > "$s/c.txt"; c3=$(commit c3)
out=$(push)
expect "drift refuses" "$out" "exit=1"
expect "drift names the file" "$out" "edited on host: .config/agent-stack/a.txt"
expect "drift shows the diff" "$out" "+edited-on-host"
same "nothing written on refusal" "$(cat "$h/c.txt")" "c2"
same "pushed revision unchanged on refusal" "$(cat "$h/.pushed-rev")" "$c2"
reject "no methodology hint without a change" "$out" "methodology.py preflight"

echo "== --force overwrites the host edit"
out=$(push --force)
expect "force succeeds" "$out" "exit=0"
same "host edit overwritten" "$(cat "$h/a.txt")" "a2"
same "pushed revision advanced" "$(cat "$h/.pushed-rev")" "$c3"

echo "== a host edit that already matches the new version is not drift"
echo a4 > "$h/a.txt"; echo a4 > "$s/a.txt"; c4=$(commit c4)
out=$(push)
expect "matching edit passes" "$out" "exit=0"
same "pushed revision advanced" "$(cat "$h/.pushed-rev")" "$c4"

echo "== an untracked host file in the way of a new tracked file is drift"
echo host-only > "$h/new.txt"; echo tracked > "$s/new.txt"; c5=$(commit c5)
out=$(push)
expect "collision refuses" "$out" "exit=1"
expect "collision names the file" "$out" "untracked on host: .config/agent-stack/new.txt"
out=$(push --force)
same "force replaces it" "$(cat "$h/new.txt")" "tracked"

echo "== uncommitted laptop changes are refused"
echo dirty > "$s/a.txt"
out=$(push)
expect "uncommitted refuses" "$out" "exit=1"
expect "uncommitted explains" "$out" "uncommitted changes"
cfg checkout -q -- .config/agent-stack/a.txt

echo "== a failed render on the host is reported"
echo "broken: true" > "$h/profile.yaml"; echo a6 > "$s/a.txt"; c6=$(commit c6)
out=$(push)
expect "render failure exits non-zero" "$out" "exit=1"
expect "render failure shows the error" "$out" "profile.yaml: broken"
same "files are still pushed" "$(cat "$h/a.txt")" "a6"
exit $fail
