{ config, lib, pkgs, ... }:

{
  # Daily-driver CLI tools, migrated from the Brewfile. After each addition,
  # uninstall the brew twin — after the PATH priority fix in .zprofile the
  # nix copy silently wins, and a stale brew copy only causes confusion.
  # Same rule for pacman on arch/pi (.packages.arch).
  home.packages = with pkgs; [
    ripgrep
    fd
    bat
    fzf
    lsd
    btop
    htop
    tree
    ncdu
    tmux
    tig
    gh
    wget
    tokei
    pv
    just
    glow
    pipx
  ] ++ lib.optionals pkgs.stdenv.hostPlatform.isDarwin [
    xcodes
  ];
}
