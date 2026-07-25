#!/usr/bin/env bash
set -euo pipefail
STACK="$HOME/.config/agent-stack"

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

# Skills: one source, symlinked into each harness.
#
# NOTE: ~/.pi/agent/skills ships as a symlink to ~/.vibe/skills, so the two are one
# directory under two names. Replace any symlinked destination with a real directory
# first, otherwise the pi and vibe passes write into the same place and the
# "independent harness" model silently breaks.
for dest in "$HOME/.pi/agent/skills" "$HOME/.claude/skills" "$HOME/.vibe/skills"; do
	if [[ -L "$dest" ]]; then
		echo "unlinking aliased skills dir: $dest -> $(readlink "$dest")"
		unlink "$dest" # removes the link only, never the target's contents
	fi
	mkdir -p "$dest"
	backup_dir=""
	for skill in "$STACK"/skills/*/; do
		name="$(basename "$skill")"
		link="$dest/$name"
		if [[ -e "$link" && ! -L "$link" ]]; then
			if [[ -z "$backup_dir" ]]; then
				backup_dir="${AGENT_STACK_BACKUP_DIR:-$HOME/.local/state/agent-stack/replaced-skills/$(date +%Y%m%d%H%M%S)-$$}"
				mkdir -p "$backup_dir"
			fi
			safe_dest="${dest#$HOME/}"
			safe_dest="${safe_dest//\//__}"
			mkdir -p "$backup_dir/$safe_dest"
			echo "moving existing skills entry: $link -> $backup_dir/$safe_dest/$name"
			mv "$link" "$backup_dir/$safe_dest/$name"
		fi
		ln -sfn "$skill" "$link"
	done
done

python3 "$STACK/render.py"

# Shell wiring: source profile.env if not already wired.
for rc in "$HOME/.zshenv.linux" "$HOME/.zshenv.macos"; do
	[[ -f "$rc" ]] || continue
	grep -q 'agent-stack/profile.env' "$rc" ||
		echo '[ -f "$HOME/.config/agent-stack/profile.env" ] && source "$HOME/.config/agent-stack/profile.env"' >>"$rc"
done

echo "agent-stack installed."
