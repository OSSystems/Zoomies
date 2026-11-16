# Installed machines follow this repository's main branch. Only the hosts
# import this: a NixOS machine that uses the modules has its own flake to
# follow.
{ hostName, ... }:

{
  nix = {
    # Updates build in the background, while a kid may be playing.
    daemonCPUSchedPolicy = "idle";
    daemonIOSchedClass = "idle";
    # The disk is sized for a few systems, not every one since installing.
    gc.options = "--delete-older-than 7d";
  };
  system.autoUpgrade = {
    enable = true;
    flake = "github:OSSystems/zoomies#${hostName}";
    # Switching in place would restart the greeter in a kid's session; the
    # new system starts with the next boot instead.
    operation = "boot";
    runGarbageCollection = true;
  };
  systemd = {
    services = {
      # With 2 GiB, building a system next to a 3D game can run out of
      # memory; the update should be what gets stopped, not the game.
      nix-daemon.serviceConfig.OOMScoreAdjust = 1000;
      nixos-upgrade.serviceConfig = {
        CPUSchedulingPolicy = "idle";
        IOSchedulingClass = "idle";
        OOMScoreAdjust = 1000;
      };
    };
    # Family computers are rarely on at the nightly time, and a timer that
    # has never fired has nothing to catch up on, so each boot checks once.
    timers.nixos-upgrade.timerConfig.OnBootSec = "10min";
  };
}
