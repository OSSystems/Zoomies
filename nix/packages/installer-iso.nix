{ flake, ... }:

(flake.lib.mkInstallerIso { system = flake.nixosConfigurations.zoomies; }).overrideAttrs (old: {
  meta = old.meta or { } // {
    platforms = [ "x86_64-linux" ];
  };
})
