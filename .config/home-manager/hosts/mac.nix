{
  home.username = "hugo";
  home.homeDirectory = "/Users/hugo";

  # GUI-launched Alacritty inherits launchd's minimal PATH, not the shell
  # PATH, so the zellij program must be an absolute path.
  programs.alacritty.settings.terminal.shell.program = "/opt/homebrew/bin/zellij";
}
