# The installer points /dev/disk/zoomies-boot at the chosen disk and runs the
# prebuilt disko script, so this must not depend on the machine.
{
  disko.devices.disk.zoomies = {
    content = {
      partitions = {
        ESP = {
          content = {
            format = "vfat";
            mountOptions = [ "umask=0077" ];
            mountpoint = "/boot";
            type = "filesystem";
          };
          priority = 1;
          size = "1G";
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
