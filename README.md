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
terminal with `zoomies-profile` and `zoomies-time`. Its Calm screen switch
stops everything that moves on its own, the drifting clouds and Zip's loops,
for kids who find motion distracting.

The rules are enforced by the system, not just hidden by the screens: logins
are refused once a kid's time is up, and a running session ends when time
runs out.

## Install it on a PC

Build the installer ISO and write it to a USB stick (this erases the stick):

```sh
nix build .#installer-iso
sudo dd if=result/iso/zoomies-installer.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Boot the PC from the stick. It starts quietly behind Zip, into a graphical
installer (Calamares) that asks for:

1. the language of the installer;
2. the time zone, guessed from the network when one is connected and
   confirmed on a map;
3. the disk: erase a whole disk, or partition it by hand.

Zoomies asks for the grown-ups PIN on first start. No network is needed: the
whole system is on the stick.

### Requirements

- A 64-bit x86 CPU (32-bit-only UEFI firmware is not supported).
- 2 GiB of RAM. That fits a 3D game, or Firefox with a few tabs next to
  LibreOffice; heavy sites like video need more.
- An internal disk with room for the system, about 15 GiB including the older
  kids' apps. The installer knows the exact size and refuses smaller disks.

### One disk, BIOS and UEFI

The installed disk boots on both legacy BIOS and UEFI firmware. One image
serves every PC, and the disk keeps booting if you switch firmware modes or
move it to another PC:

- GPT with a BIOS boot partition, a 512 MiB ESP mounted at `/boot/efi`, and
  an ext4 root labelled `zoomies` that also holds `/boot`, so the kernels stay
  off the ESP. The installer records the ESP's partition UUID instead of
  relabelling it, so an ESP shared with another OS keeps its name.
- GRUB installed twice from a single `grub.cfg`: into the BIOS boot partition,
  and at the removable UEFI path `EFI/BOOT/BOOTX64.EFI`, which needs no NVRAM
  entry.
- When installed in BIOS mode, the protective MBR is marked active, because
  some old BIOSes refuse to boot GPT disks otherwise. Those BIOSes may still
  refuse a disk installed in UEFI mode.

`nix build .#checks.x86_64-linux.installer` installs from the ISO under both
SeaBIOS and OVMF in QEMU, then boots each installed disk under both.

## Install it on a Raspberry Pi

One image runs on the Raspberry Pi 3, 4 and 5. Build it and write it to an
SD card or USB stick (this erases the card):

```sh
nix build --accept-flake-config .#packages.aarch64-linux.raspberry-pi-image
zstdcat result/sd-image/zoomies-raspberry-pi.img.zst | sudo dd of=/dev/sdX bs=4M status=progress oflag=sync
```

`--accept-flake-config` trusts the
[nixos-raspberrypi](https://github.com/nvmd/nixos-raspberrypi) binary cache,
so the Raspberry Pi kernel is downloaded instead of built. On an x86 PC the
build also needs an aarch64 builder, or emulation:
`boot.binfmt.emulatedSystems = [ "aarch64-linux" ];` in its NixOS
configuration.

Put the card in the Pi and power it on. On first boot Zoomies grows to fill
the card, then asks for the grown-ups PIN.

### Requirements

- A Raspberry Pi 3, 4 or 5. With 1 GiB of RAM, a Pi suits only the little
  kids' games; the older kids' desktop needs 2 GiB. SuperTuxKart needs a
  Pi 4 or 5: the Pi 3's GPU is too old for it.
- An SD card or USB stick of 16 GB or more.

### How it boots

Every board runs the Pi 4 kernel, which Raspberry Pi OS also ships for the
Pi 3 and 5. The Pi's own firmware loads it straight from the FAT partition,
without U-Boot, along with the device tree for the board.

`config.txt` boots the folder `nixos/default/`, which each update replaces
whole. Earlier systems stay in folders such as `nixos/3-default/`: to go
back, put the card in another computer and point `os_prefix` in
`config.txt` at one of them.

`nix build --accept-flake-config .#checks.x86_64-linux.raspberry-pi` boots
the image's own boot files in QEMU's Pi 3 emulation and runs an update.

## Updates

An installed Zoomies, on a PC or a Pi, updates itself from this repository's
`main` branch. It checks ten minutes after each boot, and every night at
04:40 if it is on, whenever it has a network. The update downloads and builds
in the background, at the lowest priority, so games keep running smoothly.
The new system starts at the next boot, never in the middle of a session.
Kids and their settings are kept. Systems older than 7 days are deleted to
free disk space.

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
| `nix/modules/nixos/raspberry-pi/` | `nixosModules.raspberry-pi` (SD image, firmware boot, Pi hardware) |
| `nix/modules/nixos/installer/` | `nixosModules.installer` |
| `nix/lib/` | `lib.mkInstallerIso` |
| `nix/packages/installer-iso.nix` | `packages.installer-iso` |
| `nix/packages/raspberry-pi-image.nix` | `packages.raspberry-pi-image` (aarch64-linux) |
| `nix/packages/zoomies-shell/` | `packages.zoomies-shell` (greeter, launcher, grown-ups panel; Python source in `shell/`) |
| `nix/packages/zoomies-splash/` | `packages.zoomies-splash` (Plymouth boot splash; theme and renderer in `splash/`) |
| `nix/checks/installer.nix` | `checks.installer` (BIOS/UEFI install and boot in QEMU) |
| `nix/checks/raspberry-pi.nix` | `checks.raspberry-pi` (Pi image boot and update in QEMU) |
| `nix/checks/kiosk.nix` | `checks.kiosk` (logins, PIN, screen time, network block, home reset) |
| `nix/checks/splash.nix` | `checks.splash` (records the boot; fails if the screen goes dark before the greeter) |
| `nix/checks/translations.nix` | `checks.translations` (the template lists every string; each translation compiles) |
| `nix/hosts/zoomies/` | `nixosConfigurations.zoomies` |
| `nix/hosts/zoomies-pi/` | `nixosConfigurations.zoomies-pi` |
| `nix/devshell.nix` | `devShells.default` |
| `nix/formatter.nix` | `formatter` (`nix fmt`) |
