{ config, lib, pkgs, ... }:

let
  # Nix Python with the renderer's one third-party dependency (PyYAML), so
  # rendering does not depend on whichever python3 comes first on PATH.
  python = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
  render = pkgs.writeShellApplication {
    name = "agent-stack-render";
    runtimeInputs = [ python ];
    text = builtins.readFile ../scripts/agent-stack-render;
  };
in
{
  # agent-stack owns agent content (skills, roster, AGENTS.md) on every
  # machine, including clusters without Nix. On Nix machines, `hm` also
  # re-renders it so one command applies both.
  home.packages = [ render ];
  home.activation.agentStackRender = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
    run ${lib.getExe render} ${lib.escapeShellArg "${config.xdg.configHome}/agent-stack"}
  '';
}
