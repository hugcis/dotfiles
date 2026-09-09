#!/usr/bin/env bash
set -euo pipefail
STACK="$HOME/.config/agent-stack"
CFG="$HOME/.cfg"

# Ignore rule FIRST, before anything else can stage a file.
#
# The whole public/private boundary of this repo is one `*` in the bare repo's
# info/exclude. Git NEVER transfers info/exclude on clone -- it is per-clone
# local state -- so a fresh clone is unprotected and the first `config add -A`
# there would stage every untracked private file in $HOME.
if [[ ! -d "$CFG" ]]; then
	echo "No bare dotfiles repo at $CFG."
	echo "Clone it first, then re-run this script:"
	echo "  git clone --bare <url> \"$CFG\""
	exit 1
fi

EXCLUDE="$(git --git-dir="$CFG" rev-parse --git-path info/exclude)"
if [[ -f "$EXCLUDE" ]] && grep -qx '\*' "$EXCLUDE"; then
	echo "ignore rule already present: $EXCLUDE"
else
	mkdir -p "$(dirname "$EXCLUDE")"
	if [[ -s "$EXCLUDE" ]]; then # separate from whatever is already there
		printf '\n' >>"$EXCLUDE"
	fi
	cat >>"$EXCLUDE" <<'RULE'
# Ignore everything by default.
# Tracked files are unaffected by ignore rules, so every tracked path keeps
# working normally. To start tracking something new:
#     config add -f <path>
*
RULE
	echo "added ignore rule '*' to $EXCLUDE"
fi

command -v python3 >/dev/null || {
	echo "python3 required"
	exit 1
}
# ce-artifact-root evaluates Python 3.10 union annotations at import time.
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null || {
	echo "Python 3.10 or newer is required; select a supported python3 on PATH."
	exit 1
}
python3 -c "import yaml" 2>/dev/null || {
	echo "PyYAML is required for the selected python3; install it in that interpreter's environment."
	exit 1
}

if [[ ! -f "$STACK/profile.yaml" ]]; then
	echo "No profile.yaml. Copy profile.example.yaml and fill it in first."
	exit 1
fi

# Check prerequisites before preparation can replace sources, and validate
# every rendered output before activation.
python3 "$STACK/methodology.py" preflight --profile "$STACK/profile.yaml"
python3 "$STACK/methodology.py" prepare --profile "$STACK/profile.yaml"
python3 "$STACK/render.py" validate --profile "$STACK/profile.yaml"
python3 "$STACK/methodology.py" activate --profile "$STACK/profile.yaml"
python3 "$STACK/render.py"
python3 "$STACK/methodology.py" doctor --profile "$STACK/profile.yaml"

# Shell wiring: source profile.env if not already wired.
for rc in "$HOME/.zshenv.linux" "$HOME/.zshenv.macos"; do
	[[ -f "$rc" ]] || continue
	grep -q 'agent-stack/profile.env' "$rc" ||
		echo '[ -f "$HOME/.config/agent-stack/profile.env" ] && source "$HOME/.config/agent-stack/profile.env"' >>"$rc"
done

echo "agent-stack installed."
