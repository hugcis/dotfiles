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
python3 -c "import yaml" 2>/dev/null || {
	echo "pip install pyyaml"
	exit 1
}

if [[ ! -f "$STACK/profile.yaml" ]]; then
	echo "No profile.yaml. Copy profile.example.yaml and fill it in first."
	exit 1
fi

# prepare -> activate -> render -> doctor.
#
# Activation is transactional and rendering is not, so the switch of skill
# links and pi packages happens first: a rejected activation rolls itself back
# and aborts here, leaving the instruction files describing the methodology
# that is still installed. Rendering the fragment before activating would
# publish instructions for a methodology the harnesses never got.
python3 "$STACK/methodology.py" prepare --profile "$STACK/profile.yaml"
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
