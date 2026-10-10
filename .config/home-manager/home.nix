{ config, pkgs, ... }:

{
  home.username = "hugo";
  home.homeDirectory = "/Users/hugo";

  # Do not change after first switch; only set to the release you started with.
  home.stateVersion = "25.05";

  # Installs the home-manager CLI into the profile at
  # ~/.local/state/nix/profiles/home-manager (wired into PATH in .zshenv.macos).
  programs.home-manager.enable = true;

  # Migrated from the bare repo. The keybind DSL dominates this file and
  # gains nothing from Nix encoding, so it stays real KDL — symlinked into
  # ~/.config/zellij. Only the binary is Nix-managed.
  programs.zellij.enable = true;
  xdg.configFile."zellij/config.kdl".source = ./configs/zellij.kdl;

  # Migrated from the bare repo (alacritty.toml). The old file sent bare
  # ESC+CR for Shift+Enter, which zellij re-encodes ambiguously; it now sends
  # the kitty CSI-u sequence, which zellij binds (see configs/zellij.kdl) and
  # re-emits so CSI-u-aware apps (Claude Code, crossterm/Ink apps) insert a
  # newline instead of submitting.
  programs.alacritty = {
    enable = true;
    settings = {
      bell = {
        animation = "Ease";
        duration = 0;
      };
      cursor.style = {
        blinking = "On";
        shape = "Block";
      };
      font = {
        size = 12.0;
        normal = {
          family = "MesloLGS Nerd Font Mono";
          style = "Regular";
        };
      };
      selection.save_to_clipboard = false;
      terminal.shell.program = "/opt/homebrew/bin/zellij";
      window = {
        decorations = "buttonless";
        startup_mode = "Fullscreen";
        title = "Alacritty";
      };
      keyboard.bindings = [
        { key = "I"; mode = "Vi|~Search"; action = "ScrollToBottom"; }
        { key = "I"; mode = "Vi|~Search"; action = "ToggleViMode"; }
        { key = "G"; mode = "Vi|~Search"; action = "ScrollToTop"; }
        { key = "G"; mods = "Shift"; mode = "Vi|~Search"; action = "ScrollToBottom"; }
        { key = "B"; mods = "Control"; mode = "Vi|~Search"; action = "ScrollPageUp"; }
        { key = "F"; mods = "Control"; mode = "Vi|~Search"; action = "ScrollPageDown"; }
        { key = "Y"; mode = "Vi|~Search"; action = "Copy"; }
        { key = "Y"; mode = "Vi|~Search"; action = "ClearSelection"; }
        { key = "V"; mode = "Vi|~Search"; action = "ToggleNormalSelection"; }
        { key = "V"; mods = "Shift"; mode = "Vi|~Search"; action = "ToggleLineSelection"; }
        { key = "V"; mods = "Control"; mode = "Vi|~Search"; action = "ToggleBlockSelection"; }
        { key = "V"; mods = "Alt"; mode = "Vi|~Search"; action = "ToggleSemanticSelection"; }
        { key = "K"; mode = "Vi|~Search"; action = "Up"; }
        { key = "J"; mode = "Vi|~Search"; action = "Down"; }
        { key = "H"; mode = "Vi|~Search"; action = "Left"; }
        { key = "L"; mode = "Vi|~Search"; action = "Right"; }
        { key = "Slash"; mode = "Vi|~Search"; action = "SearchForward"; }
        { key = "Slash"; mods = "Shift"; mode = "Vi|~Search"; action = "SearchBackward"; }
        { key = "N"; mode = "Vi|~Search"; action = "SearchNext"; }
        { key = "N"; mods = "Shift"; mode = "Vi|~Search"; action = "SearchPrevious"; }
        { key = "Return"; mode = "Search|Vi"; action = "SearchConfirm"; }
        { key = "Escape"; mode = "Search"; action = "SearchCancel"; }
        { key = "Return"; mode = "Search|~Vi"; action = "SearchFocusNext"; }
        { key = "Return"; mods = "Shift"; mode = "Search|~Vi"; action = "SearchFocusPrevious"; }
        { key = "V"; mods = "Command"; action = "Paste"; }
        { key = "C"; mods = "Command"; action = "Copy"; }
        { key = "Return"; mods = "Shift"; chars = "\\u001b[13;2u"; }
      ];
    };
  };

  # Migrated from the bare repo (.gitconfig). The module writes
  # ~/.config/git/config (git reads it only after ~/.gitconfig is gone).
  programs.git = {
    enable = true;
    userName = "hugcis";
    userEmail = "hmj.cisneros@gmail.com";

    signing = {
      key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIISAYNU+ArG43Zp4mHI5pm7Wfa4VQ4cV/dgNexczIfpU hugo@Hcis";
      format = "ssh";
      signByDefault = true;
    };

    # NOTE: renamed to `alias` when home.stateVersion reaches 26.11.
    aliases = {
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

    settings = {
      core.excludesfile = "~/.gitexclude";
      pull.ff = "only";
      init.defaultBranch = "main";
      push.default = "simple";
      fetch.prune = true;
      url."github-work:last_genocto/".insteadOf = "git@github.com:last_genocto/";
      credential."https://github.com".helper = [ "" "!/opt/homebrew/bin/gh auth git-credential" ];
      credential."https://gist.github.com".helper = [ "" "!/opt/homebrew/bin/gh auth git-credential" ];
    };
  };

  # Migrated from the bare repo (starship.toml). Shell init stays manual in
  # .zshrc; this only owns the config file.
  programs.starship = {
    enable = true;
    settings = {
      "$schema" = "https://starship.rs/config-schema.json";
      add_newline = true;
      continuation_prompt = "[▸▹ ](dimmed white)";
      format = "($fill$git_metrics\n)$cmd_duration$username$hostname$jobs$sudo$character";
      right_format = "$directory$git_branch$git_status$docker_context$nodejs$python$rust$package$time";

      fill.symbol = " ";

      character = {
        format = "$symbol ";
        success_symbol = "[◎](bold italic bright-yellow)";
        error_symbol = "[○](italic purple)";
        vimcmd_symbol = "[■](italic dimmed green)";
      };

      username = {
        style_user = "bright-yellow bold italic";
        style_root = "purple bold italic";
        format = "[⭘ $user]($style)";
        show_always = true;
        disabled = false;
      };

      hostname = {
        ssh_only = false;
        format = "[@$hostname](italic dimmed bright-cyan) ";
        trim_at = ".";
        disabled = false;
      };

      sudo = {
        format = "[$symbol]($style)";
        style = "bold italic bright-purple";
        symbol = "⋈┈";
        disabled = false;
      };

      jobs = {
        format = "[$symbol$number]($style) ";
        style = "white";
        symbol = "[▶](blue italic)";
      };

      cmd_duration.format = "[◄ $duration ](italic white)";

      directory = {
        home_symbol = "⌂";
        truncation_length = 2;
        truncation_symbol = "□ ";
        read_only = " ◈";
        use_os_path_sep = true;
        style = "italic blue";
        format = "[$path]($style)[$read_only]($read_only_style)";
        repo_root_style = "bold blue";
        repo_root_format = "[$before_root_path]($before_repo_root_style)[$repo_root]($repo_root_style)[$path]($style)[$read_only]($read_only_style) [△](bold bright-blue)";
      };

      git_branch = {
        format = " [$branch(:$remote_branch)]($style)";
        symbol = "[△](bold italic bright-blue)";
        style = "italic bright-blue";
        truncation_symbol = "⋯";
        truncation_length = 40;
        ignore_branches = [ "main" "master" ];
        only_attached = true;
      };

      git_metrics = {
        format = "([▴$added]($added_style))([▿$deleted]($deleted_style))";
        added_style = "italic dimmed green";
        deleted_style = "italic dimmed red";
        ignore_submodules = true;
        disabled = false;
      };

      git_status = {
        style = "bold italic bright-blue";
        format = "([⎪$ahead_behind$staged$modified$untracked$renamed$deleted$conflicted$stashed⎥]($style))";
        conflicted = "[◪◦](italic bright-magenta)";
        ahead = "[▴│[\${count}](bold white)│](italic green)";
        behind = "[▿│[\${count}](bold white)│](italic red)";
        diverged = "[◇ ▴┤[\${ahead_count}](regular white)│▿┤[\${behind_count}](regular white)│](italic bright-magenta)";
        untracked = "[◌◦](italic bright-yellow)";
        stashed = "[◃◈](italic white)";
        modified = "[●◦](italic yellow)";
        staged = "[▪┤[$count](bold white)│](italic bright-cyan)";
        renamed = "[◎◦](italic bright-blue)";
        deleted = "[✕](italic red)";
      };

      docker_context = {
        symbol = "◧ ";
        format = " docker [$symbol$context](italic dimmed cyan)";
      };

      nodejs = {
        format = " [node](italic) [◫ ($version)](bold bright-green)";
        version_format = "\${raw}";
        detect_files = [ "package-lock.json" "yarn.lock" "package.json" ];
        detect_folders = [ "node_modules" ];
        detect_extensions = [ ];
      };

      python = {
        format = " [py](italic) [\${symbol}\${version}]($style)";
        symbol = "[⌉](bold bright-blue)⌊ ";
        version_format = "\${raw}";
        style = "bold bright-yellow";
      };

      rust = {
        format = " [rs](italic) [$symbol$version]($style)";
        symbol = "⊃ ";
        version_format = "\${raw}";
        style = "bold red";
      };

      package = {
        format = " [pkg](italic dimmed) [$symbol$version]($style)";
        version_format = "\${raw}";
        symbol = "◨ ";
        style = "dimmed yellow italic bold";
      };

      time = {
        format = "[ $time]($style)";
        time_format = "%R";
        utc_time_offset = "local";
        style = "italic dimmed white";
        disabled = false;
      };
    };
  };

  # Migration pattern, one program at a time:
  #   1. Replace the raw config file here (e.g. programs.zellij.enable + settings).
  #   2. config rm --cached ~/.config/zellij/config.kdl   (stop tracking in the bare repo)
  #   3. Delete the raw file, then `home-manager switch` links the HM-generated one.
  # Home-manager fails loudly on a collision instead of overwriting, so steps
  # taken out of order are recoverable.
}
