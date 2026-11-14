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
| `nix/modules/nixos/zoomies.nix` | `nixosModules.zoomies` |
| `nix/hosts/zoomies/` | `nixosConfigurations.zoomies` |
| `nix/devshell.nix` | `devShells.default` |
| `nix/formatter.nix` | `formatter` (`nix fmt`) |
