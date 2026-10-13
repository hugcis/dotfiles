{ pkgs, ... }:

{
  home.username = "hugo.cisneros";
  home.homeDirectory = "/Users/hugo.cisneros";

  # The release this machine first switched with.
  home.stateVersion = "26.05";

  hq.desktop = true;

  # Signing goes through the Secretive agent; the private key never leaves
  # the Secure Enclave.
  hq.gitSign = true;
  hq.gitSignKey = "key::ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBOGtI6n2/5am65Tcpbv0NEwzuwdZc/zryby9e6WoeczbjKzfeOdJ6D8QDSAO6XXMEiNaKaJNGGQd2Qq/9RaY0WU= ssh-macbook-gh-signing@secretive.MacBook-Air-HugoCisneros.local";

  # Cluster tooling, only needed for Mistral work.
  home.packages = with pkgs; [
    k9s
    kubectl
    mosh
  ];
}
