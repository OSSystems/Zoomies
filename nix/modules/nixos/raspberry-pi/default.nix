# Takes over a Raspberry Pi 3, 4 or 5 booting from an SD card or USB stick,
# like nixosModules.platform does for PCs. One image serves all three: they
# share the Pi 4 kernel, which Raspberry Pi OS also ships for the Pi 3 and 5,
# and the Pi's own firmware loads it with the device tree for the board.
{ inputs, ... }:

{
  config,
  lib,
  modulesPath,
  ...
}:

{
  _module.args.nixos-raspberrypi = inputs.nixos-raspberrypi;
  boot = {
    # The board modules' 7 floods the kids' screen during boot.
    consoleLogLevel = 4;
    # U-Boot would load a Pi 4 device tree on every board. This loads the
    # kernel straight from the firmware, under [all] so every board takes
    # it, and keeps earlier systems on the card for going back.
    loader.raspberry-pi.bootloader = "kernel";
  };
  # sd-image leaves it unmounted, but every update writes to it.
  fileSystems."/boot/firmware".options = lib.mkForce [
    "nofail"
    "umask=0077"
  ];
  # sd-image turns this on, but it lists PC drivers the vendor kernel
  # lacks.
  hardware.enableAllHardware = lib.mkForce false;
  # On the Pi 3 the serial console pins the core clock at 250 MHz, slowing
  # the GPU, and families have no use for it. The firmware leaves the UART
  # off, so the board modules' console=serial0 finds no device.
  hardware.raspberry-pi.config.all.options.enable_uart.value = lib.mkForce 0;
  image.baseName = "zoomies-raspberry-pi";
  imports = with inputs.nixos-raspberrypi.nixosModules; [
    "${modulesPath}/installer/sd-card/sd-image.nix"
    ../platform/common.nix
    inputs.nixos-raspberrypi.lib.inject-overlays
    raspberry-pi-4.base
    raspberry-pi-4.bluetooth
    raspberry-pi-4.display-vc4
    # Updates on the Pi itself fetch the kernel instead of building it.
    trusted-nix-caches
  ];
  sdImage = {
    # Room for the kernels and initrds of the systems kept for going back.
    firmwareSize = 1024;
    populateFirmwareCommands = ''
      ${config.boot.loader.raspberry-pi.firmwarePopulateCmd} -c ${config.system.build.toplevel} -f ./firmware
    '';
    populateRootCommands = "mkdir -p ./files/boot/firmware";
  };
}
