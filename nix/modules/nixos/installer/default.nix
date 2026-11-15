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
  closure = pkgs.closureInfo { rootPaths = [ target.toplevel ]; };

  installTarget = pkgs.writeShellApplication {
    name = "zoomies-install-target";
    runtimeEnv = {
      CLOSURE_INFO = closure;
      TOPLEVEL = target.toplevel;
    };
    runtimeInputs = [
      config.nix.package
      config.system.build.nixos-install
      pkgs.coreutils
      pkgs.gawk
      pkgs.e2fsprogs
      pkgs.parted
      pkgs.util-linux
    ];
    text = builtins.readFile ./install-target.sh;
  };

  calamaresConfig =
    pkgs.runCommand "zoomies-calamares-config"
      {
        nativeBuildInputs = [ pkgs.gawk ];
      }
      ''
        cp -r ${./calamares} $out
        chmod -R u+w $out
        mkdir -p $out/modules-dir
        mv $out/zoomies $out/modules-dir/zoomies
        cp ${../../../../assets/mascot/zip.png} $out/branding/zoomies/zip.png
        # -c points Calamares at this folder for its own QML too.
        ln -s ${pkgs.calamares}/share/calamares/qml $out/qml

        # ext4 rounds every store file up to a whole block; the rest is the
        # ESP and room for later generations.
        storage=$(awk '{ printf "%.1f", $1 * 1.25 / 2^30 + 3 }' ${closure}/total-nar-size)

        substituteInPlace $out/settings.conf --replace-fail @modules@ $out/modules-dir
        substituteInPlace $out/modules/welcome.conf --replace-fail @requiredStorage@ "$storage"
        substituteInPlace $out/modules/locale.conf --replace-fail @glibcLocales@ ${pkgs.glibcLocales}
        substituteInPlace $out/branding/zoomies/branding.desc \
          --replace-fail @version@ ${cfg.system.config.system.nixos.release}
        substituteInPlace $out/modules-dir/zoomies/main.py \
          --replace-fail 'os.environ["ZOOMIES_INSTALL_TARGET"]' '"${lib.getExe installTarget}"'
      '';

  # Calamares partitions and copies, so it needs root; cage runs it for the
  # live user, whose sudo needs no password.
  launcher = pkgs.writeShellScript "zoomies-installer" ''
    exec /run/wrappers/bin/sudo \
      --preserve-env=WAYLAND_DISPLAY,XDG_RUNTIME_DIR,QT_QPA_PLATFORM,QT_PLUGIN_PATH \
      ${lib.getExe pkgs.calamares} -c ${calamaresConfig}
  '';
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
    environment.systemPackages = [ installTarget ];
    fonts = {
      fontconfig.enable = true;
      packages = [ pkgs.andika ];
    };
    hardware.graphics.enable = true;
    image.baseName = lib.mkForce "zoomies-installer";
    isoImage = {
      appendToMenuLabel = " Installer";
      makeEfiBootable = true;
      makeUsbBootable = true;
      squashfsCompression = "zstd -Xcompression-level 6";
      volumeID = "ZOOMIES";
    };
    networking = {
      hostName = "zoomies-installer";
      # The time zone guess needs the network; Wi-Fi is set up from a
      # terminal if needed.
      networkmanager.enable = true;
      wireless.enable = lib.mkForce false;
    };
    nixpkgs.hostPlatform = "x86_64-linux";
    # KPMcore, which Calamares partitions with, needs its D-Bus helper.
    programs.partition-manager.enable = true;
    services = {
      cage = {
        enable = true;
        environment = {
          QT_PLUGIN_PATH = "${pkgs.kdePackages.qtwayland}/${pkgs.kdePackages.qtbase.qtPluginPrefix}";
          QT_QPA_PLATFORM = "wayland";
        };
        program = launcher;
        user = "nixos";
      };
      getty.helpLine = lib.mkForce ''

        Zoomies installer. The graphical installer runs on the first screen.
      '';
    };
    system.stateVersion = "26.05";
  };
  imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix" ];
  options.zoomies.installer.system = lib.mkOption {
    description = ''
      The NixOS system the installer copies to disk, as returned by
      nixosSystem. It must import nixosModules.platform, which provides the
      filesystems and the bootloader.
    '';
    type = lib.types.raw;
  };
}
