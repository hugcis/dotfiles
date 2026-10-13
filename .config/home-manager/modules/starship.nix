{ config, pkgs, ... }:

{
  # Migrated from the bare repo (starship.toml). Shell init stays manual in
  # .zshrc; this only owns the config file.
  programs.starship = {
    enable = true;
    settings = {
      "$schema" = "https://starship.rs/config-schema.json";
      # The ($fill$git_metrics\n) line above always renders (fill matches
      # even outside repos), so it already provides the blank line between
      # prompts; add_newline would double it.
      add_newline = false;
      continuation_prompt = "[▸▹ ](dimmed white)";
      # ❯ is a constant opener so the prompt keeps its mark on the local
      # machine; user@host joins it only over SSH (see username/hostname).
      format = "($fill$git_metrics\n)$cmd_duration[❯ ](bright-yellow bold italic)$username$hostname$jobs$sudo$character";
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
        format = "[$user]($style)";
        # Local sessions stay bare (❯ only); SSH and root still show $user.
        # username has no ssh_only (that is a hostname key); show_always =
        # false is what limits it to SSH, root, or a switched user.
        show_always = false;
        disabled = false;
      };

      hostname = {
        ssh_only = true;
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

      # Language segments use real Nerd Font brand logos (devicons E7xx,
      # linux icons F3xx, octicons F4xx). Requires a Nerd Font in the
      # terminal: kitty/alacritty run MesloLGS Nerd Font Mono.
      docker_context = {
        symbol = " ";
        format = " [\${symbol}$context](italic dimmed cyan)";
      };

      nodejs = {
        symbol = " ";
        format = " [\${symbol}$version](bold bright-green)";
        version_format = "\${major}.\${minor}";
        detect_files = [ "package-lock.json" "yarn.lock" "package.json" ];
        detect_folders = [ "node_modules" ];
        detect_extensions = [ ];
      };

      python = {
        symbol = " ";
        format = " [\${symbol}$version](bold bright-yellow)";
        version_format = "\${major}.\${minor}";
      };

      rust = {
        symbol = " ";
        format = " [\${symbol}$version](bold red)";
        version_format = "\${major}.\${minor}";
      };

      package = {
        symbol = " ";
        format = " [\${symbol}$version](bold italic dimmed yellow)";
        version_format = "\${major}.\${minor}";
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
}
