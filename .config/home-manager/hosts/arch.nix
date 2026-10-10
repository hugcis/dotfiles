{
  home.username = "hugo";
  home.homeDirectory = "/home/hugo";

  # TODO on the Arch box: verify username/homedir, point Alacritty at the
  # zellij binary there (absolute path), and migrate remaining .zshenv.linux /
  # .zshrc.linux / .packages.arch content here as host-specific modules.
  programs.alacritty.settings.terminal.shell.program = "/usr/bin/zellij";
}
