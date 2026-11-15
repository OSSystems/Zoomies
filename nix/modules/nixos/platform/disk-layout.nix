# The installer lets grown-ups pick or share the disk, so the system cannot
# name its partitions when it is built. The root filesystem carries a label
# the installer sets. The ESP may be another OS's, which we must not
# relabel, so the installer records its partition UUID instead and udev
# links whichever partition matches.
{ pkgs, ... }:

let
  isEsp = pkgs.writeShellScript "zoomies-is-esp" ''
    [ -n "$1" ] && [ "$1" = "$(${pkgs.coreutils}/bin/cat /var/lib/zoomies/esp-partuuid 2>/dev/null)" ]
  '';
in
{
  fileSystems = {
    "/" = {
      device = "/dev/disk/by-label/zoomies";
      fsType = "ext4";
    };
    "/boot/efi" = {
      device = "/dev/disk/zoomies-esp";
      fsType = "vfat";
      # Only updates need the ESP; a missing one must not stop the kids.
      options = [
        "nofail"
        "umask=0077"
        "x-systemd.device-timeout=10s"
      ];
    };
  };
  services.udev.extraRules = ''
    SUBSYSTEM=="block", ENV{DEVTYPE}=="partition", PROGRAM="${isEsp} $env{ID_PART_ENTRY_UUID}", SYMLINK+="disk/zoomies-esp"
  '';
}
