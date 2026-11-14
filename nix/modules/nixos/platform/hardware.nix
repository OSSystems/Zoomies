# One image for every PC, so no per-machine hardware scan.
{ modulesPath, ... }:

{
  boot = {
    kernel.sysctl = {
      # zram is much faster than reclaiming page cache from a slow disk, so
      # prefer swapping to it; readahead only helps on spinning swap.
      "vm.page-cluster" = 0;
      "vm.swappiness" = 180;
      "vm.watermark_boost_factor" = 0;
      "vm.watermark_scale_factor" = 125;
    };
    # The last console= becomes /dev/console, so boot messages stay on the
    # screen; the serial console helps debug machines and VMs.
    kernelParams = [
      "console=ttyS0,115200n8"
      "console=tty0"
    ];
  };
  hardware = {
    # Only redistributable firmware, so the images can be shared freely.
    enableRedistributableFirmware = true;
    graphics.enable = true;
  };
  imports = [ "${modulesPath}/profiles/all-hardware.nix" ];
  networking.networkmanager.enable = true;
  services.fstrim.enable = true;
  zramSwap = {
    algorithm = "zstd";
    enable = true;
    memoryPercent = 60;
  };
}
