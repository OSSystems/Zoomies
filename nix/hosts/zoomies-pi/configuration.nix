# The reference host for the Raspberry Pi 3, 4 and 5, built as an SD image.
{
  flake,
  hostName,
  ...
}:

{
  imports = [
    flake.nixosModules.raspberry-pi
    flake.nixosModules.zoomies
    ../updates.nix
  ];
  networking.hostName = hostName;
  nixpkgs.hostPlatform = "aarch64-linux";
  system.stateVersion = "26.05";
  zoomies.enable = true;
}
