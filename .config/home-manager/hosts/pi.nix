{
  home.username = "hugo";
  home.homeDirectory = "/home/hugo";

  # TODO on the Pi: verify username/homedir, and prune the HM-managed tools
  # (git, fzf, tmux, starship, bat, ripgrep, gh, tig, ...) from
  # ~/.packages.arch so pacman twins do not shadow the nix profile.
  home.stateVersion = "26.05";

  # Headless by default. Flip to true if the Pi runs a desktop with
  # Alacritty; zellij/tmux/starship and the CLI set come either way.
  hq.desktop = false;

  # TODO: provision the SSH signing key on the Pi, then enable.
  hq.gitSign = false;
}
