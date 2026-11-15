# Every session is a single fullscreen app inside cage: no panel, no window
# switching, and cage refuses VT switching, so there is nothing to escape to.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.zoomies;
  pam = "${config.security.pam.package}/lib/security";

  kiosk =
    name: program:
    pkgs.writeShellScript "zoomies-${name}-session" ''
      # Old GPUs without usable GL still get a desktop through llvmpipe.
      export WLR_RENDERER_ALLOW_SOFTWARE=1
      exec ${lib.getExe pkgs.cage} -d -- ${program}
    '';
in
{
  config = lib.mkIf cfg.enable {
    environment.etc."polkit-1/rules.d/00-zoomies.rules".text = ''
      // Before NixOS's own rules, which would accept the grown-up's PIN
      // (a wheel password) from a kid's session and so let kids guess it.
      polkit.addAdminRule(function(action, subject) {
        if (subject.isInGroup("zoomies-kids") || subject.isInGroup("zoomies-older")) {
          return ["unix-user:root"];
        }
      });
      // Lingering would keep a kid's programs running after their session
      // ends, outside screen time.
      polkit.addRule(function(action, subject) {
        if (action.id == "org.freedesktop.login1.set-self-linger" &&
            (subject.isInGroup("zoomies-kids") || subject.isInGroup("zoomies-older"))) {
          return polkit.Result.NO;
        }
      });
    '';
    # The CLIs let parents manage kids and time from a terminal or over SSH.
    environment.systemPackages = [
      cfg.package
      pkgs.foot
    ];
    fonts.packages = [
      pkgs.andika
      pkgs.noto-fonts-color-emoji
    ];
    security = {
      pam.services =
        let
          # The PIN is short, so wrong guesses lock the grown-up account
          # for a while, and the count survives reboots and greeter
          # restarts. Kids never get here: they are let in earlier.
          faillock = "${pam}/pam_faillock.so";
          options = [
            "deny=5"
            "unlock_time=600"
            "dir=/var/lib/zoomies/faillock"
          ];
          lockout = {
            account.zoomies-faillock = {
              args = options;
              control = "required";
              modulePath = faillock;
              order = 10040;
            };
            auth = {
              zoomies-faillock-authfail = {
                args = [ "authfail" ] ++ options;
                control = "[default=die]";
                modulePath = faillock;
                order = config.security.pam.services.login.rules.auth.unix.order + 50;
              };
              zoomies-faillock-preauth = {
                args = [ "preauth" ] ++ options;
                control = "required";
                modulePath = faillock;
                order = 10010;
              };
            };
          };
        in
        {
          # Kids have no password: picking the avatar is the login.
          greetd.rules = lib.mkMerge [
            lockout
            {
              auth = lib.listToAttrs (
                lib.imap0
                  (index: group: {
                    name = group;
                    value = {
                      args = [
                        "quiet"
                        "user"
                        "ingroup"
                        group
                      ];
                      control = "sufficient";
                      modulePath = "${pam}/pam_succeed_if.so";
                      # Ahead of every module that would prompt for a
                      # password, such as the early pam_unix that GNOME
                      # Keyring adds.
                      order = 10000 + index;
                    };
                  })
                  [
                    "zoomies-kids"
                    "zoomies-older"
                  ]
              );
            }
          ];
          # Older kids can reach a text console from their desktop.
          login.rules = lockout;
          # Kids could otherwise guess the PIN with su; grown-ups use sudo.
          su.requireWheel = true;
        };
      polkit.enable = true;
    };
    services.greetd = {
      enable = true;
      settings.default_session = {
        command = kiosk "greeter" "${cfg.package}/bin/zoomies-greeter";
        user = "greeter";
      };
    };
    # "idle" holds the greeter back up to 5 s for boot messages to settle on
    # a text console; the kiosk draws its own screen, so that is only a
    # black screen at the end of the boot.
    systemd.services.greetd.serviceConfig.Type = lib.mkForce "simple";
    systemd.tmpfiles.rules = [ "d /var/lib/zoomies/faillock 0700 root root -" ];
    users = lib.mkIf (cfg.parent.user != null) {
      groups.zoomies-parents = { };
      users.${cfg.parent.user} = {
        description = "Grown-up";
        extraGroups = [
          "wheel"
          "zoomies-parents"
        ]
        ++ lib.optional config.networking.networkmanager.enable "networkmanager";
        isNormalUser = true;
      };
    };
    zoomies.sessions = {
      kid = kiosk "kid" "${cfg.package}/bin/zoomies-launcher";
      parent = kiosk "parent" "${cfg.package}/bin/zoomies-parent";
    };
  };
}
