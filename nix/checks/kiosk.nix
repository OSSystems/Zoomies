# Drives the real greeter and launcher with keystrokes and checks the
# outcome from the system side, so screen time, the PIN, the network block
# and the home reset are enforced by the OS, not just hidden by the UI.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  # A stand-in game: a real window that covers the launcher, cheap to start.
  game = pkgs.makeDesktopItem {
    categories = [ "Game" ];
    desktopName = "Aaa Test Game";
    exec = "${lib.getExe pkgs.foot} --title zoomies-test-game";
    name = "zoomies-test-game";
  };

  # Talks to greetd directly, bypassing the greeter, to prove PAM itself
  # refuses kids whose time is up.
  greetdTry = pkgs.writers.writePython3Bin "greetd-try" { } ''
    import glob
    import json
    import socket
    import struct
    import sys

    sock = socket.socket(socket.AF_UNIX)
    sock.connect(glob.glob("/run/greetd-*.sock")[0])


    def send(payload):
        data = json.dumps(payload).encode()
        sock.sendall(struct.pack("=I", len(data)) + data)
        size = struct.unpack("=I", sock.recv(4))[0]
        return json.loads(sock.recv(size))


    reply = send({"type": "create_session", "username": sys.argv[1]})
    send({"type": "cancel_session"})
    print(reply)
    sys.exit(0 if reply["type"] == "success" else 1)
  '';
in
pkgs.testers.runNixOSTest {
  name = "zoomies-kiosk";
  nodes = {
    machine = {
      environment.systemPackages = [
        greetdTry
        pkgs.curl
      ];
      imports = [ flake.nixosModules.zoomies ];
      users.users.parent.initialPassword = "1234";
      virtualisation = {
        memorySize = 2048;
        qemu.options = [
          "-vga none"
          "-device virtio-vga"
        ];
      };
      zoomies = {
        enable = true;
        games = [ game ];
        kids = {
          ana = {
            avatar = "🦊";
            dailyMinutes = 60;
          };
          ben.avatar = "🐼";
          lia.avatar = "🦄";
        };
      };
    };
    server = {
      networking.firewall.allowedTCPPorts = [ 80 ];
      services.nginx = {
        enable = true;
        virtualHosts.server.locations."/".return = "200 hello";
      };
    };
  };
  testScript = ''
    import json


    def write_state(name, data):
        machine.succeed(
            f"echo '{json.dumps(data)}' > /var/lib/zoomies/{name}.json"
        )


    def wait_for_greeter():
        machine.wait_until_succeeds("pgrep -u greeter -f zoomies-greeter")
        # The window needs a moment to map and take keyboard focus.
        machine.sleep(5)


    def log_out(user):
        machine.succeed(f"loginctl terminate-user {user}")
        machine.wait_until_fails(f"pgrep -u {user} cage")
        wait_for_greeter()


    start_all()
    server.wait_for_unit("nginx.service")
    machine.wait_for_unit("greetd.service")
    machine.wait_for_unit("zoomies-timekeeper.service")

    with subtest("the profile picker comes up"):
        wait_for_greeter()
        machine.screenshot("greeter")

    with subtest("a wrong PIN keeps grown-ups out"):
        machine.send_key("ctrl-alt-p")
        machine.sleep(2)
        machine.send_chars("9999\n")
        machine.sleep(5)
        machine.fail("pgrep -u parent zoomies-parent")
        machine.send_key("esc")

    with subtest("the PIN opens the grown-ups panel"):
        machine.send_key("ctrl-alt-p")
        machine.sleep(2)
        machine.send_chars("1234\n")
        machine.wait_until_succeeds("pgrep -u parent -f zoomies-parent")
        machine.sleep(3)
        machine.screenshot("parent")
        log_out("parent")

    with subtest("a kid logs in by picking the avatar"):
        machine.send_key("ret")
        machine.wait_until_succeeds("pgrep -u ana -f zoomies-launcher")
        machine.succeed("loginctl show-user ana --property=State | grep -q active")
        machine.sleep(5)
        machine.screenshot("launcher")

    with subtest("a game covers the launcher and quitting it goes home"):
        machine.send_key("ret")
        machine.wait_until_succeeds("pgrep -u ana -f zoomies-test-game")
        machine.succeed("pkill -u ana -f zoomies-test-game")
        machine.sleep(2)
        machine.succeed("pgrep -u ana -f zoomies-launcher")

    with subtest("kids cannot reach the network"):
        machine.succeed("curl -sf --max-time 5 http://server/")
        machine.fail("runuser -u ana -- curl -sf --max-time 5 http://server/")

    with subtest("the session ends when screen time runs out"):
        # Ana has been playing for a while; a one-minute budget is used up.
        write_state("policy", {"kids": {"ana": {"dailyMinutes": 1}}})
        machine.wait_until_fails("pgrep -u ana cage", timeout=120)
        wait_for_greeter()
        machine.screenshot("time-up")

    with subtest("PAM refuses a kid whose time is up"):
        machine.fail("greetd-try ana")
        machine.fail("zoomies-time check ana")
        machine.succeed("greetd-try ben")

    with subtest("bonus time lets the kid back in"):
        machine.succeed("zoomies-time grant ana 15")
        machine.succeed("greetd-try ana")

    with subtest("kids cannot log in outside their hours"):
        hour = int(machine.succeed("date +%H"))
        write_state("policy", {"kids": {"lia": {"hours": {
            "start": f"{(hour + 2) % 24:02d}:00",
            "end": f"{(hour + 3) % 24:02d}:00",
        }}}})
        machine.fail("greetd-try lia")
        machine.succeed("greetd-try ben")

    with subtest("homes are reset at boot, saves survive"):
        machine.succeed(
            "runuser -u ana -- sh -c 'mkdir -p ~/.pingus ~/Downloads"
            " && touch ~/.pingus/save ~/Downloads/junk ~/junk'"
        )
        machine.shutdown()
        machine.start()
        machine.wait_for_unit("zoomies-reset-homes.service")
        machine.succeed("test -e /home/ana/.pingus/save")
        machine.fail("test -e /home/ana/junk")
        machine.fail("test -e /home/ana/Downloads")
  '';
}
