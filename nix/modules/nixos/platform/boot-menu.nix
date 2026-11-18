# With Zoomies alone there is nothing to pick, so the menu stays hidden. GRUB
# still waits a second, so that grown-ups can press Esc or hold Shift to boot
# an older version. Next to another OS, GRUB finds that OS's boot loader and
# shows the menu. It looks for Windows at boot rather than at install time,
# so the menu also appears when Windows is installed later.
{ pkgs, ... }:

let
  theme = pkgs.callPackage ./grub-theme {
    zoomies-splash = pkgs.callPackage ../../../packages/zoomies-splash/package.nix { };
  };
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
          # A bare --set points $root at Windows' partition, where GRUB
          # would then look for Zoomies' kernels, and no --set prints the
          # partition on the screen; "other" is a variable nothing reads.
          for loader in /EFI/Microsoft/Boot/bootmgfw.efi /bootmgr; do
            if search --no-floppy --file --set=other "$loader"; then
              set timeout_style=menu
              set timeout=10
              break
            fi
          done
        fi
      '';
      # Shown while the chosen entry loads; the default is the NixOS logo.
      splashImage = "${theme}/loading.png";
      timeoutStyle = "hidden";
    };
    timeout = 1;
  };
  system.nixos.distroName = "Zoomies";
}
