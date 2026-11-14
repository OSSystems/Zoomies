{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.zoomies;
  fixGame = import ./games.nix { inherit lib pkgs; };

  kid =
    { name, ... }:
    {
      options = {
        avatar = lib.mkOption {
          default = "🐧";
          description = "Emoji the kid picks on the profile screen.";
          type = lib.types.str;
        };
        color = lib.mkOption {
          default = "sky";
          description = "Background colour behind the avatar.";
          type = lib.types.enum [
            "green"
            "orange"
            "pink"
            "purple"
            "red"
            "sky"
            "teal"
            "yellow"
          ];
        };
        dailyMinutes = lib.mkOption {
          default = null;
          description = ''
            Minutes of play a day, or null for no limit. Parents can change
            it at runtime from the grown-ups panel.
          '';
          type = lib.types.nullOr lib.types.ints.positive;
        };
        games = lib.mkOption {
          default = cfg.games;
          defaultText = lib.literalExpression "config.zoomies.games";
          description = "Games on this kid's home screen.";
          type = lib.types.listOf lib.types.package;
        };
        hours = lib.mkOption {
          default = null;
          description = "Time of day when playing is allowed, or null for any time.";
          example = {
            end = "20:00";
            start = "08:00";
          };
          type = lib.types.nullOr (
            lib.types.submodule {
              options = {
                # "24:00" lets a window run until midnight.
                end = lib.mkOption { type = lib.types.strMatching "(([01][0-9]|2[0-3]):[0-5][0-9])|24:00"; };
                start = lib.mkOption { type = lib.types.strMatching "([01][0-9]|2[0-3]):[0-5][0-9]"; };
              };
            }
          );
        };
        name = lib.mkOption {
          default = name;
          defaultText = lib.literalExpression "<attribute name>";
          description = "Name shown on the profile screen.";
          type = lib.types.str;
        };
      };
    };
in
{
  config = lib.mkIf cfg.enable {
    assertions = lib.mapAttrsToList (user: _: {
      assertion =
        config.users.users.${user}.extraGroups == [ ]
        && lib.all (group: !(lib.elem user group.members)) (lib.attrValues config.users.groups);
      message = ''
        Zoomies kid ${user} must not be in other groups: the network rules
        match the kid's group, and kids could switch to any other one.
      '';
    }) cfg.kids;
    environment = {
      etc."zoomies/config.json".text = builtins.toJSON {
        assets = "${cfg.package}/share/zoomies";
        kidSession = cfg.sessions.kid;
        kids = lib.mapAttrsToList (user: k: {
          inherit user;
          inherit (k)
            avatar
            color
            dailyMinutes
            hours
            name
            ;
          games = map (game: toString (fixGame game)) k.games;
        }) cfg.kids;
        parent = if cfg.parent.user == null then null else { inherit (cfg.parent) user; };
        parentSession = cfg.sessions.parent;
        warningSound = "${pkgs.sound-theme-freedesktop}/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga";
      };
      systemPackages = map fixGame (
        lib.unique (cfg.games ++ lib.concatMap (k: k.games) (lib.attrValues cfg.kids))
      );
    };
    hardware.graphics.enable = true;
    services.pipewire = {
      enable = true;
      pulse.enable = true;
    };
    users = {
      groups.zoomies-kids.gid = cfg.kidsGroupId;
      # Kids get the kids group as their primary group: the network block
      # matches sockets by their owner's group.
      users = lib.mapAttrs (_user: k: {
        autoSubUidGidRange = false;
        description = k.name;
        group = "zoomies-kids";
        isNormalUser = true;
      }) cfg.kids;
    };
  };
  imports = [
    ./kiosk.nix
    ./network.nix
    ./reset.nix
    ./screen-time.nix
  ];
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
      description = "Games installed for every kid unless their profile picks others.";
      type = lib.types.listOf lib.types.package;
    };
    kids = lib.mkOption {
      default.kid = { };
      description = ''
        One profile per kid. The attribute name is the login account; each
        kid has their own saves and screen time.
      '';
      example = lib.literalExpression ''
        {
          ana = { avatar = "🦊"; color = "orange"; dailyMinutes = 60; };
          ben = { avatar = "🐼"; color = "green"; hours = { start = "08:00"; end = "19:00"; }; };
        }
      '';
      type = lib.types.attrsOf (lib.types.submodule kid);
    };
    kidsGroupId = lib.mkOption {
      default = 2700;
      description = "Fixed gid of the kids group, so firewall rules can match it.";
      type = lib.types.ints.positive;
    };
    package = lib.mkOption {
      default = pkgs.callPackage ../../../packages/zoomies-shell/package.nix { };
      defaultText = lib.literalExpression "the Zoomies shell";
      description = "Greeter, launcher, grown-ups panel and screen time tools.";
      type = lib.types.package;
    };
    parent.user = lib.mkOption {
      default = "parent";
      description = ''
        Grown-up account behind the lock on the profile screen; its password
        is the PIN. Null removes the way out of the kiosk.
      '';
      type = lib.types.nullOr lib.types.str;
    };
    sessions = {
      kid = lib.mkOption {
        description = "Command greetd starts for a kid.";
        internal = true;
        type = lib.types.path;
      };
      parent = lib.mkOption {
        description = "Command greetd starts for the grown-up.";
        internal = true;
        type = lib.types.path;
      };
    };
  };
}
