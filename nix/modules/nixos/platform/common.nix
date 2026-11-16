# Tuning shared by every Zoomies machine, PC or Raspberry Pi.
{
  boot.kernel.sysctl = {
    # zram is much faster than reclaiming page cache from a slow disk, so
    # prefer swapping to it; readahead only helps on spinning swap.
    "vm.page-cluster" = 0;
    "vm.swappiness" = 180;
    "vm.watermark_boost_factor" = 0;
    "vm.watermark_scale_factor" = 125;
  };
  hardware = {
    # Only redistributable firmware, so the images can be shared freely.
    enableRedistributableFirmware = true;
    graphics.enable = true;
  };
  # The languages Zoomies' screens are translated to; the installer offers
  # only these.
  i18n.supportedLocales = [
    "en_US.UTF-8/UTF-8"
    "es_ES.UTF-8/UTF-8"
    "pt_BR.UTF-8/UTF-8"
  ];
  networking.networkmanager.enable = true;
  services.fstrim.enable = true;
  zramSwap = {
    algorithm = "zstd";
    enable = true;
    memoryPercent = 60;
  };
}
