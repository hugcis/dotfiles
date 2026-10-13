{ config, pkgs, ... }:

{
  # Migrated from the bare repo (.zshenv and friends). The interactive
  # machinery in .zshrc gains nothing from Nix encoding, so the files stay
  # real zsh — copied verbatim to configs/zsh/ and symlinked into $HOME.
  # The per-OS sourcing (case $OSTYPE inside .zshenv/.zshrc) keeps working
  # unchanged, so there are no .macos/.nix variants to maintain.
  home.file = {
    ".zshenv".source = ../configs/zsh/zshenv;
    ".zshenv.macos".source = ../configs/zsh/zshenv.macos;
    ".zshenv.linux".source = ../configs/zsh/zshenv.linux;
    ".zprofile".source = ../configs/zsh/zprofile;
    ".zshrc".source = ../configs/zsh/zshrc;
    ".zshrc.macos".source = ../configs/zsh/zshrc.macos;
    ".zshrc.linux".source = ../configs/zsh/zshrc.linux;
    # Switch helper, on PATH via ~/.local/bin (see .zprofile).
    ".local/bin/hm".source = ../scripts/hm;
  };
}
