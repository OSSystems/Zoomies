# `nix run .#nixosConfigurations.zoomies.config.system.build.vm` for trying
# the kiosk. Sample profiles cover every screen time state; the known PIN and
# open root login exist only here, never in the published image. The shared
# shell folder and SSH serve hacking on the shell; see the README.
{ lib, pkgs, ... }:

let
  dev = "/mnt/zoomies-shell";
in
{
  environment.extraInit = ''
    if [ -d ${dev}/zoomies_shell ]; then export PYTHONPATH=${dev}; fi
  '';
  security.pam.services.sshd.allowNullPassword = true;
  services.openssh = {
    enable = true;
    settings = {
      PermitEmptyPasswords = "yes";
      PermitRootLogin = "yes";
    };
  };
  # The VM runs the checkout, not the published system.
  system.autoUpgrade.enable = lib.mkForce false;
  systemd.services.zoomies-timekeeper.environment.PYTHONPATH = dev;
  # Root already has an empty password in NixOS VMs.
  users.users.parent.initialPassword = "1234";
  virtualisation = {
    cores = 4;
    diskSize = 8192;
    forwardPorts = [
      {
        from = "host";
        guest.port = 22;
        host = {
          address = "127.0.0.1";
          port = 2222;
        };
      }
    ];
    memorySize = 4096;
    qemu.options = [
      "-vga none"
      "-device virtio-vga"
    ];
    sharedDirectories.zoomies-shell = {
      securityModel = "none";
      source = ''"''${ZOOMIES_SHELL:-$TMPDIR/xchg}"'';
      target = dev;
    };
  };
  zoomies.kids = {
    ana = {
      avatar = "🦊";
      color = "orange";
      dailyMinutes = 20;
      name = "Ana";
    };
    ben = {
      avatar = "🐼";
      color = "green";
      name = "Ben";
    };
    lia = {
      avatar = "🦄";
      color = "purple";
      games = with pkgs; [
        gcompris
        tuxpaint
      ];
      hours = {
        end = "07:00";
        start = "06:00";
      };
      name = "Lia";
    };
  };
  # Developers log in as root with no password, which the panel's switch
  # would not allow.
  zoomies.remoteAccess.enable = lib.mkForce false;
}
