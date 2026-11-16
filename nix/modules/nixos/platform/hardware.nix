# One image for every PC, so no per-machine hardware scan.
{ modulesPath, ... }:

{
  # Only redistributable firmware, so the images can be shared freely.
  hardware.enableRedistributableFirmware = true;
  imports = [
    "${modulesPath}/profiles/all-hardware.nix"
    ./common.nix
    ./console.nix
  ];
}
