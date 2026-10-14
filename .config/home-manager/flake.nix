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
      #   home-manager switch --flake ~/.config/home-manager#<user>@<name>
      # Bootstrap a new machine straight from GitHub (no clone needed):
      #   home-manager switch --flake "github:hugcis/dotfiles?dir=.config/home-manager#<user>@<name>"
      hosts = {
        mac = {
          user = "hugo";
          system = "aarch64-darwin";
          channel = "unstable";
        };
        # Mistral work laptop.
        mistral-mac = {
          user = "hugo.cisneros";
          system = "aarch64-darwin";
          channel = "unstable";
        };
        # x86_64 Arch desktop.
        archcis = {
          user = "hugcis";
          system = "x86_64-linux";
          channel = "unstable";
        };
        # Raspberry Pi 5, aarch64 Debian (headless).
        rpi-5 = {
          user = "raspberry";
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

      # Build the home configuration of a registry host. Exported so a
      # private flake can layer extra modules onto a host without this
      # repo knowing about them.
      mkHome =
        { name
        , extraModules ? [ ]
        , extraSpecialArgs ? { }
        }:
        let
          host = hosts.${name};
          channel = channels.${host.channel};
        in
        channel.home-manager.lib.homeManagerConfiguration {
          pkgs = import channel.nixpkgs { system = host.system; };
          modules = [ ./home.nix ./hosts/${name}.nix ] ++ extraModules;
          inherit extraSpecialArgs;
        };
    in
    {
      lib = { inherit mkHome; };

      homeConfigurations = lib.mapAttrs'
        (name: host: lib.nameValuePair "${host.user}@${name}" (mkHome { inherit name; }))
        hosts;
    };
}
