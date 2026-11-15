# Takes over the disk and bootloader. To add the desktop to an existing NixOS
# machine, use nixosModules.zoomies alone.
_:

{
  imports = [
    ./disk-layout.nix
    ./boot.nix
    ./boot-menu.nix
    ./hardware.nix
    ./splash.nix
  ];
}
