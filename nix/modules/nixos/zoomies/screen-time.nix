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
    # The greeter greys out kids whose time is up, but PAM is what actually
    # refuses the login.
    security.pam.services.greetd.rules.account.zoomies-time = {
      args = [
        "quiet"
        "${cfg.package}/bin/zoomies-time"
        "check"
      ];
      control = "required";
      modulePath = "${config.security.pam.package}/lib/security/pam_exec.so";
      # Before any "sufficient" account module (LDAP, SSSD, ...) that would
      # end the stack early and skip it.
      order = config.security.pam.services.greetd.rules.account.ldap.order - 50;
    };
    systemd = {
      services.zoomies-timekeeper = {
        before = [ "greetd.service" ];
        description = "Zoomies screen time";
        path = [
          config.systemd.package
          pkgs.pipewire
          pkgs.util-linux
        ];
        serviceConfig = {
          ExecStart = "${cfg.package}/bin/zoomies-time daemon";
          # Screen time must come back after any crash, however often.
          Restart = "always";
          RestartSec = 2;
          RuntimeDirectory = "zoomies";
          RuntimeDirectoryPreserve = true;
        };
        startLimitIntervalSec = 0;
        wantedBy = [ "multi-user.target" ];
      };
      # Parents edit the policy through the shared group; the timekeeper
      # alone writes usage.
      tmpfiles.rules = [
        "d /var/lib/zoomies 2775 root ${if cfg.parent.user == null then "root" else "zoomies-parents"} -"
      ];
    };
  };
}
