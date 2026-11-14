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
      script = lib.concatMapStrings (user: ''
        ${cfg.package}/bin/zoomies-reset-home ${
          lib.escapeShellArgs ([ config.users.users.${user}.home ] ++ cfg.resetHomes.keep)
        }
      '') (lib.attrNames cfg.kids);
      serviceConfig = {
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
      description = "Wipe the kids' homes at boot, keeping only game data.";
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
