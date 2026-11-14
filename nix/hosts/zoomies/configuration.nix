{
  flake,
  hostName,
  ...
}:

{
  imports = [
    flake.nixosModules.platform
    flake.nixosModules.zoomies
  ];
  networking.hostName = hostName;
  nixpkgs.hostPlatform = "x86_64-linux";
  system.stateVersion = "26.05";
  virtualisation.vmVariant.imports = [ ./vm.nix ];
  zoomies.enable = true;
}
