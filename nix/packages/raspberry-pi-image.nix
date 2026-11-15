{ flake, ... }:

flake.nixosConfigurations.zoomies-pi.config.system.build.sdImage.overrideAttrs (old: {
  meta = old.meta or { } // {
    platforms = [ "aarch64-linux" ];
  };
})
