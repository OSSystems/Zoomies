# A fresh home on every boot undoes whatever a kid changed by accident,
# while saves and drawings survive.
{ config, lib, ... }:

let
  cfg = config.zoomies;
in
{
  config = lib.mkIf (cfg.enable && cfg.resetHomes.enable) {
    systemd.services.zoomies-reset-homes = {
      after = [ "local-fs.target" ];
      before = [
        "greetd.service"
        "systemd-user-sessions.service"
      ];
      description = "Reset the kids' home directories";
      # Only at boot: rerunning it on a system switch would wipe the home
      # of a kid who is playing right now.
      restartIfChanged = false;
      serviceConfig = {
        # Kids added from the panel are not known at build time, so the
        # list comes from the merged profiles.
        ExecStart = "${cfg.package}/bin/zoomies-reset-home --all";
        RemainAfterExit = true;
        Type = "oneshot";
      };
      unitConfig.RequiresMountsFor = "/home";
      wantedBy = [ "multi-user.target" ];
    };
  };
  options.zoomies.resetHomes = {
    enable = lib.mkOption {
      default = true;
      description = "Wipe little kids' homes at boot, keeping only game data.";
      type = lib.types.bool;
    };
    keep = lib.mkOption {
      default = [
        ".config/gcompris-qt"
        ".config/supertuxkart"
        ".etr"
        ".local/share/GCompris"
        ".local/share/supertux2"
        ".local/share/supertuxkart"
        ".neverball"
        ".pingus"
        ".tuxpaint"
      ];
      description = "Paths, relative to each kid's home, that survive the reset.";
      type = lib.types.listOf lib.types.str;
    };
  };
}
