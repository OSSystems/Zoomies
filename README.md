<p align="center">
  <img src="assets/mascot/zip.svg" alt="Zip, the Zoomies mascot" width="240">
</p>

# Zoomies

A playful NixOS desktop for kids, packed with open-source games and tuned to
run well on old hardware.

Meet **Zip**, a penguin chick with a permanent case of the zoomies.

## Try it

Boot the reference host in a VM:

```sh
nix run .#nixosConfigurations.zoomies.config.system.build.vm
```

## Install it on a PC

Build the installer ISO and write it to a USB stick (this erases the stick):

```sh
nix build .#installer-iso
sudo dd if=result/iso/zoomies-installer.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Boot the PC from the stick. The installer picks the best internal disk
(NVMe, then SSD, then the largest hard disk), shows what is on it and only
erases it after you type `ERASE`. It needs no network: the whole system is on
the stick.

The installed disk boots on both legacy BIOS and UEFI firmware, so the same
image serves every PC, and the disk keeps booting if the firmware mode or the
PC changes (except that some old BIOSes refuse a disk installed in UEFI mode,
see below):

- GPT with a 1 MiB BIOS boot partition, a 1 GiB ESP mounted at `/boot` and an
  ext4 root.
- GRUB installed twice from one `grub.cfg`: into the BIOS boot partition, and
  at the removable UEFI path `EFI/BOOT/BOOTX64.EFI`, which needs no NVRAM
  entry.
- On machines started in BIOS mode, the protective MBR is marked active,
  because some old BIOSes refuse to boot GPT disks otherwise.

Requirements: a 64-bit x86 CPU, 2 GiB of RAM, and an internal disk large
enough for the system (the installer computes the size and lists the disks it
can use). 32-bit-only UEFI firmware is not supported.

`nix build .#checks.x86_64-linux.installer` installs from the ISO under
SeaBIOS and under OVMF in QEMU, then boots each installed disk under both.

## Use it in your own NixOS configuration

```nix
{
  inputs.zoomies.url = "github:OSSystems/zoomies";

  # in your NixOS configuration
  imports = [ inputs.zoomies.nixosModules.zoomies ];
  zoomies.enable = true;
}
```

## Layout

All Nix code lives under `nix/` and is wired by
[red-tape](https://github.com/phaer/red-tape):

| Path | Output |
|---|---|
| `nix/modules/nixos/zoomies.nix` | `nixosModules.zoomies` (the desktop) |
| `nix/modules/nixos/platform/` | `nixosModules.platform` (disk layout, hybrid boot, hardware) |
| `nix/modules/nixos/installer/` | `nixosModules.installer` |
| `nix/lib/` | `lib.mkInstallerIso` |
| `nix/packages/installer-iso.nix` | `packages.installer-iso` |
| `nix/checks/installer.nix` | `checks.installer` (BIOS/UEFI install and boot in QEMU) |
| `nix/hosts/zoomies/` | `nixosConfigurations.zoomies` |
| `nix/devshell.nix` | `devShells.default` |
| `nix/formatter.nix` | `formatter` (`nix fmt`) |
