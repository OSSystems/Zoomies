# Each install boots under both firmwares, not just the one that installed
# it. Games are dropped for speed; they do not affect the boot path.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  instrumentation =
    { modulesPath, ... }:
    {
      imports = [ "${modulesPath}/testing/test-instrumentation.nix" ];
    };

  system = flake.nixosConfigurations.zoomies.extendModules {
    modules = [
      instrumentation
      {
        zoomies = {
          games = lib.mkForce [ ];
          older.apps = lib.mkForce [ ];
        };
      }
    ];
  };

  iso = flake.lib.mkInstallerIso {
    inherit system;
    modules = [ instrumentation ];
  };

  qemu = "${pkgs.qemu_test}/bin/qemu-system-x86_64 -machine q35,accel=kvm -cpu max -m 2048 -smp 2";
  ovmf = lib.concatStringsSep " " [
    "-drive if=pflash,format=raw,unit=0,readonly=on,file=${pkgs.OVMF.firmware}"
    "-drive if=pflash,format=raw,unit=1,readonly=on,file=${pkgs.OVMF.variables}"
  ];
in
pkgs.testers.runNixOSTest {
  # Reads the installer's pages and the boot menu off the screen.
  enableOCR = true;
  # Three times a normal run: a stuck step fails the check instead of
  # holding an idle VM for an hour or two.
  globalTimeout = 1800;
  # qemu-system-x86_64 under KVM.
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-installer";
  nodes = { };
  testScript = ''
    import os
    import subprocess

    iso = "${iso}/iso/${iso.name}"
    tmp = os.environ.get("TMPDIR", "/tmp")


    def qemu_img(*args):
        subprocess.run(["${pkgs.qemu_test}/bin/qemu-img", *args], check=True)


    def start_command(firmware, disk, medium=None):
        flags = ["${qemu}"]
        if firmware == "uefi":
            flags.append("${ovmf}")
        flags.append(f"-drive id=disk,if=none,format=qcow2,file={disk}")
        flags.append("-device ide-hd,drive=disk,bus=ide.0,bootindex=2")
        if medium == "usb":
            flags.append(f"-drive id=stick,if=none,format=raw,readonly=on,file={iso}")
            flags.append("-device qemu-xhci,id=xhci")
            flags.append("-device usb-storage,bus=xhci.0,drive=stick,bootindex=1")
        elif medium == "cd":
            flags.append(f"-drive id=cd,if=none,media=cdrom,readonly=on,file={iso}")
            flags.append("-device ide-cd,drive=cd,bus=ide.2,bootindex=1")
        return " ".join(flags)


    # The driver does not stop machines from create_machine when a test fails,
    # so a failure would otherwise hang until the global timeout.
    vms = []


    def start(command, name):
        machine = create_machine(command, name=name)
        vms.append(machine)
        machine.start()
        return machine


    def install(name, firmware, medium):
        disk = f"{tmp}/{name}.qcow2"
        qemu_img("create", "-f", "qcow2", disk, "32G")
        machine = start(start_command(firmware, disk, medium), f"{name}_installer")
        # Calamares is driven with its keyboard shortcuts, reading each page
        # off the screen before moving on. Pages show within seconds; the
        # driver's 15-minute default would stare at a page that never comes.
        machine.wait_for_text("Welcome to the Zoomies installer", timeout=180)
        # Next stays disabled until the requirement checks finish.
        machine.sleep(5)
        machine.screenshot(f"{name}-welcome")
        machine.send_key("alt-n")
        machine.wait_for_text("Region", timeout=60)
        machine.send_key("alt-n")
        machine.wait_for_text("Keyboard model", timeout=60)
        machine.send_key("alt-n")
        machine.wait_for_text("Erase disk", timeout=60)
        machine.screenshot(f"{name}-partitions")
        machine.send_key("alt-n")
        machine.wait_for_text("overview of what will happen", timeout=60)
        machine.send_key("alt-i")
        machine.wait_for_text("Install Now", timeout=60)
        machine.send_key("alt-i")
        # Not wait_for_console_text: given a timeout, it reads one queued
        # serial line per second, so it trails the boot's 1000-odd lines and
        # saw the end of a 2-minute install 17 minutes late. Not journalctl
        # --grep either: the journal files "zoomies-installer:" away as the
        # sender, so the full line never matches.
        machine.wait_until_succeeds(
            "dmesg | grep -E 'zoomies-installer: (Installation complete|ERROR)'", timeout=600
        )
        machine.fail("dmesg | grep 'zoomies-installer: ERROR'")
        machine.wait_for_text("All done", timeout=60)
        machine.screenshot(f"{name}-done")
        machine.shutdown()
        return disk


    def boot(installed_in, disk, firmware):
        # A copy-on-write overlay, so every boot starts from the fresh install.
        overlay = f"{tmp}/{installed_in}-{firmware}.qcow2"
        qemu_img("create", "-q", "-f", "qcow2", "-b", disk, "-F", "qcow2", overlay)
        machine = start(start_command(firmware, overlay), f"{installed_in}_on_{firmware}")
        machine.wait_for_unit("multi-user.target")

        if firmware == "uefi":
            machine.succeed("test -d /sys/firmware/efi")
        else:
            machine.fail("test -d /sys/firmware/efi")

        # Offline, Calamares keeps its default time zone, language and keyboard.
        machine.succeed('test "$(readlink /etc/localtime)" = /etc/zoneinfo/Europe/London')
        machine.succeed("grep -qx LANG=en_US.UTF-8 /var/lib/zoomies/locale.conf")
        machine.succeed("grep -qx XKB_DEFAULT_LAYOUT=us /var/lib/zoomies/locale.conf")

        machine.succeed("test -s /boot/efi/EFI/BOOT/BOOTX64.EFI")
        # Kernels live on the root filesystem, not on the small ESP.
        machine.fail("mountpoint -q /boot")
        machine.fail("find /boot/efi -name '*bzImage*' -o -name '*initrd*' | grep -q .")
        machine.succeed("test -s /boot/grub/i386-pc/core.img")
        machine.succeed(
            "test \"$(findmnt -no SOURCE /)\" = \"$(readlink -f /dev/disk/by-label/zoomies)\""
        )
        # The ESP is found by the partition UUID the installer recorded.
        machine.succeed(
            "test \"$(findmnt -no SOURCE /boot/efi)\" = \"$(readlink -f /dev/disk/zoomies-esp)\""
        )

        flag = machine.succeed(
            "dd if=/dev/sda bs=1 skip=446 count=1 status=none | od -An -tx1"
        ).strip()
        assert flag == ("80" if installed_in == "bios" else "00"), flag

        machine.succeed("systemctl is-active nixos-upgrade.timer")

        # Updates reinstall GRUB without the installer's help.
        machine.fail("test -e /dev/disk/zoomies-boot")
        machine.succeed(
            "NIXOS_INSTALL_BOOTLOADER=1 /run/current-system/bin/switch-to-configuration boot"
        )
        machine.succeed('test "$(readlink /dev/disk/zoomies-boot)" = /dev/sda')

        machine.shutdown()


    try:
        with subtest("install under BIOS from a USB stick"):
            bios_disk = install("bios", "bios", "usb")

        with subtest("install under UEFI from a CD"):
            uefi_disk = install("uefi", "uefi", "cd")

        for installed_in, disk in [("bios", bios_disk), ("uefi", uefi_disk)]:
            for firmware in ["bios", "uefi"]:
                with subtest(f"boot the {installed_in} install under {firmware}"):
                    boot(installed_in, disk, firmware)

        with subtest("the boot menu stays hidden until Windows is on the disk"):
            overlay = f"{tmp}/windows.qcow2"
            qemu_img("create", "-q", "-f", "qcow2", "-b", uefi_disk, "-F", "qcow2", overlay)
            machine = start(start_command("uefi", overlay), "next_to_windows")
            machine.wait_for_unit("multi-user.target")
            # Once shown, the menu now waits far longer than a boot takes, so
            # booting in time proves it stayed hidden; it also gives the slow
            # screen reading below time to find it.
            machine.succeed("sed -i 's/set timeout=10/set timeout=600/' /boot/grub/grub.cfg")
            machine.shutdown()
            machine.start()
            machine.wait_for_unit("multi-user.target", timeout=300)
            # GRUB only looks for the file, so an empty one stands in for Windows.
            machine.succeed(
                "mkdir -p /boot/efi/EFI/Microsoft/Boot"
                " && touch /boot/efi/EFI/Microsoft/Boot/bootmgfw.efi"
            )
            machine.shutdown()
            machine.start()
            machine.wait_for_text("configurations", timeout=300)
            machine.screenshot("boot-menu")
            machine.send_key("ret")
            machine.wait_for_unit("multi-user.target")
            machine.shutdown()
    finally:
        for vm in vms:
            vm.crash()
  '';
}
