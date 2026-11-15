# The menu appears only when Esc or Shift is pressed (see splash.nix), and
# then looks like Zoomies rather than NixOS.
{ pkgs, ... }:

let
  theme = pkgs.callPackage ./grub-theme { };
in
{
  boot.loader.grub = {
    inherit theme;
    # Shown while the chosen entry loads; the default is the NixOS logo.
    splashImage = "${theme}/background.png";
  };
  system.nixos.distroName = "Zoomies";
}
