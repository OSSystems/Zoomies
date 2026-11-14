# Takes over the disk and bootloader. To add the desktop to an existing NixOS
# machine, use nixosModules.zoomies alone.
{ inputs, ... }:

{
  imports = [
    inputs.disko.nixosModules.disko
    ./disk-layout.nix
    ./boot.nix
    ./hardware.nix
  ];
}
