# Agent notes

- All Nix code lives in `nix/`; red-tape maps paths to flake outputs.
- Before committing: `nix fmt` and `nix flake check --no-build`.
- After touching `platform/` or `installer/`, run
  `nix build -L .#checks.x86_64-linux.installer` (needs KVM).
- After touching `shell/` or `nix/modules/nixos/zoomies/`, run
  `nix build -L .#checks.x86_64-linux.kiosk` (needs KVM).
- Kids' protections are enforced by the system (PAM, the timekeeper,
  firewall rules, the admin service), never only by the screens; test them
  from the system side.
- One installed system boots on both BIOS and UEFI. Do not add per-firmware
  hosts.
- Images are shared publicly: redistributable firmware only, no secrets.
- `nixosModules.zoomies` must stay usable on any NixOS machine; disk and boot
  belong in `nixosModules.platform`.
- Comments explain why, never what.
- Make logical commits, refactoring first.
