# One image serves every country: the installer saves the grown-ups' language
# and keyboard in a file rather than in the system's configuration. greetd
# sources /etc/profile, which sets the system's LANG, after PAM has set up a
# session, so each session reads the file itself as it starts.
{
  config,
  lib,
  ...
}:

let
  cfg = config.zoomies;
in
{
  config = lib.mkIf cfg.enable {
    # The screen time warnings are written by this service, not the session.
    systemd.services.zoomies-timekeeper.serviceConfig.EnvironmentFile = "-${cfg.localeFile}";
    zoomies.loadLocale = ''
      # Only language and keyboard settings, so the file cannot change how
      # the session runs.
      if [ -r ${cfg.localeFile} ]; then
        while IFS='=' read -r name value; do
          case $name in
            LANG | LANGUAGE | LC_* | XKB_DEFAULT_*) export "$name=$value" ;;
          esac
        done <${cfg.localeFile}
      fi
    '';
  };
  options.zoomies = {
    loadLocale = lib.mkOption {
      description = "Shell code a session runs first to take the saved language and keyboard.";
      internal = true;
      type = lib.types.lines;
    };
    localeFile = lib.mkOption {
      default = "/var/lib/zoomies/locale.conf";
      description = ''
        Lines of VARIABLE=value, such as LANG and XKB_DEFAULT_LAYOUT, that every
        Zoomies session starts with. The installer writes it.
      '';
      readOnly = true;
      type = lib.types.str;
    };
  };
}
