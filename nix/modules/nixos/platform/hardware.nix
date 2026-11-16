# One image for every PC, so no per-machine hardware scan.
{ modulesPath, ... }:

{
  imports = [
    "${modulesPath}/profiles/all-hardware.nix"
    ./common.nix
    ./console.nix
  ];
}
