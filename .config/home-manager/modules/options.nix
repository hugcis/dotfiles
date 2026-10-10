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
  };
}
