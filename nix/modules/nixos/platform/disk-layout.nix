# The installer points /dev/disk/zoomies-boot at the chosen disk and runs the
# prebuilt disko script, so this must not depend on the machine.
#
# /boot stays on the root filesystem, which GRUB reads under either
# firmware: the ESP then holds only GRUB, so the same system also fits next
# to Windows, whose ESP is often 100 MiB.
{
  disko.devices.disk.zoomies = {
    content = {
      partitions = {
        ESP = {
          content = {
            format = "vfat";
            mountOptions = [ "umask=0077" ];
            mountpoint = "/boot/efi";
            type = "filesystem";
          };
          priority = 1;
          # FAT32 needs 256 MiB on disks with 4 KiB sectors.
          size = "512M";
          type = "EF00";
        };
        bios = {
          priority = 0;
          size = "1M";
          type = "EF02";
        };
        root = {
          content = {
            format = "ext4";
            mountpoint = "/";
            type = "filesystem";
          };
          size = "100%";
        };
      };
      type = "gpt";
    };
    device = "/dev/disk/zoomies-boot";
    type = "disk";
  };
}
