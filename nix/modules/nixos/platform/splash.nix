# Kids should see Zip, not kernel logs, between power on and the greeter.
# Holding Shift or pressing Esc during the second GRUB waits still shows the
# menu, so grown-ups can boot an older generation.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  plymouth = lib.getExe' config.boot.plymouth.package "plymouth";

  # The splash's last frame is Zip zooming off an empty sky, the same sky the
  # greeter draws, so the greeter seems to appear on the splash itself.
  # Deactivated, the splash lets the display manager take the screen while
  # its last frame stays up; it quits once the display manager has drawn.
  takeoff = pkgs.writeShellScript "zoomies-splash-takeoff" ''
    if ${plymouth} --ping; then
      ${plymouth} update --status=zoomies-takeoff
      ${lib.getExe' pkgs.coreutils "sleep"} 0.9
      ${plymouth} deactivate
    fi
  '';

  # NixOS writes DeviceTimeout=8 before any extra settings, and Plymouth
  # keeps the first value it reads, so the whole file is replaced.
  daemonConfig = pkgs.writeText "plymouthd.conf" ''
    [Daemon]
    ShowDelay=0
    DeviceTimeout=5
    Theme=${config.boot.plymouth.theme}
  '';
in
{
  boot = {
    # Tests raise this to read kernel logs.
    consoleLogLevel = lib.mkDefault 3;
    initrd = {
      # Intel and AMD drive most PCs, so their drivers start the splash in
      # the panel's own mode and nothing switches later in the boot. The
      # splash waits up to DeviceTimeout for them, then falls back to the
      # firmware's framebuffer, as on NVIDIA, whose firmware alone is
      # hundreds of megabytes and would slow every boot.
      availableKernelModules = [
        "amdgpu"
        "i915"
        "radeon"
        "xe"
      ];
      systemd.contents."/etc/plymouth/plymouthd.conf".source = lib.mkForce daemonConfig;
      verbose = false;
    };
    kernelParams = [
      "quiet"
      "splash"
      "rd.udev.log_level=3"
      "udev.log_level=3"
      "systemd.show_status=auto"
      # The splash belongs on the screen; the serial console keeps the logs.
      "plymouth.ignore-serial-consoles"
    ];
    loader = {
      grub = {
        # Hand Linux the firmware's graphics mode on BIOS too, so the splash
        # starts early there and no mode switch flashes the screen.
        gfxmodeBios = lib.mkDefault "auto";
        gfxpayloadBios = "keep";
        timeoutStyle = "hidden";
      };
      timeout = 1;
    };
    plymouth = {
      enable = true;
      theme = "zoomies";
      themePackages = [ (pkgs.callPackage ../../../packages/zoomies-splash/package.nix { }) ];
    };
  };
  environment.etc."plymouth/plymouthd.conf".source = lib.mkForce daemonConfig;
  systemd.services = {
    # Without --retain-splash the console flashes between the splash and
    # the greeter.
    plymouth-quit.serviceConfig.ExecStart = [
      ""
      "-${plymouth} quit --retain-splash"
    ];
    zoomies-splash-takeoff = {
      after = [ "systemd-user-sessions.service" ];
      before = [
        "display-manager.service"
        "plymouth-quit.service"
        "plymouth-quit-wait.service"
      ];
      description = "Zip zooms off the boot splash";
      serviceConfig = {
        ExecStart = takeoff;
        Type = "oneshot";
      };
      wantedBy = [ "multi-user.target" ];
    };
  };
}
