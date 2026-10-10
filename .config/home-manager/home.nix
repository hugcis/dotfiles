{ config, pkgs, ... }:

{
  home.username = "hugo";
  home.homeDirectory = "/Users/hugo";

  # Do not change after first switch; only set to the release you started with.
  home.stateVersion = "25.05";

  # Installs the home-manager CLI into the profile at
  # ~/.local/state/nix/profiles/home-manager (wired into PATH in .zshenv.macos).
  programs.home-manager.enable = true;

  # Migration pattern, one program at a time:
  #   1. Replace the raw config file here (e.g. programs.zellij.enable + settings).
  #   2. config rm --cached ~/.config/zellij/config.kdl   (stop tracking in the bare repo)
  #   3. Delete the raw file, then `home-manager switch` links the HM-generated one.
  # Home-manager fails loudly on a collision instead of overwriting, so steps
  # taken out of order are recoverable.
}
