{
  flake,
  pkgs,
  system,
  ...
}:

pkgs.mkShellNoCC {
  packages = [
    flake.formatter.${system}
    pkgs.nixos-rebuild
  ];
}
