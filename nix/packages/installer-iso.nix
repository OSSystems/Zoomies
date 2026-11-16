{ flake, lib, ... }:

lib.addMetaAttrs { platforms = [ "x86_64-linux" ]; } (
  flake.lib.mkInstallerIso { system = flake.nixosConfigurations.zoomies; }
)
