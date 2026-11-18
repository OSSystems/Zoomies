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
  kidGroups = [
    "zoomies-kids"
    "zoomies-older"
  ];
  kidCondition = lib.concatMapStringsSep " || " (group: "subject.isInGroup(\"${group}\")") kidGroups;
  pam = "${config.security.pam.package}/lib/security";

  # Cage clears to black until its window draws, a flash between the boot
  # splash and the greeter and whenever a game starts; it paints the sky.
  # It also lights the screen up black and draws one frame later, which on a
  # busy machine without a GPU leaves a second of black after the splash; it
  # lights the screen up with the sky already drawn.
  # At power off and restart it hands the screen to the splash in place;
  # see handover.
  cage = pkgs.cage.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [
      ./cage-sky.patch
      ./cage-first-frame.patch
      ./cage-handover.patch
    ];
  });

  # Run by cage once it stops. When the shell asked for the power off, cage
  # keeps showing the bare sky it faded to until the platform's splash has
  # loaded behind it, says it is holding the screen, and stays until the
  # splash has taken it. Anything else, such as logging out, finds no
  # request and is not held.
  handover = pkgs.writeShellScript "zoomies-handover" ''
    dir=/run/zoomies-splash
    wait_for() {
      for _ in $(${lib.getExe' pkgs.coreutils "seq"} 300); do
        [ -e "$dir/$1" ] && return 0
        ${lib.getExe' pkgs.coreutils "sleep"} 0.01
      done
      return 1
    }
    # The session's stop signals every process in it, including any cage
    # forks while the signals go out; the waits below are bounded.
    trap "" TERM HUP INT
    [ -e "$dir/requested" ] && wait_for ready || exit 0
    # Which compositor to take the screen from: cage, which runs this.
    echo "$PPID" > "$dir/holding"
    wait_for shown
  '';

  kiosk =
    name: program:
    pkgs.writeShellScript "zoomies-${name}-session" ''
      ${cfg.loadLocale}
      # Old GPUs without usable GL still get a desktop through llvmpipe.
      export WLR_RENDERER_ALLOW_SOFTWARE=1
      # There, GTK's GL renderer redraws the whole window on the CPU for
      # every moving cloud; its cairo renderer redraws only what moved.
      if [ -e /run/zoomies-gpu/software ]; then
        export GSK_RENDERER=cairo
      fi
      export ZOOMIES_HANDOVER=${handover}
      # Into the journal: any text on the screen wakes the text console,
      # which then flashes between the boot splash and the greeter.
      exec ${lib.getExe' config.systemd.package "systemd-cat"} -t zoomies-${name} \
        ${lib.getExe cage} -d -- ${program}
    '';
in
{
  config = lib.mkIf cfg.enable {
    environment.etc."polkit-1/rules.d/00-zoomies.rules".text = ''
      // Before NixOS's own rules, which would accept the grown-up's PIN
      // (a wheel password) from a kid's session and so let kids guess it.
      polkit.addAdminRule(function(action, subject) {
        if (${kidCondition}) {
          return ["unix-user:root"];
        }
      });
      // Lingering would keep a kid's programs running after their session
      // ends, outside screen time.
      polkit.addRule(function(action, subject) {
        if (action.id == "org.freedesktop.login1.set-self-linger" &&
            (${kidCondition})) {
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
                lib.imap0 (index: group: {
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
                }) kidGroups
              );
            }
          ];
          # Older kids can reach a text console from their desktop.
          login.rules = lockout;
          # Over SSH the password is the PIN too.
          sshd.rules = lib.mkIf cfg.remoteAccess.enable lockout;
          # Kids could otherwise guess the PIN with su; grown-ups use sudo.
          su.requireWheel = true;
          # greetd fails a locked account just like a wrong PIN, apart from
          # a note in the system's language, so the admin service asks this
          # for the greeter. It reads the count without adding to it, and
          # only root may ask: it ends in pam_permit.
          zoomies-pin-lock.text = ''
            auth requisite ${pam}/pam_rootok.so
            auth required ${faillock} preauth nodelay ${lib.concatStringsSep " " options}
            auth required ${pam}/pam_permit.so
          '';
        };
      polkit.enable = true;
    };
    services.greetd = {
      enable = true;
      # The boot splash hands the screen to cage without quitting, and leaves
      # once the greeter has drawn: quitting earlier gives the screen back to
      # the kernel's black console for a moment.
      greeterManagesPlymouth = config.boot.plymouth.enable;
      settings.default_session = {
        command = kiosk "greeter" "${cfg.package}/bin/zoomies-greeter";
        user = "greeter";
      };
    };
    systemd = {
      services = {
        # "idle" holds the greeter back up to 5 s for boot messages to settle on
        # a text console; the kiosk draws its own screen, so that is only a
        # black screen at the end of the boot.
        greetd.serviceConfig.Type = lib.mkForce "simple";
        plymouth-quit = lib.mkIf config.boot.plymouth.enable {
          after = [ "display-manager.service" ];
          serviceConfig.ExecStartPre = "-${lib.getExe' pkgs.coreutils "timeout"} 60 ${pkgs.runtimeShell} -c 'until ls /run/user/*/zoomies-greeter-ready; do sleep 0.1; done'";
        };
        # Between two sessions, nobody holds the screen and the kernel shows
        # the greeter's text console: black, with any kernel message on it.
        # The console's black is made the sky's colour, and so is its text,
        # so that moment looks like the sky the next screen opens on. Done
        # once the greeter has drawn: text on the console earlier wakes it
        # while the splash hands over.
        zoomies-console-sky = {
          after = [ "display-manager.service" ];
          description = "Paint the greeter's console as the sky";
          script = ''
            until ls /run/user/*/zoomies-greeter-ready >/dev/null 2>&1; do sleep 0.1; done
            # Palette entry 0 is the sky; the colour pair 0 on 0 becomes the
            # default, so later kernel messages draw invisibly too. No
            # cursor, and no blanking, which would turn it black again.
            printf '\033]P0B8ECFF\033[30;40m\033[8]\033[9;0]\033[?25l\033[H\033[2J' \
              > /dev/tty${toString config.services.greetd.settings.terminal.vt}
          '';
          serviceConfig = {
            RemainAfterExit = true;
            TimeoutStartSec = 60;
            Type = "oneshot";
          };
          wantedBy = [ "display-manager.service" ];
        };
        # Asking Mesa takes half a second, too long for every login, so it is
        # asked once, early in the boot, while the rest of the system starts.
        zoomies-gpu = {
          before = [ "display-manager.service" ];
          description = "Check whether Zoomies draws without a GPU";
          script = ''
            if ${lib.getExe' pkgs.mesa-demos "eglinfo"} -B -p surfaceless 2>/dev/null |
              ${lib.getExe pkgs.gnugrep} -qE 'renderer: (llvmpipe|softpipe)'; then
              touch /run/zoomies-gpu/software
            fi
          '';
          serviceConfig = {
            RemainAfterExit = true;
            RuntimeDirectory = "zoomies-gpu";
            RuntimeDirectoryPreserve = true;
            Type = "oneshot";
          };
          wantedBy = [ "display-manager.service" ];
        };
      };
      tmpfiles.rules = [ "d /var/lib/zoomies/faillock 0700 root root -" ];
    };
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
