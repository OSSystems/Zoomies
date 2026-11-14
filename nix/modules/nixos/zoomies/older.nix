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
in
{
  config = lib.mkIf (cfg.enable && older.enable) (
    lib.mkMerge [
      {
        environment = {
          # Settings that would only confuse or let a kid undo the setup.
          etc."xdg/xfce4/kiosk/kioskrc".text = ''
            [xfce4-session]
            SaveSession=NONE
            CustomizeSplash=%zoomies-setup
            CustomizeChooser=%zoomies-setup

            [xfce4-panel]
            CustomizePanel=%zoomies-setup
          '';
          systemPackages = older.apps;
        };
        # Kids must not install software of their own.
        nix.settings.allowed-users = lib.mkDefault [
          "root"
          "@wheel"
        ];
        programs.firefox = {
          enable = true;
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
            # xfdesktop keys the wallpaper by connector, which is only known
            # once X runs, so the default is written here, before xfdesktop
            # starts. A kid's own pick lives in the same file and wins.
            desktop = pkgs.writeShellScript "zoomies-older-desktop" ''
              conf=''${XDG_CONFIG_HOME:-$HOME/.config}/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml
              if [ ! -e "$conf" ]; then
                mkdir -p "$(dirname "$conf")"
                {
                  echo '<?xml version="1.0" encoding="UTF-8"?>'
                  echo '<channel name="xfce4-desktop" version="1.0">'
                  echo '<property name="backdrop" type="empty"><property name="screen0" type="empty">'
                  for monitor in $(${lib.getExe pkgs.xrandr} --listactivemonitors | ${lib.getExe pkgs.gawk} 'NR > 1 { print $4 }'); do
                    echo "<property name=\"monitor$monitor\" type=\"empty\">"
                    for workspace in 0 1 2 3; do
                      echo "<property name=\"workspace$workspace\" type=\"empty\">"
                      echo '<property name="last-image" type="string" value="${older.wallpaper}"/>'
                      echo '</property>'
                    done
                    echo '</property>'
                  done
                  echo '</property></property></channel>'
                } >"$conf"
              fi
              exec ${pkgs.xfce4-session}/bin/startxfce4
            '';
          in
          pkgs.writeShellScript "zoomies-older-session" ''
            exec ${pkgs.xinit}/bin/startx ${desktop} -- -keeptty vt"$XDG_VTNR"
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
    wallpaper = lib.mkOption {
      default = ../../../../assets/wallpaper/older.svg;
      defaultText = lib.literalMD "Zip flying over the clouds";
      description = "Default wallpaper of the older kids' desktop; kids may pick another.";
      type = lib.types.path;
    };
  };
}
