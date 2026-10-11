{ config, pkgs, ... }:

{
  # Shared, host-independent configuration. Host-specific settings live in
  # hosts/<host>.nix (selected by the registry in flake.nix); OS-specific
  # settings use lib.mkIf on the platform inside the module that needs them.
  # Switch with:
  #   hm                                        (auto-detects host)
  #   home-manager switch --flake ~/.config/home-manager#hugo@<host>
  #
  # Migration pattern for the raw dotfiles still tracked at $HOME, one file
  # at a time:
  #   1. Copy the raw file to configs/ and add a home.file entry in the
  #      owning module (see modules/shell.nix).
  #   2. GIT_DIR=~/.cfg git rm --cached .zshrc   (stop tracking in the bare repo)
  #   3. Delete the raw file, then `hm` links the HM-generated one.
  # Home-manager fails loudly on a collision instead of overwriting, so steps
  # taken out of order are recoverable. NOTE: step 3 must be repeated on
  # every machine — pulling main only removes the index entries; each host
  # deletes its live files right before its own first `hm` switch.
  #
  # The bare repo (~/.cfg) excludes everything by default (~/.cfg/info/exclude),
  # so new files under this tree need an explicit `git add -f` to be tracked.

  imports = [
    ./modules/options.nix
    ./modules/packages.nix
    ./modules/editors.nix
    ./modules/git.nix
    ./modules/terminal.nix
    ./modules/starship.nix
    ./modules/shell.nix
    ./modules/claude.nix
  ];

  # Set per host in hosts/*.nix (the release each machine started with).
  # home.stateVersion

  # Installs the home-manager CLI into the profile at
  # ~/.local/state/nix/profiles/home-manager (wired into PATH in .zprofile).
  programs.home-manager.enable = true;
}
