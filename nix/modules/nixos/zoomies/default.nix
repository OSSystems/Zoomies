{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.zoomies;
in
{
  config = lib.mkIf cfg.enable {
    environment.systemPackages = cfg.games;
    hardware.graphics.enable = true;
    # Xfce keeps the desktop responsive on old hardware.
    services = {
      displayManager.autoLogin = {
        inherit (cfg) user;
        enable = true;
      };
      pipewire = {
        enable = true;
        pulse.enable = true;
      };
      xserver = {
        desktopManager.xfce.enable = true;
        enable = true;
      };
    };
    users.users.${cfg.user} = {
      description = "Zoomies player";
      extraGroups = [
        "audio"
        "video"
        "input"
      ];
      isNormalUser = true;
    };
  };
  options.zoomies = {
    enable = lib.mkEnableOption "the Zoomies kids desktop";
    games = lib.mkOption {
      default = with pkgs; [
        extremetuxracer
        gcompris
        neverball
        pingus
        supertux
        supertuxkart
        tuxpaint
      ];
      defaultText = lib.literalExpression "a curated set of open-source games";
      description = "Games installed for the kid account.";
      type = lib.types.listOf lib.types.package;
    };
    user = lib.mkOption {
      default = "kid";
      description = "Account the desktop logs in to automatically.";
      type = lib.types.str;
    };
  };
}
