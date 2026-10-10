{ config, lib, pkgs, ... }:

{
  # Migrated from the bare repo (.gitconfig). The module writes
  # ~/.config/git/config (git reads it only after ~/.gitconfig is gone).
  programs.git = {
    enable = true;

    signing = lib.mkIf config.hq.gitSign {
      key = config.hq.gitSignKey;
      format = "ssh";
      signByDefault = true;
    };

    # NOTE: userName/userEmail/aliases were renamed by home-manager
    # (settings.user.*, settings.alias); the old spellings warn on both
    # the master and release-26.05 channels.
    settings = {
      user = {
        name = "hugcis";
        email = "hmj.cisneros@gmail.com";
      };

      alias = {
        co = "checkout";
        ci = "commit";
        st = "status";
        br = "branch";
        hist = ''log --pretty=format:"%h %ad | %s%d [%an]" --graph --date=short'';
        type = "cat-file -t";
        dump = "cat-file -p";
        la = "log --all --graph --oneline --decorate";
        sync = "!dotfiles-sync";
      };

      core.excludesfile = "~/.gitexclude";
      pull.ff = "only";
      init.defaultBranch = "main";
      push.default = "simple";
      fetch.prune = true;
      url."github-work:last_genocto/".insteadOf = "git@github.com:last_genocto/";
      # gh comes from modules/packages.nix; reference its store path so the
      # helper tracks the exact binary the flake installs.
      credential."https://github.com".helper = [ "" "${pkgs.gh}/bin/gh auth git-credential" ];
      credential."https://gist.github.com".helper = [ "" "${pkgs.gh}/bin/gh auth git-credential" ];
    };
  };

  # Migrated from the bare repo (.gitexclude), linked at the same path the
  # git config above expects.
  home.file.".gitexclude".source = ../configs/gitexclude;
}
