{ flake, inputs }:

{
  mkInstallerIso =
    {
      modules ? [ ],
      system,
    }:
    (inputs.nixpkgs.lib.nixosSystem {
      modules = [
        flake.nixosModules.installer
        { zoomies.installer.system = system; }
      ]
      ++ modules;
    }).config.system.build.isoImage;
}
