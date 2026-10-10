{ config, pkgs, ... }:

{
  home.username = "hugo";
  home.homeDirectory = "/Users/hugo";

  # Do not change after first switch; only set to the release you started with.
  home.stateVersion = "25.05";

  # Installs the home-manager CLI into the profile at
  # ~/.local/state/nix/profiles/home-manager (wired into PATH in .zshenv.macos).
  programs.home-manager.enable = true;

  # Migrated from the bare repo (commit d30a806-era starship.toml).
  # Shell init stays manual in .zshrc; this only owns the config file.
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
