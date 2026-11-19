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
        # GRUB draws the picture behind its terminal only when something is
        # written, and nothing is while it waits and loads Linux: the screen
        # stayed black for that whole time, seconds on BIOS. Clearing draws
        # each picture now: the splash's first frame, faded in from the
        # firmware's black. The theme sits next to where GRUB was installed.
        # GRUB has no shorter sleep than a second; a silent note in its
        # tune player holds each step for 60 ms. The first, almost black,
        # stays 240 ms: a screen switching to GRUB's mode may show nothing
        # for that long.
        if regexp --set=1:zoomies '^(.*)/theme\.txt$' "''${theme}"; then
          for step in 1 2 3 4 5 6 7; do
            background_image --mode stretch "''${zoomies}/fade-''${step}.png"
            clear
            if [ "''${step}" = 1 ]; then
              play 250 0 1
            else
              play 1000 0 1
            fi
          done
          background_image --mode stretch "''${zoomies}/loading.png"
        fi
        clear
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
      # The theme's picture is shown instead, after its fade; the default
      # is the NixOS logo.
      splashImage = null;
      timeoutStyle = "hidden";
    };
    timeout = 1;
  };
  system.nixos.distroName = "Zoomies";
}
