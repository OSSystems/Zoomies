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
in
{
  boot = {
    # Tests raise this to read kernel logs.
    consoleLogLevel = lib.mkDefault 3;
    initrd.verbose = false;
    kernelParams = [
      "quiet"
      "splash"
      "rd.udev.log_level=3"
      "udev.log_level=3"
      "systemd.show_status=auto"
      # GPU drivers load only after the initrd, so without the firmware's
      # framebuffer the screen stays black for most of the boot.
      "plymouth.use-simpledrm"
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
