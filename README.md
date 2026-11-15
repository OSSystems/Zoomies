<p align="center">
  <img src="assets/mascot/zip.svg" alt="Zip, the Zoomies mascot" width="240">
</p>

# Zoomies

A playful NixOS desktop for kids: a shelf of open-source games, with screen
time and parental controls built in.

Meet **Zip**, a penguin chick with a permanent case of the zoomies.

## Try it

Boot the reference host in a VM:

```sh
nix run .#nixosConfigurations.zoomies.config.system.build.vm
```

It comes with two sample kids: Ana gets 20 minutes a day, and Lia may only
play early in the morning. To reach the grown-ups panel, press and hold 🔒 or
press Ctrl+Alt+P, then enter the PIN `1234`.

### Hacking on the shell

Start the VM with `ZOOMIES_SHELL=$PWD/shell` set, and it runs the Python code
straight from your checkout. After each edit, restart the greeter to see it:

```sh
ssh -p 2222 root@localhost systemctl restart greetd
```

## How it works

Each kid gets a profile: an avatar on the "Who's playing?" screen and an
account of their own, so saves and screen time stay separate.

- **Little kids** get a fullscreen grid of big game tiles and nothing else.
  They have no network access, and their home folder is wiped at every boot,
  except for game saves.
- **Older kids** get a simple desktop with Firefox, LibreOffice, and learning
  and creative apps, dressed in Zoomies colours with Zip flying across the
  wallpaper. Their files are kept. Web traffic goes through a family DNS
  filter (Cloudflare for Families), which keeps adult and malicious sites out
  of everyday browsing. It is not a lock against a determined kid with a
  terminal.

Profiles are not passwords: picking an avatar is the login, so nothing stops
one kid from playing as another.

The grown-ups panel, behind the PIN, lets you add and edit kids, set minutes
per day and allowed hours, grant extra time, and change the PIN. Five wrong
PINs lock the grown-ups account for ten minutes. You can do the same from a
terminal with `zoomies-profile` and `zoomies-time`.

The rules are enforced by the system, not just hidden by the screens: logins
are refused once a kid's time is up, and a running session ends when time
runs out.

## Install it on a PC

Build the installer ISO and write it to a USB stick (this erases the stick):

```sh
nix build .#installer-iso
sudo dd if=result/iso/zoomies-installer.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Boot the PC from the stick. The installer:

1. picks the best internal disk (NVMe first, then SSD, then the largest hard
   disk) and shows what is on it;
2. erases it only after you type `ERASE`;
3. asks for the grown-ups PIN. Skip this and Zoomies asks on first start
   instead.

No network is needed: the whole system is on the stick.

### Requirements

- A 64-bit x86 CPU (32-bit-only UEFI firmware is not supported).
- 4 GiB of RAM.
- An internal disk with room for the system, about 15 GiB including the older
  kids' apps. The installer computes the exact size and lists the disks that
  fit.

### One disk, BIOS and UEFI

The installed disk boots on both legacy BIOS and UEFI firmware. One image
serves every PC, and the disk keeps booting if you switch firmware modes or
move it to another PC:

- GPT with a 1 MiB BIOS boot partition, a 1 GiB ESP mounted at `/boot`, and
  an ext4 root.
- GRUB installed twice from a single `grub.cfg`: into the BIOS boot partition,
  and at the removable UEFI path `EFI/BOOT/BOOTX64.EFI`, which needs no NVRAM
  entry.
- When installed in BIOS mode, the protective MBR is marked active, because
  some old BIOSes refuse to boot GPT disks otherwise. Those BIOSes may still
  refuse a disk installed in UEFI mode.

`nix build .#checks.x86_64-linux.installer` installs from the ISO under both
SeaBIOS and OVMF in QEMU, then boots each installed disk under both.

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
| `nix/packages/zoomies-splash/` | `packages.zoomies-splash` (Plymouth boot splash; theme and renderer in `splash/`) |
| `nix/checks/installer.nix` | `checks.installer` (BIOS/UEFI install and boot in QEMU) |
| `nix/checks/kiosk.nix` | `checks.kiosk` (logins, PIN, screen time, network block, home reset) |
| `nix/checks/splash.nix` | `checks.splash` (records the boot; fails if the screen goes dark before the greeter) |
| `nix/hosts/zoomies/` | `nixosConfigurations.zoomies` |
| `nix/devshell.nix` | `devShells.default` |
| `nix/formatter.nix` | `formatter` (`nix fmt`) |
