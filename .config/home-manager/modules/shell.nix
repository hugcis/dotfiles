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

  # fzf shell integration, replacing the brew-generated ~/.fzf.zsh (which
  # hardcoded /opt/homebrew paths and pinned the brew copy of fzf). The
  # raw .zshrc sources this file; the store paths are baked in per switch
  # so the nix-installed fzf is always the one providing bindings and
  # completion.
  xdg.configFile."zsh/fzf.zsh".text = ''
    [[ $- == *i* ]] && source "${pkgs.fzf}/share/fzf/completion.zsh" 2> /dev/null
    source "${pkgs.fzf}/share/fzf/key-bindings.zsh"
  '';

  # Oh-my-zsh, migrated from the ~/.oh-my-zsh git clone — the last piece of
  # manual shell bootstrap. The framework comes from nixpkgs and is therefore
  # read-only, which makes omz's self-update machinery inert (updates happen
  # on the next `hm` switch instead). The raw .zshrc sources this file to get
  # $ZSH/$ZSH_CUSTOM before its `source $ZSH/oh-my-zsh.sh` line.
  xdg.configFile."zsh/oh-my-zsh.zsh".text = ''
    export ZSH="${pkgs.oh-my-zsh}/share/oh-my-zsh"
    export ZSH_CUSTOM="$HOME/.config/zsh/omz-custom"
  '';

  # Custom plugin tree that $ZSH_CUSTOM points at. Core plugins used by
  # .zshrc (git, brew, z, shrink-path) ship with the nixpkgs oh-my-zsh.
  xdg.configFile = {
    # Vendored poetry completion (completion-only "plugin", exactly as in
    # the old clone: no plugin.zsh, OMZ just adds the dir to fpath).
    "zsh/omz-custom/plugins/poetry/_poetry".source = ../configs/zsh/poetry/_poetry;
    # nixpkgs layouts are OMZ-compatible; link both files per plugin.
    "zsh/omz-custom/plugins/zsh-autosuggestions/zsh-autosuggestions.plugin.zsh".source = "${pkgs.zsh-autosuggestions}/share/zsh-autosuggestions/zsh-autosuggestions.plugin.zsh";
    "zsh/omz-custom/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh".source = "${pkgs.zsh-autosuggestions}/share/zsh-autosuggestions/zsh-autosuggestions.zsh";
    # zsh-syntax-highlighting ships no OMZ shim, so generate one; the store
    # file resolves its highlighters relative to its own location.
    "zsh/omz-custom/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.plugin.zsh".text = ''
      source "${pkgs.zsh-syntax-highlighting}/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
    '';
  };
}
