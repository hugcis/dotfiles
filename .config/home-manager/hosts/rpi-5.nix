{
  home.username = "raspberry";
  home.homeDirectory = "/home/raspberry";

  home.stateVersion = "26.05";

  # Headless server; CLI set only.
  hq.desktop = false;

  # TODO: provision the SSH signing key on the Pi, then enable.
  hq.gitSign = false;
}
