# Little kids' programs reach nothing but localhost: games that talk to a
# local server keep working, nothing reaches the internet. Older kids are
# online, but only the system resolver may do DNS, so the family filter
# cannot be skipped by simply asking another server.
{ config, lib, ... }:

let
  cfg = config.zoomies;
  little = toString cfg.kidsGroupId;
  older = toString (cfg.kidsGroupId + 1);
  dnsPorts = [
    "53"
    "853"
  ];

  rules =
    lib.optional cfg.network.blockKids "OUTPUT ! -o lo -m owner --gid-owner ${little} -j REJECT"
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
  config = lib.mkIf (cfg.enable && rules != [ ]) (
    lib.mkMerge [
      (lib.mkIf config.networking.nftables.enable {
        networking.nftables.tables.zoomies = {
          content = ''
            chain output {
              type filter hook output priority filter; policy accept;
              oifname "lo" accept
              ${lib.optionalString cfg.network.blockKids "meta skgid ${little} reject"}
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
        networking.firewall = {
          extraCommands =
            remove
            + lib.concatMapStrings (rule: ''
              iptables -I ${rule}
              ip6tables -I ${rule}
            '') rules;
          extraStopCommands = remove;
        };
      })
    ]
  );
  options.zoomies.network.blockKids = lib.mkOption {
    default = true;
    description = "Keep little kids' programs off the network.";
    type = lib.types.bool;
  };
}
