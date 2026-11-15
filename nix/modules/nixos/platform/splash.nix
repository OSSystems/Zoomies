# Kids should see a logo, not kernel logs, between power on and the greeter.
# Holding Shift or pressing Esc during the second GRUB waits still shows the
# menu, so grown-ups can boot an older generation.
{ lib, ... }:

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
    ];
    loader = {
      grub.timeoutStyle = "hidden";
      timeout = 1;
    };
    plymouth.enable = true;
  };
}
