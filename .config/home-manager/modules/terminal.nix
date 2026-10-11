{ config, lib, pkgs, ... }:

{
  # Migrated from the bare repo. The keybind DSL dominates this file and
  # gains nothing from Nix encoding, so it stays real KDL — symlinked into
  # ~/.config/zellij. Only the binary is Nix-managed.
  programs.zellij = {
    enable = true;
  };
  xdg.configFile."zellij/config.kdl".source = ../configs/zellij.kdl;

  # Migrated from the bare repo (oh-my-tmux). The config deliberately stays
  # raw text; local overrides live in ~/.tmux.conf.local — also migrated
  # from the bare repo, so tweaks now go through the repo + `hm` switch
  # rather than ad-hoc edits (the symlink is read-only).
  home.file = {
    ".tmux.conf".source = ../configs/tmux.conf;
    ".tmux.conf.local".source = ../configs/tmux.conf.local;
  };

  # Alacritty's font. On macOS CoreText does not see nix-installed fonts,
  # so the brew cask font stays the real provider there (see Brewfile);
  # on linux fontconfig hosts this package makes the font portable.
  home.packages = lib.mkIf config.hq.desktop [ pkgs.nerd-fonts.meslo-lg ];

  # Migrated from the bare repo (alacritty.toml). The old file sent bare
  # ESC+CR for Shift+Enter, which zellij re-encodes ambiguously; it now sends
  # the kitty CSI-u sequence, which zellij binds (see configs/zellij.kdl) and
  # re-emits so CSI-u-aware apps (Claude Code, crossterm/Ink apps) insert a
  # newline instead of submitting.
  #
  # GUI-launched Alacritty inherits launchd's minimal PATH, not the shell
  # PATH, so the zellij program must be an absolute path. The home-manager
  # profile path is stable across hosts and across switches (only its store
  # target changes), so this lives in shared config, not per-host files.
  programs.alacritty = lib.mkIf config.hq.desktop {
    enable = true;
    settings = {
      bell = {
        animation = "Ease";
        duration = 0;
      };
      cursor.style = {
        blinking = "On";
        shape = "Block";
      };
      font = {
        size = 12.0;
        normal = {
          family = "MesloLGS Nerd Font Mono";
          style = "Regular";
        };
      };
      selection.save_to_clipboard = false;
      window = {
        decorations = "buttonless";
        startup_mode = "Fullscreen";
        title = "Alacritty";
      };
      terminal.shell.program = "${config.home.homeDirectory}/.local/state/nix/profiles/home-manager/home-path/bin/zellij";
      keyboard.bindings = [
        { key = "I"; mode = "Vi|~Search"; action = "ScrollToBottom"; }
        { key = "I"; mode = "Vi|~Search"; action = "ToggleViMode"; }
        { key = "G"; mode = "Vi|~Search"; action = "ScrollToTop"; }
        { key = "G"; mods = "Shift"; mode = "Vi|~Search"; action = "ScrollToBottom"; }
        { key = "B"; mods = "Control"; mode = "Vi|~Search"; action = "ScrollPageUp"; }
        { key = "F"; mods = "Control"; mode = "Vi|~Search"; action = "ScrollPageDown"; }
        { key = "Y"; mode = "Vi|~Search"; action = "Copy"; }
        { key = "Y"; mode = "Vi|~Search"; action = "ClearSelection"; }
        { key = "V"; mode = "Vi|~Search"; action = "ToggleNormalSelection"; }
        { key = "V"; mods = "Shift"; mode = "Vi|~Search"; action = "ToggleLineSelection"; }
        { key = "V"; mods = "Control"; mode = "Vi|~Search"; action = "ToggleBlockSelection"; }
        { key = "V"; mods = "Alt"; mode = "Vi|~Search"; action = "ToggleSemanticSelection"; }
        { key = "K"; mode = "Vi|~Search"; action = "Up"; }
        { key = "J"; mode = "Vi|~Search"; action = "Down"; }
        { key = "H"; mode = "Vi|~Search"; action = "Left"; }
        { key = "L"; mode = "Vi|~Search"; action = "Right"; }
        { key = "Slash"; mode = "Vi|~Search"; action = "SearchForward"; }
        { key = "Slash"; mods = "Shift"; mode = "Vi|~Search"; action = "SearchBackward"; }
        { key = "N"; mode = "Vi|~Search"; action = "SearchNext"; }
        { key = "N"; mods = "Shift"; mode = "Vi|~Search"; action = "SearchPrevious"; }
        { key = "Return"; mode = "Search|Vi"; action = "SearchConfirm"; }
        { key = "Escape"; mode = "Search"; action = "SearchCancel"; }
        { key = "Return"; mode = "Search|~Vi"; action = "SearchFocusNext"; }
        { key = "Return"; mods = "Shift"; mode = "Search|~Vi"; action = "SearchFocusPrevious"; }
        { key = "V"; mods = "Command"; action = "Paste"; }
        { key = "C"; mods = "Command"; action = "Copy"; }
        { key = "Return"; mods = "Shift"; chars = "\\u001b[13;2u"; }
      ];
    };
  };
}
