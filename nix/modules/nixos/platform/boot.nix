# The removable EFI path needs no NVRAM entry, so the disk keeps booting
# after it moves to another machine. Disk names change between boots (a USB
# stick can take /dev/sda), so GRUB targets a link to the disk holding /boot,
# refreshed before every install.
{ pkgs, ... }:

{
  boot.loader.grub = {
    # Each generation copies its kernel and initrd, about 95 MB with the GPU
    # drivers the splash needs, into the 1 GB /boot.
    configurationLimit = 5;
    efiInstallAsRemovable = true;
    efiSupport = true;
    extraPrepareConfig = ''
      disk=$(${pkgs.util-linux}/bin/lsblk -npo PKNAME "$(${pkgs.util-linux}/bin/findmnt -no SOURCE /boot)")
      ${pkgs.coreutils}/bin/ln -sfn "$disk" /dev/disk/zoomies-boot
    '';
  };
}
