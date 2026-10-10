{
  description = "Hugo's home-manager configuration";

  inputs = {
    # Rolling channel for the daily drivers (mac).
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    # Stable channel for the machines that should not churn (pi, remote
    # clusters). Keep home-manager pinned to the matching release so HM
    # module changes track the nixpkgs release they were tested against.
    nixpkgs-stable.url = "github:NixOS/nixpkgs/nixos-26.05";

    home-manager = {
      url = "github:nix-community/home-manager/master";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    home-manager-stable = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs-stable";
    };
  };

  outputs =
    { nixpkgs
    , nixpkgs-stable
    , home-manager
    , home-manager-stable
    , ...
    }:
    let
      lib = nixpkgs.lib;

      # Host registry, keyed by hostname. The user@host homeConfigurations
      # name (the flake selector) is composed from each entry's user field.
      # To add a machine: create hosts/<name>.nix, then add an entry here.
      # Switch with:
      #   hm                                      (auto-detects, see scripts/hm)
      #   home-manager switch --flake ~/.config/home-manager#hugo@<name>
      # Bootstrap a new machine straight from GitHub (no clone needed):
      #   home-manager switch --flake "github:hugcis/dotfiles?dir=.config/home-manager#hugo@<name>"
      hosts = {
        mac = {
          user = "hugo";
          system = "aarch64-darwin";
          channel = "unstable";
        };
        # The Raspberry Pi is the only Arch box (Arch Linux ARM).
        pi = {
          user = "hugo";
          system = "aarch64-linux";
          channel = "stable";
        };
        # Remote cluster login nodes (RHEL/Ubuntu-like).
        remote-mistral = {
          user = "hugo";
          system = "x86_64-linux";
          channel = "stable";
        };
      };

      channels = {
        unstable = {
          nixpkgs = nixpkgs;
          home-manager = home-manager;
        };
        stable = {
          nixpkgs = nixpkgs-stable;
          home-manager = home-manager-stable;
        };
      };
    in
    {
      homeConfigurations = lib.mapAttrs'
        (name: host:
          let channel = channels.${host.channel}; in
          lib.nameValuePair "${host.user}@${name}"
            (channel.home-manager.lib.homeManagerConfiguration {
              pkgs = import channel.nixpkgs { system = host.system; };
              modules = [ ./home.nix ./hosts/${name}.nix ];
            }))
        hosts;
    };
}
