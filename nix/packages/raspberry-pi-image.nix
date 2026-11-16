{ flake, lib, ... }:

lib.addMetaAttrs {
  platforms = [ "aarch64-linux" ];
} flake.nixosConfigurations.zoomies-pi.config.system.build.sdImage
