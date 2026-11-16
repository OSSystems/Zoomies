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
  # Nobody reads manuals on a family's Zoomies, and they would fill the
  # image. man-db follows man.enable, not enable.
  documentation = {
    enable = false;
    man.enable = false;
  };
  # The languages Zoomies' screens are translated to; the installer offers
  # only these.
  i18n.supportedLocales = [
    "en_US.UTF-8/UTF-8"
    "es_ES.UTF-8/UTF-8"
    "pt_BR.UTF-8/UTF-8"
  ];
  networking.networkmanager.enable = true;
  # Updates come from the Zoomies flake, which brings its own nixpkgs; one
  # pinned for `nix run nixpkgs#…` and <nixpkgs> only adds a 200 MiB source.
  nixpkgs.flake = {
    setFlakeRegistry = false;
    setNixPath = false;
  };
  services.fstrim.enable = true;
  # Reads the options' documentation and brings man-db back.
  system.tools.nixos-option.enable = false;
  zramSwap = {
    algorithm = "zstd";
    enable = true;
    memoryPercent = 60;
  };
}
