{ config, lib, pkgs, ... }:

{
  # Migrated from the bare repo (.vimrc, .vim/, .doom.d/). Both editors stay
  # raw text — only the files are symlinked. Vim plugin clones under
  # .vim/pack/ (self-contained git checkouts) and Doom's runtime state
  # (custom.el, snippets/, bin/) are not managed here and stay live files.
  home.file = {
    ".vimrc".source = ../configs/vim/vimrc;
    ".vim/colors/solarized.vim".source = ../configs/vim/colors/solarized.vim;
    ".vim/UltiSnips/tex.snippets".source = ../configs/vim/UltiSnips/tex.snippets;
    ".vim/spell/fr.utf-8.spl".source = ../configs/vim/spell/fr.utf-8.spl;
    ".vim/spell/fr.utf-8.sug".source = ../configs/vim/spell/fr.utf-8.sug;

    ".doom.d/init.el".source = ../configs/doom/init.el;
    ".doom.d/config.el".source = ../configs/doom/config.el;
    ".doom.d/packages.el".source = ../configs/doom/packages.el;
    ".doom.d/org-config.el".source = ../configs/doom/org-config.el;
    ".doom.d/org-config.org".source = ../configs/doom/org-config.org;
  };
}
