{
  home.username = "hugo";
  home.homeDirectory = "/Users/hugo";

  # GUI-launched Alacritty inherits launchd's minimal PATH, not the shell
  # PATH, so the zellij program must be an absolute path. The home-manager
  # profile path is stable (only its store target changes on switch).
  programs.alacritty.settings.terminal.shell.program = "/Users/hugo/.local/state/nix/profiles/home-manager/home-path/bin/zellij";
}
