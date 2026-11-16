# Older kids get a plain Xfce desktop with study and creative apps. The web
# goes through a family DNS filter that keeps everyday browsing clean; they
# cannot ask other DNS servers directly. It is not a lock against a
# determined kid with a terminal, who could tunnel out over HTTPS.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.zoomies;
  inherit (cfg) older;
  # Title strips with only a close button: apps are always maximized.
  windowTheme =
    pkgs.runCommand "zoomies-window-theme"
      { nativeBuildInputs = [ (pkgs.python3.withPackages (p: [ p.pycairo ])) ]; }
      ''
        python3 ${./window-theme.py} $out/share/themes/Zoomies/xfwm4
      '';
in
{
  config = lib.mkIf (cfg.enable && older.enable) (
    lib.mkMerge [
      {
        environment = {
          # The cape on the wallpaper flaps; the helper checks the wallpaper
          # is still Zoomies' own.
          etc."xdg/autostart/zoomies-desktop-zip.desktop".text = ''
            [Desktop Entry]
            Type=Application
            Name=Zip on the desktop
            Exec=${cfg.package}/bin/zoomies-desktop-zip ${older.wallpaper}
            OnlyShowIn=XFCE;
            NoDisplay=true
          '';
          # The shelf takes the place of the Xfce panel.
          etc."xdg/autostart/zoomies-shelf.desktop".text = ''
            [Desktop Entry]
            Type=Application
            Name=Zoomies shelf
            Exec=${cfg.package}/bin/zoomies-shelf
            OnlyShowIn=XFCE;
            NoDisplay=true
          '';
          # Settings that would only confuse or let a kid undo the setup.
          etc."xdg/xfce4/kiosk/kioskrc".text = ''
            [xfce4-session]
            SaveSession=NONE
            CustomizeSplash=%zoomies-setup
            CustomizeChooser=%zoomies-setup

            [xfce4-panel]
            CustomizePanel=%zoomies-setup
          '';
          systemPackages = older.apps ++ [ windowTheme ];
        };
        # Kids must not install software of their own.
        nix.settings.allowed-users = lib.mkDefault [
          "root"
          "@wheel"
        ];
        programs.firefox = {
          enable = true;
          # The languages Zoomies' own screens are translated to; English is
          # built in. Firefox fetches them on its first start, online.
          languagePacks = [
            "es-ES"
            "pt-BR"
          ];
          # The easy ways around the filter from inside the browser.
          policies = {
            BlockAboutConfig = true;
            DNSOverHTTPS = {
              Enabled = false;
              Locked = true;
            };
            DisableFirefoxStudies = true;
            DisablePocket = true;
            DisableTelemetry = true;
            ExtensionSettings."*".installation_mode = "blocked";
            OverrideFirstRunPage = "";
            Proxy = {
              Locked = true;
              Mode = "system";
            };
          };
          # Follow the session's language, which the installer saved.
          preferences."intl.locale.requested" = "";
        };
        services.xserver = {
          desktopManager.xfce = {
            enable = true;
            # Kids have no password, so a lock screen would lock them out.
            enableScreensaver = false;
          };
          # greetd starts X itself; startx keeps NixOS from adding LightDM.
          displayManager.startx.enable = true;
          enable = true;
        };
        zoomies.sessions.older =
          let
            desktop = pkgs.writeShellApplication {
              name = "zoomies-older-desktop";
              runtimeInputs = [
                pkgs.gawk
                pkgs.setxkbmap
                pkgs.xfce4-session
                pkgs.xrandr
              ];
              text = ''
                wallpaper=${older.wallpaper}
                ${builtins.readFile ./older-desktop.sh}
              '';
            };
          in
          pkgs.writeShellScript "zoomies-older-session" ''
            ${cfg.loadLocale}
            exec ${pkgs.xinit}/bin/startx ${lib.getExe desktop} -- -keeptty vt"$XDG_VTNR"
          '';
      }
      (lib.mkIf older.dnsFilter.enable {
        assertions = [
          {
            assertion = !config.services.resolved.enable;
            message = ''
              zoomies.older.dnsFilter writes /etc/resolv.conf itself and cannot be
              used with systemd-resolved; set zoomies.older.dnsFilter.enable = false.
            '';
          }
        ];
        environment.etc."resolv.conf".text = ''
          ${lib.concatMapStrings (server: "nameserver ${server}\n") older.dnsFilter.servers}
          options edns0
        '';
        networking = {
          dhcpcd.extraConfig = "nohook resolv.conf";
          networkmanager.dns = "none";
          resolvconf.enable = false;
        };
      })
    ]
  );
  options.zoomies.older = {
    apps = lib.mkOption {
      default = with pkgs; [
        audacity
        gcompris
        inkscape
        kdePackages.kgeography
        kdePackages.ktouch
        krita
        libreoffice
        stellarium
      ];
      defaultText = lib.literalExpression "office, learning and creative apps";
      description = "Apps on the older kids' desktop, besides Firefox and the games.";
      type = lib.types.listOf lib.types.package;
    };
    dnsFilter = {
      enable = lib.mkOption {
        default = true;
        description = ''
          Send every DNS lookup on the machine through a family filter that
          blocks adult and malicious sites. Lookups are made by a system
          service, not by each program, so this covers grown-ups too, and it
          replaces the DNS servers from DHCP, NetworkManager and VPNs.
        '';
        type = lib.types.bool;
      };
      servers = lib.mkOption {
        default = [
          "1.1.1.3"
          "1.0.0.3"
          "2606:4700:4700::1113"
          "2606:4700:4700::1003"
        ];
        description = "Filtering resolvers; the default is Cloudflare for Families.";
        type = lib.types.listOf lib.types.str;
      };
    };
    enable = lib.mkOption {
      default = true;
      description = "Offer older kid profiles with a desktop and filtered web.";
      type = lib.types.bool;
    };
    startable = lib.mkOption {
      # Thunar's bulk renamer and settings would only clutter the shelf.
      default = map toString older.apps ++ [
        "${config.programs.firefox.finalPackage}/share/applications/firefox.desktop"
        "${pkgs.thunar}/share/applications/thunar.desktop"
      ];
      defaultText = lib.literalExpression "apps, Firefox and the file manager";
      description = "Packages and desktop entries the shelf offers, besides the games.";
      internal = true;
      readOnly = true;
      type = lib.types.listOf lib.types.str;
    };
    wallpaper = lib.mkOption {
      default = ../../../../assets/wallpaper/older.svg;
      defaultText = lib.literalMD "Zip flying over the clouds";
      description = "Default wallpaper of the older kids' desktop; kids may pick another.";
      type = lib.types.path;
    };
  };
}
