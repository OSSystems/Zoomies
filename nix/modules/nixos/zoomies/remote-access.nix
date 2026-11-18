# Grown-ups can switch SSH on from the panel to look after the machine from
# another computer at home. Their password is the short PIN, so only the
# grown-up account may log in, only from the local network, and wrong
# guesses count towards the same lock as on the profile screen. The admin
# service keeps the choice in a file that sshd needs to start, so it
# survives reboots and nothing listens until a grown-up asks for it.
{
  config,
  lib,
  ...
}:

let
  cfg = config.zoomies;
in
{
  config = lib.mkIf (cfg.enable && cfg.remoteAccess.enable) {
    assertions = [
      {
        assertion = cfg.parent.user != null;
        message = "zoomies.remoteAccess needs the grown-up account, zoomies.parent.user.";
      }
    ];
    services.openssh = {
      enable = true;
      # sshd asks PAM even for users AllowUsers turns away, and PAM counts
      # the wrong PIN; outside the home network the PIN is not even asked,
      # so strangers cannot lock the grown-up out. Asking is turned off there
      # rather than on at home: sshd only sets up keyboard-interactive, and
      # NixOS only lets PAM check passwords, when they are on for everyone.
      extraConfig = ''
        Match Address *,${lib.concatMapStringsSep "," (network: "!${network}") cfg.remoteAccess.networks}
          KbdInteractiveAuthentication no
          PasswordAuthentication no
      '';
      settings = {
        AllowUsers = map (network: "${cfg.parent.user}@${network}") cfg.remoteAccess.networks;
        KbdInteractiveAuthentication = true;
        PasswordAuthentication = true;
        PermitRootLogin = "no";
      };
      # The switch starts and stops sshd.service itself.
      startWhenNeeded = false;
    };
    systemd.services.sshd.unitConfig.ConditionPathExists = cfg.remoteAccess.flag;
  };
  options.zoomies.remoteAccess = {
    enable = lib.mkEnableOption ''
      a switch in the grown-ups panel that turns on SSH for the grown-up
      account. It takes over services.openssh: sshd runs only while the
      switch is on, and lets in no one but the grown-up'';
    flag = lib.mkOption {
      default = "/var/lib/zoomies/remote-access";
      description = "File whose presence means the grown-ups turned remote access on.";
      internal = true;
      readOnly = true;
      type = lib.types.str;
    };
    networks = lib.mkOption {
      default = [
        "10.0.0.0/8"
        "127.0.0.0/8"
        "169.254.0.0/16"
        "172.16.0.0/12"
        "192.168.0.0/16"
        "::1/128"
        "fc00::/7"
        "fe80::/10"
      ];
      description = ''
        Addresses the grown-up may log in from; the private ranges of a home
        network by default, never the internet.
      '';
      type = lib.types.listOf lib.types.str;
    };
  };
}
