{
  home.username = "raspberry";
  home.homeDirectory = "/home/raspberry";

  home.stateVersion = "26.05";

  # Headless server; CLI set only.
  hq.desktop = false;

  # The signing key is this Pi's ~/.ssh/id_ed25519 ("raspberry@rpi-5"),
  # which existed before HM ever ran here; verified before enabling.
  hq.gitSign = true;
  hq.gitSignKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJTmz/U8LsPRRqM22xTuSsE0aQw0H8zcKlHNKb6lPEdZ raspberry@rpi-5";
}
