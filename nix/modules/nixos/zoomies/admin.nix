# The panel and the first-boot wizard run unprivileged; this root service
# does the few things they need root for: creating kid accounts and setting
# the PIN. Only the grown-up and the greeter can reach its socket.
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
  config = lib.mkIf (cfg.enable && cfg.parent.user != null) {
    assertions = [
      {
        # Accounts and the PIN made at runtime would be undone by the next
        # system activation.
        assertion = config.users.mutableUsers;
        message = ''
          Zoomies creates kid accounts and sets the PIN at runtime, which
          needs users.mutableUsers; for kids set only in the configuration,
          set zoomies.parent.user = null.
        '';
      }
    ];
    systemd = {
      services.zoomies-admin = {
        description = "Zoomies profiles and PIN";
        path = [
          config.systemd.package
          pkgs.pamtester
          pkgs.procps
          pkgs.shadow
        ];
        serviceConfig = {
          ExecStart = "${cfg.package}/bin/zoomies-profile serve";
          Restart = "on-failure";
        };
      };
      sockets.zoomies-admin = {
        socketConfig = {
          ListenStream = "/run/zoomies-admin.sock";
          SocketGroup = "zoomies-setup";
          SocketMode = "0660";
        };
        wantedBy = [ "sockets.target" ];
      };
    };
    users = {
      groups.zoomies-setup.members = [
        "greeter"
        cfg.parent.user
      ];
      users.${cfg.parent.user}.initialHashedPassword = lib.mkIf (
        cfg.parent.initialHashedPassword != null
      ) cfg.parent.initialHashedPassword;
    };
  };
}
