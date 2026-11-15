<p align="center">
  <img src="assets/mascot/zip.svg" alt="Zip, the Zoomies mascot" width="240">
</p>

# Zoomies

A playful NixOS desktop for kids, packed with open-source games, with screen
time and parental controls built in.

Meet **Zip**, a penguin chick with a permanent case of the zoomies.

## Try it

Boot the reference host in a VM:

```sh
nix run .#nixosConfigurations.zoomies.config.system.build.vm
```

It has sample kids (Ana has 20 minutes a day, Lia may only play early in the
morning) and the grown-ups PIN is `1234`; press and hold 🔒, or press
Ctrl+Alt+P, to reach the grown-ups panel. To work on the shell, start it with
`ZOOMIES_SHELL=$PWD/shell` in the environment: the VM then runs the Python
code from the checkout, and
`ssh -p 2222 root@localhost systemctl restart greetd` shows each edit.

## How it works

Every kid has a profile: an avatar on the "Who's playing?" screen and an
account of their own, so saves and screen time stay apart.

- **Little kids** get a fullscreen screen of big game tiles and nothing else.
  They cannot reach the network, and their home is wiped at every boot except
  for game saves.
- **Older kids** get a simple desktop with Firefox, LibreOffice and learning
  and creative apps, in Zoomies colours with Zip flying across the wallpaper,
  and their files are kept. The web goes through a family
  DNS filter (Cloudflare for Families) that keeps adult and malicious sites
  out of everyday browsing; it is not a lock against a determined kid with a
  terminal.

Profiles keep kids' saves and time apart, but they do not lock kids out of
each other's profiles: picking an avatar is the login.

The grown-ups panel, behind the PIN, adds and edits kids, sets minutes per day
and allowed hours, gives extra time and changes the PIN. Five wrong PINs lock
the grown-ups account for ten minutes. Rules are enforced by
the system, not just hidden by the screens: logins are refused once time is
up, and sessions end when it runs out. The same can be done from a terminal
with `zoomies-profile` and `zoomies-time`.

## Install it on a PC

Build the installer ISO and write it to a USB stick (this erases the stick):

```sh
nix build .#installer-iso
sudo dd if=result/iso/zoomies-installer.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Boot the PC from the stick. The installer picks the best internal disk
(NVMe, then SSD, then the largest hard disk), shows what is on it and only
erases it after you type `ERASE`. It then asks for the grown-ups PIN; skip it
and the first start asks instead. It needs no network: the whole system is on
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

Requirements: a 64-bit x86 CPU, 4 GiB of RAM, and an internal disk large
enough for the system, about 15 GiB with the older kids' apps (the installer computes the size and lists the disks it
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
| `nix/modules/nixos/zoomies/` | `nixosModules.zoomies` (the kiosk desktop) |
| `nix/modules/nixos/platform/` | `nixosModules.platform` (disk layout, hybrid boot, hardware) |
| `nix/modules/nixos/installer/` | `nixosModules.installer` |
| `nix/lib/` | `lib.mkInstallerIso` |
| `nix/packages/installer-iso.nix` | `packages.installer-iso` |
| `nix/packages/zoomies-shell/` | `packages.zoomies-shell` (greeter, launcher, grown-ups panel; Python source in `shell/`) |
| `nix/checks/installer.nix` | `checks.installer` (BIOS/UEFI install and boot in QEMU) |
| `nix/checks/kiosk.nix` | `checks.kiosk` (logins, PIN, screen time, network block, home reset) |
| `nix/hosts/zoomies/` | `nixosConfigurations.zoomies` |
| `nix/devshell.nix` | `devShells.default` |
| `nix/formatter.nix` | `formatter` (`nix fmt`) |
