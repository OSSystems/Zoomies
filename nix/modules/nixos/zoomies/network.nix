# Kids' programs reach nothing but localhost unless a grown-up lets them
# online: the timekeeper keeps the list of kids who may be online now, and
# everyone else is rejected, so an empty or lost list fails closed. Games
# that talk to a local server keep working. Older kids online may only ask
# the system resolver for names, so the family filter cannot be skipped by
# simply asking another server.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.zoomies;
  little = toString cfg.kidsGroupId;
  older = toString (cfg.kidsGroupId + 1);
  kidGroups = [ little ] ++ lib.optional cfg.older.enable older;
  dnsPorts = [
    "53"
    "853"
  ];
  chain = "zoomies-online";

  rules =
    lib.optionals cfg.network.blockKids (
      map (gid: "OUTPUT ! -o lo -m owner --gid-owner ${gid} -j ${chain}") kidGroups
    )
    ++ lib.optionals cfg.older.enable (
      lib.mapCartesianProduct
        (
          { protocol, targetPort }:
          "OUTPUT ! -o lo -p ${protocol} --dport ${targetPort} -m owner --gid-owner ${older} -j REJECT"
        )
        {
          protocol = [
            "tcp"
            "udp"
          ];
          targetPort = dnsPorts;
        }
    );

  remove = lib.concatMapStrings (rule: ''
    iptables -D ${rule} 2>/dev/null || true
    ip6tables -D ${rule} 2>/dev/null || true
  '') rules;
in
{
  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        zoomies.internetBackend =
          if !cfg.network.blockKids then
            null
          else if config.networking.nftables.enable then
            "nftables"
          else
            "iptables";
      }
      (lib.mkIf (rules != [ ]) (
        lib.mkMerge [
          (lib.mkIf config.networking.nftables.enable {
            networking.nftables.tables.zoomies = {
              content = ''
                # The timekeeper adds kids with a timeout and renews them,
                # so none stays online if it stops.
                set online {
                  typeof meta skuid
                  flags timeout
                }
                chain output {
                  type filter hook output priority filter; policy accept;
                  oifname "lo" accept
                  ${lib.optionalString cfg.network.blockKids "meta skgid { ${lib.concatStringsSep ", " kidGroups} } meta skuid != @online reject"}
                  ${lib.optionalString cfg.older.enable ''
                    meta skgid ${older} udp dport { ${lib.concatStringsSep ", " dnsPorts} } reject
                    meta skgid ${older} tcp dport { ${lib.concatStringsSep ", " dnsPorts} } reject
                  ''}
                }
              '';
              family = "inet";
            };
          })
          (lib.mkIf (!config.networking.nftables.enable) {
            assertions = [
              {
                assertion = config.networking.firewall.enable;
                message = "Zoomies network rules need networking.firewall.enable or nftables.";
              }
            ];
            # Deleted first so a firewall reload does not stack duplicates.
            # The chain keeps the timekeeper's list across reloads; a new
            # one rejects everyone until the timekeeper fills it.
            networking.firewall = {
              extraCommands =
                remove
                + lib.optionalString cfg.network.blockKids ''
                  for ipt in iptables ip6tables; do
                    $ipt -N ${chain} 2>/dev/null || true
                    $ipt -C ${chain} -j REJECT 2>/dev/null || $ipt -A ${chain} -j REJECT
                  done
                ''
                + lib.concatMapStrings (rule: ''
                  iptables -I ${rule}
                  ip6tables -I ${rule}
                '') rules;
              extraStopCommands = remove;
            };
          })
        ]
      ))
      (lib.mkIf (cfg.internetBackend != null) {
        systemd.services.zoomies-timekeeper.path = [
          (if cfg.internetBackend == "nftables" then pkgs.nftables else config.networking.firewall.package)
        ];
      })
    ]
  );
  options.zoomies = {
    internetBackend = lib.mkOption {
      description = "Firewall the timekeeper tells which kids may be online.";
      internal = true;
      readOnly = true;
      type = lib.types.nullOr (
        lib.types.enum [
          "iptables"
          "nftables"
        ]
      );
    };
    network.blockKids = lib.mkOption {
      default = true;
      description = ''
        Keep kids offline unless the grown-ups let them online from the
        panel; older kids are online by default. False leaves every kid
        online all the time.
      '';
      type = lib.types.bool;
    };
  };
}
