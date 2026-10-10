{ config, lib, ... }:

{
  options.hq = {
    # GUI/desktop-bound tools. Headless hosts (cluster login nodes, a
    # headless Pi) keep this off and get the CLI-only subset.
    desktop = lib.mkEnableOption "desktop/GUI tools (alacritty, nerd fonts)";

    # Commit signing requires the private key named by programs.git.signing
    # to exist on the machine; without it every `git commit` fails. Enable
    # per host once the key is provisioned there.
    gitSign = lib.mkEnableOption "git commit signing";

    # Public part of the signing key; defaults to the mac's hugo@Hcis key,
    # override on hosts provisioned with their own key (see hosts/*.nix).
    gitSignKey = lib.mkOption {
      type = lib.types.str;
      default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIISAYNU+ArG43Zp4mHI5pm7Wfa4VQ4cV/dgNexczIfpU hugo@Hcis";
    };
  };
}
