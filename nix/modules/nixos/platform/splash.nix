# Kids should see Zip, not kernel logs, between power on and the greeter.
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
  #
  # Once deactivated, any text written to a console wakes the kernel's own,
  # which replaces that last frame with black until the greeter draws.
  # Setting the consoles up writes to them, and a busy machine may still be
  # probing the devices that set them up, so Zip waits on his cloud until
  # all of that is done.
  takeoff = pkgs.writeShellScript "zoomies-splash-takeoff" ''
    ${lib.getExe' config.systemd.package "udevadm"} settle --timeout=10 || true
    settled=0
    for _ in $(${lib.getExe' pkgs.coreutils "seq"} 200); do
      if ${lib.getExe' config.systemd.package "systemctl"} list-jobs --no-legend |
        ${lib.getExe pkgs.gnugrep} -q systemd-vconsole-setup; then
        settled=0
      elif [ "$((settled += 1))" -ge 3 ]; then
        break
      fi
      ${lib.getExe' pkgs.coreutils "sleep"} 0.05
    done
    if ${plymouth} --ping; then
      ${plymouth} update --status=zoomies-takeoff
      ${lib.getExe' pkgs.coreutils "sleep"} 1.3
      ${plymouth} deactivate
    fi
  '';

  # A compositor may not give the screen up itself: only the process that
  # opened it, logind, or root may. This takes a copy of the compositor's
  # handle on the screen and gives it up from root, while the compositor
  # still shows its last frame, so the splash can take the screen over in
  # place.
  release = pkgs.writers.writePython3 "zoomies-splash-release" { } ''
    import ctypes
    import fcntl
    import os
    import sys

    PIDFD_GETFD = 438
    DRM_IOCTL_DROP_MASTER = 0x641F

    libc = ctypes.CDLL(None, use_errno=True)
    pid = int(sys.argv[1])
    pidfd = os.pidfd_open(pid)
    for name in os.listdir(f"/proc/{pid}/fd"):
        try:
            target = os.readlink(f"/proc/{pid}/fd/{name}")
        except OSError:
            continue
        if not target.startswith("/dev/dri/card"):
            continue
        fd = libc.syscall(PIDFD_GETFD, pidfd, int(name), 0)
        if fd < 0:
            continue
        try:
            fcntl.ioctl(fd, DRM_IOCTL_DROP_MASTER)
            sys.exit(0)
        except OSError:
            pass
        finally:
            os.close(fd)
    sys.exit(1)
  '';

  # Plymouth's own units load the splash only once the display manager has
  # stopped, so the screen stays black for the second or more that takes.
  # These load it as the shutdown starts, behind the session's last frame.
  # When the shell asked for the power off, the zoomies module's cage holds
  # that frame and the screen is taken from under it; any other session
  # simply exits first. A machine with nothing left to stop would then turn
  # off before Zip lands, so the hold keeps the splash up while the rest of
  # the shutdown carries on.
  stopping =
    {
      action,
      hold,
      mode,
    }:
    {
      before = [ "systemd-${action}.service" ];
      description = "Zip lands as the computer stops";
      path = [
        pkgs.coreutils
        pkgs.procps
      ];
      script = ''
        dir=/run/zoomies-splash
        ${lib.getExe' config.boot.plymouth.package "plymouthd"} --mode=${mode} --attach-to-session
        ${plymouth} show-splash
        touch $dir/ready
        if [ -e $dir/requested ]; then
          for _ in $(seq 300); do
            if [ -s $dir/holding ]; then
              ${release} "$(cat $dir/holding)" || true
              break
            fi
            sleep 0.01
          done
        else
          # NixOS wraps cage, so it runs as .cage-wrapped.
          for _ in $(seq 300); do
            pgrep -x '\.?cage(-wrapped)?|Xorg|X' >/dev/null || break
            sleep 0.01
          done
        fi
        # Plymouth takes the screen only when it starts or reactivates.
        ${plymouth} deactivate
        ${plymouth} reactivate
        ${plymouth} update --status=zoomies-land
        touch $dir/shown
        sleep ${hold}
        # Zip dims to black, so the firmware's black does not cut him off.
        echo "zoomies-splash: dimming to black"
        ${plymouth} update --status=zoomies-blackout
        sleep 0.5
      '';
      serviceConfig = {
        RemainAfterExit = true;
        TimeoutStartSec = 30;
        Type = "oneshot";
      };
      unitConfig = {
        ConditionKernelCommandLine = "!plymouth.enable=0";
        DefaultDependencies = false;
      };
      wantedBy = [ "${action}.target" ];
    };

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
      "rd.udev.log_level=3"
      "udev.log_level=3"
      "systemd.show_status=auto"
      # The splash belongs on the screen; the serial console keeps the logs.
      "plymouth.ignore-serial-consoles"
    ];
    loader.grub = {
      # Hand Linux the firmware's graphics mode on BIOS too, so the splash
      # starts early there and no mode switch flashes the screen.
      gfxmodeBios = lib.mkDefault "auto";
      gfxpayloadBios = "keep";
    };
    plymouth = {
      enable = true;
      theme = "zoomies";
      themePackages = [ (pkgs.callPackage ../../../packages/zoomies-splash/package.nix { }) ];
    };
  };
  environment.etc."plymouth/plymouthd.conf".source = lib.mkForce daemonConfig;
  systemd.services = {
    plymouth-poweroff.enable = false;
    # Without --retain-splash the console flashes between the splash and
    # the greeter.
    plymouth-quit.serviceConfig.ExecStart = [
      ""
      "-${plymouth} quit --retain-splash"
    ];
    plymouth-reboot.enable = false;
    # Zip lands, waves and, at power off, falls asleep.
    zoomies-splash-poweroff = stopping {
      action = "poweroff";
      hold = "3";
      mode = "shutdown";
    };
    zoomies-splash-reboot = stopping {
      action = "reboot";
      hold = "1.6";
      mode = "reboot";
    };
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
  # Sessions mark here that they asked for the power off and hand the screen
  # over; anyone may, as at worst the splash takes the screen a moment late.
  systemd.tmpfiles.rules = [ "d /run/zoomies-splash 1777 root root -" ];
}
