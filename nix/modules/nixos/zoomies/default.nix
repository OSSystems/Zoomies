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
        kind = lib.mkOption {
          default = "little";
          description = ''
            `little` gets the fullscreen game tiles and no network; `older`
            gets a desktop with study apps, filtered web and a home that is
            never reset.
          '';
          type = lib.types.enum [
            "little"
            "older"
          ];
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
    assertions =
      lib.mapAttrsToList (user: _: {
        assertion =
          config.users.users.${user}.extraGroups == [ ]
          && lib.all (group: !(lib.elem user group.members)) (lib.attrValues config.users.groups);
        message = ''
          Zoomies kid ${user} must not be in other groups: the network rules
          match the kid's group, and kids could switch to any other one.
        '';
      }) cfg.kids
      ++ [
        {
          assertion = cfg.older.enable || lib.all (k: k.kind != "older") (lib.attrValues cfg.kids);
          message = "zoomies.kids has older kids, but zoomies.older.enable is false.";
        }
      ];
    environment = {
      etc."zoomies/config.json".text = builtins.toJSON {
        assets = "${cfg.package}/share/zoomies";
        defaultGames = map (game: toString (fixGame game)) cfg.games;
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
          inherit (k) kind;
          games = map (game: toString (fixGame game)) k.games;
        }) cfg.kids;
        olderApps = lib.optionals cfg.older.enable cfg.older.startable;
        olderEnabled = cfg.older.enable;
        olderSession = if cfg.older.enable then cfg.sessions.older else null;
        parent = if cfg.parent.user == null then null else { inherit (cfg.parent) user; };
        parentSession = cfg.sessions.parent;
        resetKeep = cfg.resetHomes.keep;
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
      groups = {
        zoomies-kids.gid = cfg.kidsGroupId;
        zoomies-older.gid = cfg.kidsGroupId + 1;
      };
      # The primary group says which kind of kid this is: the network rules
      # match sockets by their owner's group, and PAM lets both groups in
      # without a password.
      # That group must be their only one, and they get no subordinate id
      # ranges, or sg, newgrp or newgidmap would make sockets the rules do
      # not match. Sound, graphics and gamepads come from logind instead.
      users = lib.mapAttrs (_user: k: {
        autoSubUidGidRange = false;
        description = k.name;
        group = if k.kind == "older" then "zoomies-older" else "zoomies-kids";
        isNormalUser = true;
      }) cfg.kids;
    };
  };
  imports = [
    ./admin.nix
    ./kiosk.nix
    ./network.nix
    ./older.nix
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
      default = { };
      description = ''
        Kids set in the configuration; grown-ups can add more from the
        panel. The attribute name is the login account; each kid has their
        own saves and screen time.
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
      description = ''
        Fixed gid of the little kids' group, so firewall rules can match it;
        older kids get the next one.
      '';
      type = lib.types.ints.positive;
    };
    package = lib.mkOption {
      default = pkgs.callPackage ../../../packages/zoomies-shell/package.nix { };
      defaultText = lib.literalExpression "the Zoomies shell";
      description = "Greeter, launcher, grown-ups panel and screen time tools.";
      type = lib.types.package;
    };
    parent.initialHashedPassword = lib.mkOption {
      default = null;
      description = ''
        Hash of the grown-ups PIN (`mkpasswd 1234`), for machines set up
        ahead of time. Without it, the first boot asks for a PIN. Never set
        it in an image shared with others.
      '';
      type = lib.types.nullOr lib.types.str;
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
      older = lib.mkOption {
        description = "Command greetd starts for an older kid.";
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
