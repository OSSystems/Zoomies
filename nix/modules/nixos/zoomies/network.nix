# Blocks every connection made by kid processes except to localhost. Games
# that talk to a local server keep working; nothing reaches the internet.
{ config, lib, ... }:

let
  cfg = config.zoomies;
  gid = toString cfg.kidsGroupId;
  rule = "OUTPUT ! -o lo -m owner --gid-owner ${gid} -j REJECT";
in
{
  config = lib.mkIf (cfg.enable && cfg.network.blockKids) (
    lib.mkMerge [
      (lib.mkIf config.networking.nftables.enable {
        networking.nftables.tables.zoomies = {
          content = ''
            chain output {
              type filter hook output priority filter; policy accept;
              oifname "lo" accept
              meta skgid ${gid} reject
            }
          '';
          family = "inet";
        };
      })
      (lib.mkIf (!config.networking.nftables.enable) {
        assertions = [
          {
            assertion = config.networking.firewall.enable;
            message = "zoomies.network.blockKids needs networking.firewall.enable or nftables.";
          }
        ];
        # Deleted first so a firewall reload does not stack duplicates.
        networking.firewall = {
          extraCommands = ''
            iptables -D ${rule} 2>/dev/null || true
            ip6tables -D ${rule} 2>/dev/null || true
            iptables -I ${rule}
            ip6tables -I ${rule}
          '';
          extraStopCommands = ''
            iptables -D ${rule} 2>/dev/null || true
            ip6tables -D ${rule} 2>/dev/null || true
          '';
        };
      })
    ]
  );
  options.zoomies.network.blockKids = lib.mkOption {
    default = true;
    description = "Keep kids' programs off the network.";
    type = lib.types.bool;
  };
}
