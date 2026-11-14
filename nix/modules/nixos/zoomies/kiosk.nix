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
    # The CLI lets parents grant time from a terminal or over SSH.
    environment.systemPackages = [
      cfg.package
      pkgs.foot
    ];
    fonts.packages = [
      pkgs.andika
      pkgs.noto-fonts-color-emoji
    ];
    security = {
      pam.services.greetd.rules.auth.zoomies-kids = {
        # Kids have no password: picking the avatar is the login.
        args = [
          "quiet"
          "user"
          "ingroup"
          "zoomies-kids"
        ];
        control = "sufficient";
        modulePath = "${pam}/pam_succeed_if.so";
        order = config.security.pam.services.greetd.rules.auth.unix.order - 10;
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
