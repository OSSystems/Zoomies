{ flake, ... }:

flake.lib.mkInstallerIso { system = flake.nixosConfigurations.zoomies; }
