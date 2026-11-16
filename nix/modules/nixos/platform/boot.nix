# The removable EFI path needs no NVRAM entry, so the disk keeps booting
# after it moves to another machine. Disk names change between boots (a USB
# stick can take /dev/sda), so GRUB targets a link to the disk holding /boot,
# refreshed before every install. /boot is a directory on the root
# filesystem, so look up the filesystem holding it.
{ pkgs, ... }:

{
  boot.loader = {
    efi.efiSysMountPoint = "/boot/efi";
    grub = {
      # Ten older versions reach back far enough after a bad update and keep
      # the menu short. Kernels stay in the store on the root filesystem, so
      # /boot space sets no limit.
      configurationLimit = 10;
      device = "/dev/disk/zoomies-boot";
      efiInstallAsRemovable = true;
      efiSupport = true;
      extraPrepareConfig = ''
        disk=$(${pkgs.util-linux}/bin/lsblk -npo PKNAME "$(${pkgs.util-linux}/bin/findmnt -no SOURCE -T /boot)")
        ${pkgs.coreutils}/bin/ln -sfn "$disk" /dev/disk/zoomies-boot
      '';
    };
  };
}
