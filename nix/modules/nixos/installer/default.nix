{
  config,
  lib,
  modulesPath,
  pkgs,
  ...
}:

let
  cfg = config.zoomies.installer;
  target = cfg.system.config.system.build;

  install = pkgs.writeShellApplication {
    name = "zoomies-install";
    runtimeEnv = {
      CLOSURE_INFO = pkgs.closureInfo { rootPaths = [ target.toplevel ]; };
      DISKO_SCRIPT = target.diskoScript;
      TOPLEVEL = target.toplevel;
    };
    runtimeInputs = [
      config.nix.package
      config.system.build.nixos-install
      pkgs.coreutils
      pkgs.gawk
      pkgs.gnugrep
      pkgs.gnused
      pkgs.jq
      pkgs.ncurses
      pkgs.parted
      pkgs.systemd
      pkgs.util-linux
    ];
    text = builtins.readFile ./install.sh;
  };
in
{
  config = {
    boot = {
      kernelParams = [
        "console=ttyS0,115200n8"
        "console=tty0"
      ];
      # Zoomies installs to ext4; ZFS only slows the ISO build down.
      supportedFilesystems.zfs = lib.mkForce false;
    };
    documentation = {
      enable = false;
      nixos.enable = false;
    };
    environment = {
      # A login shell, not a service, so whatever happens the user is left
      # at a prompt on tty1 instead of a blank screen.
      loginShellInit = ''
        if [ "$(tty)" = /dev/tty1 ]; then
          sudo ${lib.getExe install}
        fi
      '';
      systemPackages = [ install ];
    };
    image.baseName = lib.mkForce "zoomies-installer";
    isoImage = {
      appendToMenuLabel = " Installer";
      makeEfiBootable = true;
      makeUsbBootable = true;
      squashfsCompression = "zstd -Xcompression-level 6";
      volumeID = "ZOOMIES";
    };
    networking.hostName = "zoomies-installer";
    nixpkgs.hostPlatform = "x86_64-linux";
    services.getty.helpLine = lib.mkForce ''

      Zoomies installer. To start it again, run: sudo zoomies-install
    '';
    system.stateVersion = "26.05";
  };
  imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix" ];
  options.zoomies.installer.system = lib.mkOption {
    description = ''
      The NixOS system the installer copies to disk, as returned by
      nixosSystem. It must import nixosModules.platform, which provides the
      disk layout and the bootloader.
    '';
    type = lib.types.raw;
  };
}
