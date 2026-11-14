{ flake, hostName, ... }:

{
  boot.loader.grub.device = "nodev";
  fileSystems."/" = {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
  };
  imports = [ flake.nixosModules.zoomies ];
  networking.hostName = hostName;
  nixpkgs.hostPlatform = "x86_64-linux";
  system.stateVersion = "26.05";
  zoomies.enable = true;
}
