# With Zoomies alone there is nothing to pick, so the menu stays hidden (see
# splash.nix) and Esc or Shift opens it for an older version. Next to another
# OS, GRUB finds that OS's boot loader and shows the menu. It looks for
# Windows at boot rather than at install time, so the menu also appears when
# Windows is installed later.
{ pkgs, ... }:

let
  theme = pkgs.callPackage ./grub-theme { };
in
{
  boot.loader = {
    grub = {
      inherit theme;
      extraConfig = ''
        if [ -z "''${boot_once}" ]; then
          insmod part_gpt
          insmod part_msdos
          insmod fat
          insmod ntfs
          # GRUB's script has no ||.
          if search --no-floppy --file --set=other /EFI/Microsoft/Boot/bootmgfw.efi; then
            set timeout_style=menu
            set timeout=10
          elif search --no-floppy --file --set=other /bootmgr; then
            set timeout_style=menu
            set timeout=10
          fi
        fi
      '';
      # Shown while the chosen entry loads; the default is the NixOS logo.
      splashImage = "${theme}/background.png";
    };
  };
  system.nixos.distroName = "Zoomies";
}
