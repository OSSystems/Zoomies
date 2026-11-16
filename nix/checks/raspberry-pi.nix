# QEMU cannot run the Pi firmware, so this boots the files the firmware
# would: config.txt's os_prefix picks the kernel, initrd, cmdline.txt and
# device tree out of the image's FAT partition. The Pi 3 is the only Pi
# QEMU emulates well enough; the Pi 4 and 5 boot the same files. Without
# KVM it is slow, hence the long timeouts.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  system = flake.nixosConfigurations.zoomies-pi.extendModules {
    modules = [
      {
        # Families' images have no serial console; the check needs one.
        boot.kernelParams = [ "console=ttyAMA0,115200n8" ];
        sdImage.compressImage = false;
        services.getty.autologinUser = "root";
        # Games and apps do not affect the boot path.
        zoomies = {
          games = lib.mkForce [ ];
          older.apps = lib.mkForce [ ];
        };
      }
    ];
  };
  inherit (system.config.system.build) sdImage;

  test =
    pkgs.writers.writePython3 "zoomies-raspberry-pi-test"
      {
        # The image's store path alone runs past 79 columns.
        flakeIgnore = [ "E501" ];
        libraries = [ pkgs.python3Packages.pexpect ];
      }
      ''
        import json
        import os
        import re
        import shutil
        import subprocess
        import sys

        import pexpect

        tmp = os.environ["TMPDIR"]
        img = f"{tmp}/sd.img"
        source = "${sdImage}/sd-image/${system.config.image.fileName}"


        def sh(*args):
            return subprocess.run(args, check=True, capture_output=True, text=True).stdout


        shutil.copyfile(source, img)
        os.chmod(img, 0o644)
        # QEMU wants a power-of-two SD card, and the spare room shows the root
        # partition growing on first boot.
        card = 8 * 1024**3
        assert os.path.getsize(img) < card, os.path.getsize(img)
        os.truncate(img, card)

        table = json.loads(sh("sfdisk", "--json", img))["partitiontable"]
        fat = f"{img}@@{table['partitions'][0]['start'] * 512}"


        def fat_file(path):
            out = f"{tmp}/{os.path.basename(path)}"
            sh("mcopy", "-n", "-i", fat, f"::{path}", out)
            return out


        config = open(fat_file("config.txt")).read()
        prefix = re.search(r"^os_prefix=(.*)$", config, re.M).group(1)
        # The firmware would apply this; it frees the PL011 UART for the console.
        dtb = f"{tmp}/test.dtb"
        sh(
            "fdtoverlay",
            "-i", fat_file(f"{prefix}bcm2710-rpi-3-b-plus.dtb"),
            "-o", dtb,
            fat_file(f"{prefix}overlays/disable-bt.dtbo"),
        )

        vm = pexpect.spawn(
            "qemu-system-aarch64",
            [
                "-machine", "raspi3b",
                "-kernel", fat_file(f"{prefix}kernel.img"),
                "-initrd", fat_file(f"{prefix}initrd"),
                "-dtb", dtb,
                "-append", open(fat_file(f"{prefix}cmdline.txt")).read().strip(),
                "-drive", f"file={img},if=sd,format=raw",
                "-display", "none",
                "-serial", "stdio",
                "-no-reboot",
            ],
            encoding="utf-8",
            codec_errors="replace",
            logfile=sys.stdout,
            timeout=3600,
        )
        # Bash sets the terminal title inside the prompt's brackets.
        vm.expect(r"root@zoomies-pi:~\]#")
        vm.timeout = 600


        def succeed(command):
            vm.sendline(f"{command}; echo __rc=$?")
            vm.expect(r"__rc=(\d+)\r*\n")
            rc = int(vm.match.group(1))
            output = vm.before
            assert rc == 0, f"{command!r} failed with {rc}"
            return output


        try:
            succeed("mountpoint /boot/firmware")
            # The image was smaller than the card it now fills.
            succeed('[ "$(lsblk -bno SIZE "$(findmnt -no SOURCE /)")" -gt $((6 * 1024**3)) ]')

            succeed("system=$(readlink -f /run/current-system)")
            succeed("dir=/boot/firmware/nixos/default")
            succeed("grep -qx os_prefix=nixos/default/ /boot/firmware/config.txt")
            succeed("grep -qx kernel=kernel.img /boot/firmware/config.txt")
            succeed("cmp $dir/kernel.img $system/kernel")
            succeed("cmp $dir/initrd $system/initrd")
            succeed('grep -q "init=$system/init" $dir/cmdline.txt')
            for board in [
                "bcm2710-rpi-3-b.dtb",
                "bcm2711-rpi-4-b.dtb",
                "bcm2712-rpi-5-b.dtb",
                "overlays/overlay_map.dtb",
                "overlays/vc4-kms-v3d.dtbo",
            ]:
                succeed(f"test -s $dir/{board}")
            for blob in ["bootcode.bin", "start.elf", "start4.elf"]:
                succeed(f"test -s /boot/firmware/{blob}")

            # An update rewrites the default system, even a damaged one, and
            # keeps a copy of each system generation for going back.
            succeed("truncate -s 0 $dir/kernel.img")
            succeed("/run/current-system/bin/switch-to-configuration boot")
            succeed("cmp $dir/kernel.img $system/kernel")
            succeed("cmp /boot/firmware/nixos/1-default/kernel.img $system/kernel")
            succeed("! ls -d /boot/firmware/nixos/*.tmp.* /boot/firmware/nixos/*.bkp.*")
        finally:
            vm.terminate(force=True)
      '';
in
pkgs.runCommand "zoomies-raspberry-pi"
  {
    nativeBuildInputs = [
      pkgs.dtc
      pkgs.mtools
      # qemu_test only emulates the host architecture.
      pkgs.qemu
      pkgs.util-linux
    ];
  }
  ''
    export MTOOLS_SKIP_CHECK=1
    ${test}
    touch $out
  ''
