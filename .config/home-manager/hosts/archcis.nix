{
  home.username = "hugcis";
  home.homeDirectory = "/home/hugcis";

  # TODO on archcis: prune the HM-managed tools (git, fzf, tmux, starship,
  # bat, ripgrep, gh, tig, ...) from ~/.packages.arch so pacman twins do
  # not shadow the nix profile.
  home.stateVersion = "26.05";

  hq.desktop = true;

  # The SSH signing key (~/.ssh/id_ed25519, "hugo@Hcis") is present on this
  # machine; verified before enabling.
  hq.gitSign = true;
}
