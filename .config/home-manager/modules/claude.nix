{ config, pkgs, ... }:

{
  # Claude Code statusline, migrated from the bare repo (~/.claude/statusline.sh).
  # Referenced by ~/.claude/settings.json (kept raw: Claude Code appends
  # permission entries to it interactively, so it is app-mutable state that
  # does not belong in the store). The script itself is read-only tooling.
  # The macOS-specific bits (security, Claude usage API) are all guarded and
  # degrade silently on linux hosts.
  home.file.".claude/statusline.sh".source = ../configs/claude/statusline.sh;
}
