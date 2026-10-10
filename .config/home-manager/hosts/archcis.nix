{
  home.username = "hugcis";
  home.homeDirectory = "/home/hugcis";

  # .packages.arch no longer lists the HM-managed tools (the nix profile
  # provides them and wins PATH); pacman twins already installed on this
  # box still need a one-time removal on the next visit:
  #   sudo pacman -R git fzf ripgrep tmux bat starship github-cli ttf-meslo-nerd
  home.stateVersion = "26.05";

  hq.desktop = true;

  # The SSH signing key (~/.ssh/id_ed25519, "hugo@Hcis") is present on this
  # machine; verified before enabling.
  hq.gitSign = true;
}
