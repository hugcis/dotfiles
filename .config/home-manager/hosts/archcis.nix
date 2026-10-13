{
  home.username = "hugcis";
  home.homeDirectory = "/home/hugcis";

  # .packages.arch no longer lists the HM-managed tools (the nix profile
  # provides them and wins PATH). pacman twins removed on 2026-10-10,
  # except git: yay depends on it, so the pacman copy stays as a system
  # dependency, shadowed by the nix git on PATH. fzf/github-cli/fonts were
  # never pacman-installed here.
  home.stateVersion = "26.05";

  hq.desktop = true;

  # The SSH signing key (~/.ssh/id_ed25519, "hugo@Hcis") is present on this
  # machine; verified before enabling.
  hq.gitSign = true;
}
