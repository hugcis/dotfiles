{
  home.username = "hugo";
  home.homeDirectory = "/home/hugo";

  # TODO on the cluster login node: verify username/homedir. If $HOME is on
  # NFS shared with compute nodes, remember /nix stays node-local — this
  # profile is login-node only unless nix is installed with a shared store.
  home.stateVersion = "26.05";

  # Cluster login nodes are headless; CLI set only.
  hq.desktop = false;

  # TODO: provision the SSH signing key on the cluster, then enable.
  hq.gitSign = false;
}
