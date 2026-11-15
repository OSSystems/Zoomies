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
        # Checks the PIN typed during the install against /etc/shadow.
        environment.systemPackages = [ pkgs.perl ];
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
  globalTimeout = 7200;
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
        machine.wait_for_console_text(
            "zoomies-installer: waiting for confirmation to erase /dev/sda"
        )
        machine.send_chars("ERASE\n")
        machine.wait_for_console_text("zoomies-installer: waiting for the grown-ups PIN")
        machine.send_chars("2468\n2468\n")
        machine.wait_for_console_text(
            "zoomies-installer: (Installation complete.|ERROR)", timeout=1800
        )
        # The installer waits at a prompt after an error; fail right away.
        machine.fail("journalctl -k --grep 'zoomies-installer: ERROR'")
        machine.send_chars("\n")
        machine.wait_for_shutdown()
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

        machine.succeed(
            "perl -e 'exit(crypt($ARGV[0], $ARGV[1]) eq $ARGV[1] ? 0 : 1)' 2468"
            " \"$(awk -F: '$1 == \"parent\" { print $2 }' /etc/shadow)\""
        )

        machine.succeed("test -s /boot/EFI/BOOT/BOOTX64.EFI")
        machine.succeed("test -s /boot/grub/i386-pc/core.img")
        machine.succeed(
            "test \"$(findmnt -no SOURCE /)\""
            " = \"$(readlink -f /dev/disk/by-partlabel/disk-zoomies-root)\""
        )

        flag = machine.succeed(
            "dd if=/dev/sda bs=1 skip=446 count=1 status=none | od -An -tx1"
        ).strip()
        assert flag == ("80" if installed_in == "bios" else "00"), flag

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
    finally:
        for vm in vms:
            vm.crash()
  '';
}
