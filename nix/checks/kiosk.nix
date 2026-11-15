# Drives the real greeter, launcher, wizard and panel with keystrokes and
# checks the outcome from the system side, so screen time, the PIN,
# profiles, the network rules and the home reset are enforced by the OS,
# not just hidden by the UI.
#
# The machines have 2 GiB of RAM, the smallest Zoomies supports, and run a
# real 3D game, Firefox and LibreOffice, so a PC that small stays usable.
# Memory use lands in memory-report.txt. QEMU has no GPU acceleration, so
# Mesa renders on the CPU and the numbers are a little pessimistic.
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
  # decides who gets in. An optional second argument answers the password
  # prompt.
  greetdTry = pkgs.writers.writePython3Bin "greetd-try" { } ''
    import glob
    import json
    import socket
    import struct
    import sys

    sock = socket.socket(socket.AF_UNIX)
    sock.connect(glob.glob("/run/greetd-*.sock")[0])
    secret = sys.argv[2] if len(sys.argv) > 2 else None


    def send(payload):
        data = json.dumps(payload).encode()
        sock.sendall(struct.pack("=I", len(data)) + data)
        size = struct.unpack("=I", sock.recv(4))[0]
        return json.loads(sock.recv(size))


    reply = send({"type": "create_session", "username": sys.argv[1]})
    while reply["type"] == "auth_message" and secret is not None:
        reply = send({"type": "post_auth_message_response", "response": secret})
        secret = None
    send({"type": "cancel_session"})
    print(reply)
    sys.exit(0 if reply["type"] == "success" else 1)
  '';

  manual = flake.nixosConfigurations.zoomies.config.system.build.manual.manualHTML;

  # Static manuals are lighter than the sites kids use; these stand in for a
  # video or document app: a large JS heap and a page that keeps repainting.
  webApp = pkgs.writeTextDir "app.html" ''
    <!doctype html>
    <title>web app</title>
    <canvas id="c" width="1280" height="720"></canvas>
    <script>
      const heap = [];
      for (let i = 0; i < 40; i++) heap.push(new Float64Array(256 * 1024).fill(i));
      const ctx = document.getElementById("c").getContext("2d");
      let t = 0;
      (function draw() {
        ctx.fillStyle = `hsl(''${t++ % 360} 60% 50%)`;
        ctx.fillRect(0, 0, 1280, 720);
        requestAnimationFrame(draw);
      })();
    </script>
  '';

  pages = [
    "file://${manual}/share/doc/nixos/index.html"
    "file://${manual}/share/doc/nixos/release-notes.html"
    "file://${webApp}/app.html"
    "file://${webApp}/app.html?2"
  ];

  common = {
    imports = [
      flake.nixosModules.zoomies
      # The zram and VM tuning of a real install, not its disk layout.
      ../modules/nixos/platform/hardware.nix
    ];
    virtualisation = {
      memorySize = 2048;
      qemu.options = [
        "-vga none"
        "-device virtio-vga"
      ];
    };
    zoomies = {
      enable = true;
      games = [
        game
        # The heaviest game in the default set.
        pkgs.supertuxkart
      ];
      older.apps = [ pkgs.libreoffice ];
    };
  };
in
pkgs.testers.runNixOSTest {
  # qemu-system-x86_64 under KVM.
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-kiosk";
  nodes = {
    # A fresh install that skipped the installer's PIN question. It also
    # covers the nftables firewall and a system without older kids.
    fresh = {
      environment.systemPackages = [
        greetdTry
        pkgs.curl
      ];
      imports = [ common ];
      networking.nftables.enable = true;
      zoomies.older.enable = false;
    };
    # Set up ahead of time: kids and the PIN (1234) in the configuration.
    machine =
      { nodes, ... }:
      {
        environment.systemPackages = [
          greetdTry
          pkgs.curl
          pkgs.dig
          pkgs.e2fsprogs
          pkgs.pam
          pkgs.xdotool
        ];
        imports = [ common ];
        zoomies = {
          kids = {
            ana = {
              avatar = "🦊";
              dailyMinutes = 60;
            };
            ben.avatar = "🐼";
            lia.avatar = "🦄";
          };
          older.dnsFilter.servers = [ nodes.server.networking.primaryIPAddress ];
          parent.initialHashedPassword = "$y$j9T$3WW/k1HS/Ed6c6kwRa2ZP/$rNZyoGDfB9pcnRP3J/BeYYy2AjCMPPQ4CVQgZnLVdz3";
        };
      };
    # Web server and stand-in family DNS filter.
    server =
      { config, ... }:
      {
        networking.firewall = {
          allowedTCPPorts = [
            53
            80
          ];
          allowedUDPPorts = [ 53 ];
        };
        services = {
          dnsmasq = {
            enable = true;
            settings = {
              address = [
                "/allowed.test/${config.networking.primaryIPAddress}"
                "/blocked.test/0.0.0.0"
              ];
              no-resolv = true;
            };
          };
          nginx = {
            enable = true;
            virtualHosts.default = {
              default = true;
              locations."/".return = "200 hello";
            };
          };
        };
      };
  };
  testScript = ''
    import json
    import shlex

    memory_report = []


    def sample_memory(label):
        meminfo = dict(
            (line.split(":")[0], int(line.split()[1]))
            for line in machine.succeed("cat /proc/meminfo").splitlines()
        )
        pressure = machine.succeed("cat /proc/pressure/memory").strip().replace("\n", " | ")
        # orig_data_size compr_data_size ...
        zram = machine.succeed("cat /sys/block/zram0/mm_stat").split()
        line = (
            f"{label}: available {meminfo['MemAvailable'] // 1024} MiB,"
            f" zram {int(zram[0]) // 2**20} MiB in {int(zram[1]) // 2**20} MiB,"
            f" pressure {pressure}"
        )
        machine.log(line)
        memory_report.append(line)


    def nothing_killed():
        machine.succeed("[ \"$(awk '/^oom_kill / { print $2 }' /proc/vmstat)\" = 0 ]")
        machine.fail("journalctl -u systemd-oomd | grep -q Killed")


    def write_state(name, data):
        machine.succeed(
            f"echo '{json.dumps(data)}' > /var/lib/zoomies/{name}.json"
        )


    def wait_for_ready(screen, user, node=machine):
        # Keys sent before the window has focus are lost, and on a slow
        # runner a lost key can land on the wrong screen; the screens mark
        # when they take input.
        node.wait_until_succeeds(
            f"kill -0 \"$(cat /run/user/$(id -u {user})/{screen}-ready)\"", timeout=120
        )


    def in_max_x(command):
        """A shell command run in Max's X session."""
        return (
            "runuser -u max -- sh -c 'export $(tr \"\\\\0\" \"\\\\n\" "
            "</proc/$(pgrep -u max -o xfce4-session)/environ"
            " | grep -E \"^(DISPLAY|XAUTHORITY|DBUS_SESSION_BUS_ADDRESS)=\"); "
            + command + "'"
        )


    def wait_for_greeter(node=machine):
        wait_for_ready("zoomies-greeter", "greeter", node)


    def restart_greeter(node=machine):
        node.succeed("systemctl restart greetd")
        wait_for_greeter(node)


    def log_out(user, node=machine):
        node.succeed(f"loginctl terminate-user {user}")
        node.wait_until_fails(f"pgrep -u {user} -f 'cage|xinit'")
        wait_for_greeter(node)


    def as_parent(command):
        return f"runuser -u parent -- {command}"


    def hours_from_now(start, end):
        hour = int(machine.succeed("date +%H"))
        return {
            "start": f"{(hour + start) % 24:02d}:00",
            "end": "24:00" if hour + end == 24 else f"{(hour + end) % 24:02d}:00",
        }


    start_all()
    server.wait_for_unit("nginx.service")
    server.wait_for_unit("dnsmasq.service")
    machine.wait_for_unit("greetd.service")
    machine.wait_for_unit("zoomies-timekeeper.service")

    with subtest("the profile picker comes up"):
        wait_for_greeter()
        machine.screenshot("greeter")
        # The test VM has no GPU: the screens draw with GTK's cheaper
        # renderer there.
        machine.succeed("test -e /run/zoomies-gpu/software")
        machine.succeed(
            "tr '\\0' '\\n' </proc/$(pgrep -u greeter -n -f zoomies-greeter)/environ"
            " | grep -qx GSK_RENDERER=cairo"
        )
        machine.succeed("swapon --show | grep -q zram")
        sample_memory("greeter")

    with subtest("a wrong PIN keeps grown-ups out"):
        machine.send_key("ctrl-alt-p")
        machine.sleep(2)
        machine.send_chars("9999\n")
        machine.sleep(5)
        machine.fail("pgrep -u parent zoomies-parent")
        machine.send_key("esc")

    with subtest("the PIN set in the configuration opens the grown-ups panel"):
        machine.succeed("zoomies-profile status | grep -q '\"pinSet\": true'")
        machine.send_key("ctrl-alt-p")
        machine.sleep(2)
        machine.send_chars("1234\n")
        machine.wait_until_succeeds("pgrep -u parent -f zoomies-parent")
        machine.sleep(3)
        machine.screenshot("parent")
        log_out("parent")

    with subtest("a kid logs in by picking the avatar"):
        machine.send_key("ret")
        wait_for_ready("zoomies-launcher", "ana")
        machine.succeed("loginctl show-user ana --property=State | grep -q active")
        machine.screenshot("launcher")

    with subtest("a game covers the launcher and quitting it goes home"):
        machine.send_key("ret")
        machine.wait_until_succeeds("pgrep -u ana -f zoomies-test-game")
        machine.succeed("pkill -u ana -f zoomies-test-game")
        machine.sleep(2)
        machine.succeed("pgrep -u ana -f zoomies-launcher")

    with subtest("a 3D game runs in 2 GiB"):
        machine.send_key("right")
        machine.sleep(1)
        machine.send_key("ret")
        machine.wait_until_succeeds("pgrep -u ana -f supertuxkart")
        machine.sleep(60)
        machine.screenshot("supertuxkart")
        machine.succeed("pgrep -u ana -f supertuxkart")
        sample_memory("SuperTuxKart")
        nothing_killed()
        machine.succeed("pkill -u ana -f supertuxkart")
        machine.wait_until_fails("pgrep -u ana -f supertuxkart")

    with subtest("little kids cannot reach the network"):
        machine.succeed("curl -sf --max-time 5 http://server/")
        machine.fail("runuser -u ana -- curl -sf --max-time 5 http://server/")

    with subtest("kids have no other group to switch to"):
        machine.succeed('[ "$(id -G ana)" = 2700 ]')
        machine.fail("timeout 10 runuser -u ana -- sg audio -c true </dev/null")
        machine.fail("grep -q '^ana:' /etc/subgid")
        machine.fail("runuser -u ana -- unshare --map-auto --map-root-user true")

    with subtest("the session ends when screen time runs out"):
        # Ana has been playing for a while; a one-minute budget is used up.
        write_state("policy", {"kids": {"ana": {"dailyMinutes": 1}}})
        machine.wait_until_fails("pgrep -u ana cage", timeout=120)
        wait_for_greeter()
        machine.screenshot("time-up")
        machine.send_key("ret")
        machine.sleep(2)
        machine.screenshot("time-up-zip")
        machine.send_key("esc")

    with subtest("PAM refuses a kid whose time is up"):
        machine.fail("greetd-try ana")
        machine.fail("zoomies-time check ana")
        machine.succeed("greetd-try ben")

    with subtest("bonus time lets the kid back in"):
        machine.succeed("zoomies-time grant ana 15")
        machine.succeed("greetd-try ana")

    with subtest("kids cannot log in outside their hours"):
        write_state("policy", {"kids": {"lia": {"hours": hours_from_now(2, 3)}}})
        machine.fail("greetd-try lia")
        machine.succeed("greetd-try ben")

    with subtest("kids limited only by hours get a countdown"):
        write_state("policy", {"kids": {"lia": {"hours": hours_from_now(-1, 1)}}})
        machine.wait_until_succeeds("zoomies-time status | grep -q '^lia: ok, [0-9].* left'")

    with subtest("zero minutes means no play, a window can end at midnight"):
        write_state("policy", {"kids": {"ben": {"dailyMinutes": 0}}})
        machine.fail("greetd-try ben")
        hour = int(machine.succeed("date +%H"))
        write_state("policy", {"kids": {"ben": {"hours": {
            "start": f"{hour:02d}:00", "end": "24:00",
        }}}})
        machine.succeed("greetd-try ben")
        write_state("policy", {})

    with subtest("grown-ups add, edit and remove kids"):
        machine.succeed(as_parent("zoomies-profile add --name Zoé --avatar 🐱 --color pink"))
        machine.succeed("id -gn zoe | grep -qx zoomies-kids")
        machine.succeed("test -d /home/zoe")
        machine.succeed("greetd-try zoe")
        machine.succeed(as_parent("zoomies-profile edit zoe --name Zoey"))
        machine.succeed("zoomies-profile list | grep -q 'Zoey'")
        machine.succeed(as_parent("zoomies-profile add --name Max --avatar 🦉 --kind older"))
        machine.succeed("id -gn max | grep -qx zoomies-older")
        machine.succeed(as_parent("zoomies-profile add --name Tom"))
        machine.succeed(as_parent("zoomies-profile remove tom"))
        machine.fail("id tom")
        machine.fail("test -e /home/tom")
        machine.fail(as_parent("zoomies-profile remove ana"))

    with subtest("only grown-ups can change profiles"):
        machine.fail("runuser -u ana -- zoomies-profile add --name Sneaky")
        # The greeter can reach the service, but changes need the PIN.
        machine.fail("runuser -u greeter -- zoomies-profile add --name Sneaky")
        machine.fail("id sneaky")

    with subtest("the PIN changes only with the current one"):
        machine.fail("printf '0000\\n5678\\n' | " + as_parent("zoomies-profile set-pin --stdin"))
        machine.fail("printf '1234\\n12\\n' | " + as_parent("zoomies-profile set-pin --stdin"))
        machine.succeed("printf '1234\\n5678\\n' | " + as_parent("zoomies-profile set-pin --stdin"))
        machine.fail("greetd-try parent 1234")
        machine.succeed("greetd-try parent 5678")

    with subtest("guessing the PIN locks the grown-ups account"):
        for _ in range(5):
            machine.fail("greetd-try parent 0000")
        machine.fail("greetd-try parent 5678")
        machine.succeed("faillock --dir /var/lib/zoomies/faillock --user parent --reset")
        machine.succeed("greetd-try parent 5678")
        # Kids cannot try it through su or polkit either.
        machine.succeed("grep -q pam_wheel.so /etc/pam.d/su")
        machine.fail("echo 5678 | timeout 10 runuser -u max -- su -c true parent")

    with subtest("an older kid gets the desktop"):
        restart_greeter()
        # Tiles: ana, ben, lia, then the kids added above.
        for _ in range(4):
            machine.send_key("right")
            machine.sleep(1)
        machine.screenshot("greeter-more-kids")
        machine.send_key("ret")
        machine.wait_until_succeeds("pgrep -u max xfce4-session", timeout=60)
        machine.sleep(10)
        machine.screenshot("older-desktop")
        machine.succeed(
            "tr -d '\\n' </home/max/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml"
            " | grep -q 'monitorVirtual-1.*older.svg'"
        )
        # The Zoomies look is set up, and the cape flaps over the wallpaper.
        machine.succeed("grep -q Andika /home/max/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml")
        machine.succeed("grep -q xfce4-panel /home/max/.config/gtk-3.0/gtk.css")
        machine.wait_until_succeeds("pgrep -u max -f zoomies-desktop-zip")
        # The cape's window lets clicks through to the desktop: a right
        # click on it opens the desktop's menu.
        cape = machine.wait_until_succeeds(in_max_x('xdotool search --name "^Zip$"')).split()[0]
        geometry = machine.succeed(in_max_x(f"xdotool getwindowgeometry --shell {cape}"))
        box = dict(line.split("=") for line in geometry.split())
        x = int(box["X"]) + int(box["WIDTH"]) // 2
        y = int(box["Y"]) + int(box["HEIGHT"]) // 2
        visible = in_max_x("xdotool search --onlyvisible --class xfdesktop | wc -l")
        windows = int(machine.succeed(visible))
        machine.succeed(in_max_x(f"xdotool mousemove {x} {y} click 3"))
        machine.wait_until_succeeds(f'[ "$({visible})" -gt {windows} ]')
        machine.succeed(in_max_x("xdotool key Escape"))
        machine.fail("pgrep -u max xfce4-screensaver")
        session = machine.succeed("pgrep -u max -o xfce4-session").strip()
        machine.fail(f"pkcheck --action-id org.freedesktop.login1.set-self-linger --process {session}")

    with subtest("Firefox and LibreOffice run together in 2 GiB"):
        sample_memory("older kids' desktop")
        machine.succeed(in_max_x("setsid firefox ${lib.escapeShellArgs pages} >/dev/null 2>&1 &"))
        machine.wait_until_succeeds(in_max_x("xdotool search --onlyvisible --class firefox"), timeout=300)
        machine.sleep(60)
        sample_memory("Firefox, 4 tabs")
        machine.succeed(in_max_x("setsid soffice --writer >/dev/null 2>&1 &"))
        machine.wait_until_succeeds(
            in_max_x("xdotool search --onlyvisible --name \"LibreOffice Writer\""), timeout=300
        )
        machine.sleep(30)
        machine.screenshot("older-apps")
        sample_memory("Firefox and Writer")
        # Switching back makes Firefox touch memory that may be in zram.
        machine.succeed(in_max_x("xdotool search --onlyvisible --class firefox windowactivate --sync"))
        machine.sleep(30)
        sample_memory("back in Firefox")
        machine.succeed("pgrep -u max -f firefox")
        machine.succeed("pgrep -u max -f soffice")
        nothing_killed()
        machine.succeed(f"printf '%s\\n' {shlex.join(memory_report)} > /tmp/memory-report.txt")
        machine.copy_from_vm("/tmp/memory-report.txt")

    with subtest("older kids are online through the family filter only"):
        machine.succeed("getent hosts blocked.test | grep -q '0.0.0.0'")
        machine.succeed("runuser -u max -- curl -sf --max-time 5 http://allowed.test/")
        machine.fail("runuser -u ana -- curl -sf --max-time 5 http://allowed.test/")
        machine.succeed("dig +time=2 +tries=1 @server allowed.test | grep -q 'ANSWER SECTION'")
        machine.fail(
            "runuser -u max -- dig +time=2 +tries=1 @server allowed.test"
            " | grep -q 'ANSWER SECTION'"
        )
        machine.fail("timeout 10 runuser -u max -- sg audio -c true </dev/null")
        machine.succeed("grep -q BlockAboutConfig /etc/firefox/policies/policies.json")

    with subtest("screen time fails closed when it cannot be saved"):
        log_out("max")
        machine.send_key("right")
        machine.sleep(1)
        machine.send_key("ret")
        wait_for_ready("zoomies-launcher", "ben")
        machine.succeed("chattr +i /var/lib/zoomies")
        machine.wait_until_fails("pgrep -u ben cage", timeout=90)
        machine.succeed("chattr -i /var/lib/zoomies")
        machine.succeed("systemctl is-active zoomies-timekeeper")
        machine.succeed("systemctl cat zoomies-reset-homes | grep -q X-RestartIfChanged=false")

    with subtest("little kids' homes are reset at boot, older kids' are kept"):
        machine.succeed(
            "runuser -u ana -- sh -c 'mkdir -p ~/.pingus ~/Downloads"
            " && touch ~/.pingus/save ~/Downloads/junk ~/junk'"
        )
        machine.succeed("runuser -u zoe -- touch /home/zoe/junk")
        machine.succeed("runuser -u max -- touch /home/max/homework.odt")
        machine.shutdown()
        machine.start()
        machine.wait_for_unit("zoomies-reset-homes.service")
        machine.succeed("test -e /home/ana/.pingus/save")
        machine.fail("test -e /home/ana/junk")
        machine.fail("test -e /home/ana/Downloads")
        machine.fail("test -e /home/zoe/junk")
        machine.succeed("test -e /home/max/homework.odt")

    with subtest("the first boot asks for a PIN, then for the kids"):
        fresh.wait_for_unit("greetd.service")
        wait_for_greeter(fresh)
        fresh.succeed("zoomies-profile status | grep -q '\"pinSet\": false'")
        fresh.fail('greetd-try parent ""')
        fresh.screenshot("wizard-pin")
        # It cannot be dismissed: nobody could log in without it.
        fresh.send_key("esc")
        fresh.sleep(1)
        fresh.send_chars("2468\n2468\n")
        fresh.wait_until_succeeds("zoomies-profile status | grep -q '\"pinSet\": true'")
        fresh.sleep(2)
        fresh.screenshot("wizard-kids")
        fresh.send_chars("Kim\n")
        fresh.wait_until_succeeds("id kim")
        fresh.sleep(2)
        fresh.send_chars("\n")
        fresh.sleep(2)
        fresh.screenshot("wizard-done")
        fresh.succeed("greetd-try kim")
        fresh.succeed("greetd-try parent 2468")

    with subtest("once set, the first-boot PIN cannot be replaced without it"):
        fresh.fail("printf '\\n1111\\n' | runuser -u greeter -- zoomies-profile set-pin --stdin")
        fresh.succeed("greetd-try parent 2468")

    with subtest("the nftables rules keep little kids offline too"):
        fresh.succeed("curl -sf --max-time 5 http://server/")
        fresh.fail("runuser -u kim -- curl -sf --max-time 5 http://server/")

    with subtest("without older kids, none can be added"):
        fresh.fail("zoomies-profile add --name Teen --kind older")
        fresh.fail("id teen")
  '';
}
