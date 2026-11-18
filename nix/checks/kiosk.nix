# Drives the real greeter, launcher, wizard and panel with keystrokes and
# checks the outcome from the system side, so screen time, the PIN,
# profiles, the network rules and the home reset are enforced by the OS,
# not just hidden by the UI.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  common = import ./kiosk/common.nix { inherit flake lib pkgs; };
  inherit (common) asGame;
in
pkgs.testers.runNixOSTest {
  # Reads the translated greeter off the screen.
  enableOCR = true;
  extraPythonPackages = p: [ p.pillow ];
  # Three times a normal run: a stuck step fails the check instead of
  # holding an idle VM for the driver's default hour.
  globalTimeout = 1200;
  # qemu-system-x86_64 under KVM.
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-kiosk";
  nodes = {
    # A fresh install, whose first boot asks for Wi-Fi and the PIN. It also
    # covers the nftables firewall and a system without older kids. A
    # simulated radio plays the home Wi-Fi, and a second network card the
    # cable, plugged into a network with nobody else on it.
    fresh = {
      boot = {
        extraModprobeConfig = "options mac80211_hwsim radios=2";
        kernelModules = [ "mac80211_hwsim" ];
      };
      imports = [ common.node ];
      networking = {
        # The access point hands out addresses, like a home router.
        firewall.interfaces.wlan1.allowedUDPPorts = [ 67 ];
        interfaces.wlan1.ipv4.addresses = [
          {
            address = "192.168.77.1";
            prefixLength = 24;
          }
        ];
        networkmanager = {
          enable = true;
          # The test network keeps its own addresses, and the second radio
          # is the access point's.
          unmanaged = [
            "eth0"
            "eth1"
            "wlan1"
          ];
        };
        nftables.enable = true;
        # Test VMs turn wpa_supplicant off, which NetworkManager needs for
        # Wi-Fi.
        wireless.enable = lib.mkOverride 9 true;
      };
      services.dnsmasq = {
        enable = true;
        settings = {
          bind-interfaces = true;
          dhcp-range = "192.168.77.10,192.168.77.50";
          interface = "wlan1";
          port = 0;
        };
      };
      services.hostapd = {
        enable = true;
        radios.wlan1 = {
          countryCode = "US";
          networks.wlan1 = {
            authentication = {
              mode = "wpa2-sha1";
              wpaPassword = "zoomies-home";
            };
            ssid = "Zoomies Home";
          };
        };
      };
      virtualisation.vlans = [
        1
        2
      ];
      zoomies.games = lib.mkForce [ ];
      zoomies.older.enable = false;
    };
    # Set up ahead of time: kids and the PIN (1234) in the configuration.
    machine =
      { nodes, ... }:
      {
        imports = [ common.machine ];
        zoomies.older.dnsFilter.servers = [ nodes.server.networking.primaryIPAddress ];
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
  testScript = common.helpers + ''
    import json

    from PIL import Image

    XFCONF = "/home/max/.config/xfce4/xfconf/xfce-perchannel-xml"


    def write_state(name, data):
        machine.succeed(
            f"echo '{json.dumps(data)}' > /var/lib/zoomies/{name}.json"
        )


    def enter_pin(pin):
        machine.send_key("ctrl-alt-p")
        machine.sleep(2)
        machine.send_chars(f"{pin}\n")


    def wait_for_pin_failures(count):
        machine.wait_until_succeeds(
            "[ \"$(faillock --dir /var/lib/zoomies/faillock --user parent | grep -c ' V$')\""
            f" = {count} ]"
        )


    def set_pin(old, new):
        return f"printf '{old}\\n{new}\\n' | " + as_parent("zoomies-profile set-pin --stdin")


    def offline(node, kid):
        node.succeed("curl -sf --max-time 5 http://server/")
        node.fail(f"runuser -u {kid} -- curl -sf --max-time 5 http://server/")


    def hour():
        return int(machine.succeed("date +%H"))


    def online(node, kid):
        node.wait_until_succeeds(f"runuser -u {kid} -- curl -sf --max-time 5 http://server/", timeout=60)


    def offline_now(node, kid):
        node.wait_until_fails(f"runuser -u {kid} -- curl -sf --max-time 5 http://server/", timeout=60)


    def weekday():
        return int(machine.succeed("date +%u")) - 1


    def hours_from_now(start, end):
        current = hour()
        return {
            "start": f"{(current + start) % 24:02d}:00",
            "end": "24:00" if current + end == 24 else f"{(current + end) % 24:02d}:00",
        }


    machine.start()
    server.start()
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
        machine.succeed(f"grep -qzx GSK_RENDERER=cairo {greeter_environ()}")
        machine.succeed("swapon --show | grep -q zram")

    with subtest("the screens speak the language saved at install"):
        machine.succeed(
            "printf 'LANG=pt_BR.UTF-8\\nXKB_DEFAULT_LAYOUT=br\\n' > /var/lib/zoomies/locale.conf"
        )
        restart_greeter()
        environ = greeter_environ()
        print(machine.succeed(f"grep -zE '^(LANG|LC_|XKB)' {environ} | tr '\\0' '\\n'"))
        machine.succeed(f"grep -qzx LANG=pt_BR.UTF-8 {environ}")
        machine.succeed(f"grep -qzx XKB_DEFAULT_LAYOUT=br {environ}")
        machine.wait_for_text("Quem vai jogar", timeout=60)
        machine.screenshot("greeter-pt-br")
        machine.succeed(
            "systemctl show -p EnvironmentFiles zoomies-timekeeper | grep -q /var/lib/zoomies/locale.conf"
        )
        machine.succeed("rm /var/lib/zoomies/locale.conf")
        restart_greeter()
        machine.fail(f"grep -qz LANG=pt_BR {environ}")

    with subtest("wrong PINs keep grown-ups out"):
        enter_pin("9999")
        wait_for_pin_failures(1)
        for tries in (2, 3):
            # The greeter takes no keys while PAM delays its answer.
            machine.sleep(3)
            machine.send_chars("9999\n")
            wait_for_pin_failures(tries)
        machine.sleep(3)
        machine.fail("pgrep -u parent zoomies-parent")

    with subtest("the PIN set in the configuration opens the grown-ups panel"):
        machine.succeed("zoomies-profile status | grep -q '\"pinSet\": true'")
        # Right after three wrong ones: only PAM counts them, and it
        # allows five.
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

    with subtest("Neverputt fills the screen even if it was saved windowed"):
        machine.succeed(
            "runuser -u ana -- sh -c 'mkdir -p ~/.neverball"
            " && printf \"fullscreen 0\\nwidth 800\\nheight 600\\n\" > ~/.neverball/neverballrc'"
        )
        machine.screenshot("neverputt-before")
        machine.succeed("${asGame} ana neverputt >/dev/null 2>&1 &")
        machine.wait_until_succeeds("grep -q 'Created a window' ~ana/.neverball/neverputt.log")
        machine.sleep(10)
        machine.screenshot("neverputt")
        # Drawn in a corner, the game leaves the rest of its window black,
        # or the launcher showing around a window that kept its first size.
        def corners(name):
            with Image.open(f"{machine.out_dir}/{name}.png") as shot:
                rgb = shot.convert("RGB")
                return [rgb.getpixel((rgb.width - 20, y)) for y in (20, rgb.height - 20)]

        for before, after in zip(corners("neverputt-before"), corners("neverputt")):
            assert after not in ((0, 0, 0), before), f"Neverputt leaves a corner uncovered: {after}"
        quit("ana", "neverputt")

    with subtest("little kids cannot reach the network"):
        offline(machine, "ana")

    with subtest("grown-ups let a kid online on some days or for a while"):
        every_day = {"on": True, "days": [True] * 7}
        write_state("policy", {"kids": {"ana": {"internet": every_day}}})
        online(machine, "ana")
        # A firewall reload keeps who is online.
        machine.succeed("systemctl reload firewall")
        machine.succeed("iptables -S zoomies-online | grep -q REJECT")
        online(machine, "ana")
        not_today = [day != weekday() for day in range(7)]
        write_state("policy", {"kids": {"ana": {"internet": {"on": True, "days": not_today}}}})
        offline_now(machine, "ana")
        machine.succeed("zoomies-time internet ana 30")
        online(machine, "ana")
        machine.wait_until_succeeds("zoomies-time status | grep -q '^ana: .*, online'")
        machine.succeed("zoomies-time internet ana 0")
        offline_now(machine, "ana")
        # Only while the kid may play: not after a stop for today.
        write_state("policy", {"kids": {"ana": {"internet": every_day}}})
        online(machine, "ana")
        machine.succeed("zoomies-time stop ana")
        offline_now(machine, "ana")
        machine.succeed("zoomies-time stop --undo ana")
        online(machine, "ana")
        # Whenever the timekeeper stops, however it stops, kids go offline.
        machine.succeed("systemctl stop zoomies-timekeeper")
        offline_now(machine, "ana")
        machine.succeed("systemctl start zoomies-timekeeper")
        online(machine, "ana")
        write_state("policy", {})

    with subtest("kids have no other group to switch to"):
        machine.succeed('[ "$(id -G ana)" = 2700 ]')
        machine.fail("timeout 10 runuser -u ana -- sg audio -c true </dev/null")
        machine.fail("grep -q '^ana:' /etc/subgid")
        machine.fail("runuser -u ana -- unshare --map-auto --map-root-user true")

    with subtest("the session ends when screen time runs out"):
        # Prove real accounting before seeding a full minute; expiry must
        # not depend on how long the functional scenarios happen to take.
        machine.wait_until_succeeds("grep -Eq '\"ana\": [1-9]' /var/lib/zoomies/usage.json")
        machine.succeed("systemctl stop zoomies-timekeeper")
        usage = json.loads(machine.succeed("cat /var/lib/zoomies/usage.json"))
        assert usage["seconds"]["ana"] > 0, usage
        usage["seconds"]["ana"] = max(60, usage["seconds"]["ana"])
        write_state("usage", usage)
        machine.succeed("systemctl start zoomies-timekeeper")
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
        write_state("policy", {"kids": {"ben": {"hours": {
            "start": f"{hour():02d}:00", "end": "24:00",
        }}}})
        machine.succeed("greetd-try ben")
        write_state("policy", {})

    with subtest("the week decides who plays: days off, special days, stop for today"):
        today = weekday()
        all_day = {"blocks": [["00:00", "24:00"]], "minutes": None}
        week = [None if day == today else all_day for day in range(7)]
        write_state("policy", {"kids": {"lia": {"schedule": {"days": week}}}})
        machine.fail("greetd-try lia")
        machine.wait_until_succeeds("zoomies-time status | grep -q '^lia: day, .*opens in 1 days at 00:00'")
        # A special day today plays like tomorrow.
        date = machine.succeed("date +%F").strip()
        special = {date: (today + 1) % 7}
        write_state("policy", {"kids": {"lia": {"schedule": {"days": week}, "special": special}}})
        machine.succeed("greetd-try lia")
        machine.succeed("zoomies-time stop lia")
        machine.fail("greetd-try lia")
        machine.succeed("zoomies-time stop --undo lia")
        machine.succeed("greetd-try lia")
        # Rules a grown-up broke by hand keep the kid out, they do not
        # let them play without limits.
        write_state("policy", {"kids": {"lia": {"schedule": {"days": [all_day]}}}})
        machine.fail("greetd-try lia")
        write_state("policy", {})
        machine.succeed("greetd-try lia")

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
        machine.fail(set_pin("0000", "5678"))
        machine.fail(set_pin("1234", "12"))
        machine.succeed(set_pin("1234", "5678"))
        machine.fail("greetd-try parent 1234")
        machine.succeed("greetd-try parent 5678")

    with subtest("guessing the PIN locks the grown-ups account"):
        enter_pin("0000")
        wait_for_pin_failures(1)
        for tries in range(2, 6):
            machine.sleep(3)
            machine.send_chars("0000\n")
            wait_for_pin_failures(tries)
        # Told on the very try that locked it, not "wrong PIN".
        machine.wait_for_text("Too many tries", timeout=60)
        machine.screenshot("pin-locked")
        machine.sleep(3)
        machine.send_chars("5678\n")
        machine.sleep(5)
        machine.fail("pgrep -u parent zoomies-parent")
        machine.fail("greetd-try parent 5678")
        # Asking whether it is locked neither adds a try nor lifts the lock.
        for _ in range(3):
            machine.fail("${lib.getExe pkgs.pamtester} zoomies-pin-lock parent authenticate")
        wait_for_pin_failures(5)
        machine.send_key("esc")
        machine.succeed("faillock --dir /var/lib/zoomies/faillock --user parent --reset")
        machine.succeed("greetd-try parent 5678")
        # The question ends in pam_permit, so it must not be a way in for
        # anyone but root.
        machine.succeed("${lib.getExe pkgs.pamtester} zoomies-pin-lock parent authenticate")
        machine.fail("runuser -u ana -- ${lib.getExe pkgs.pamtester} zoomies-pin-lock parent authenticate")
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
        find_window("^Zoomies shelf$")
        find_window("^Zip$")
        machine.screenshot("older-desktop")
        machine.succeed(
            f"tr -d '\\n' <{XFCONF}/xfce4-desktop.xml"
            " | grep -q 'monitorVirtual-1.*older.svg'"
        )
        # The Zoomies look is set up, and the wallpaper comes alive.
        machine.succeed(f"grep -q Andika {XFCONF}/xsettings.xml")
        # The shelf stands in for the grown-ups' panel.
        machine.wait_until_succeeds("pgrep -u max -f zoomies-shelf")
        machine.fail("pgrep -u max xfce4-panel")
        machine.wait_until_succeeds("pgrep -u max -f zoomies-desktop-zip")
        # Clouds drift over the whole desktop, with no icons on top.
        machine.succeed(
            f"tr -d '\\n' <{XFCONF}/xfce4-desktop.xml"
            " | grep -q 'desktop-icons.*name=\"style\" type=\"int\" value=\"0\"'"
        )
        # The live wallpaper lets clicks through to the desktop: a right
        # click on it opens the desktop's menu.
        cape = find_window("^Zip$")
        box = window_box(cape)
        screen = display_size()
        assert [int(box["WIDTH"]), int(box["HEIGHT"])] == screen, f"the sky covers {box}, not {screen}"
        # Old PCs draw without a GPU: only what moves is redrawn.
        helper = machine.succeed("pgrep -u max -o -f zoomies-desktop-zip").strip()
        ticks = "awk '{ print $14 + $15 }' /proc/" + helper + "/stat"
        before = int(machine.succeed(ticks))
        machine.sleep(10)
        busy = (int(machine.succeed(ticks)) - before) / int(machine.succeed("getconf CLK_TCK")) / 10
        assert busy < 0.15, f"the live wallpaper keeps {busy:.0%} of a core busy"
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

    with subtest("a calm screen keeps the cape still"):
        policy = json.loads(machine.succeed("cat /var/lib/zoomies/policy.json"))
        write_state("policy", {**policy, "calm": True})
        # Without a calm screen the cape keeps flapping until killed.
        machine.succeed(in_max_x("timeout 10 zoomies-desktop-zip /dev/null"))
        write_state("policy", policy)

    with subtest("the shelf keeps apps full screen and offers the apps"):
        machine.succeed(in_max_x("setsid soffice --writer >/dev/null 2>&1 &"))
        machine.wait_until_succeeds(WRITER_SEARCH, timeout=300)
        shelf = find_window("^Zoomies shelf$")
        box = window_box(shelf)
        screen_width, screen_height = display_size()
        top = int(box["Y"])
        assert top + int(box["HEIGHT"]) == screen_height, f"the shelf sits at {box}"
        writer = machine.succeed(WRITER_SEARCH).split()[0]

        # Writer maps its window before the shelf has maximized it.
        machine.wait_until_succeeds(
            in_max_x(f"[ \"$(xdotool getwindowgeometry --shell {writer} | grep WIDTH)\" = WIDTH={screen_width} ]")
        )
        app = window_box(writer)
        assert int(app["WIDTH"]) == screen_width, f"Writer is {app}"
        assert int(app["Y"]) > 0, f"Writer has no title strip: {app}"
        assert int(app["Y"]) + int(app["HEIGHT"]) <= top, f"Writer runs under the shelf: {app}"
        # Shrinking or minimizing an app does not stick.
        machine.succeed(in_max_x(f"xdotool windowsize {writer} 400 300"))
        machine.wait_until_succeeds(
            in_max_x(f"[ \"$(xdotool getwindowgeometry --shell {writer} | grep WIDTH)\" = WIDTH={screen_width} ]")
        )
        machine.succeed(in_max_x(f"xdotool windowminimize {writer}"))
        machine.wait_until_succeeds(WRITER_SEARCH)
        machine.succeed(in_max_x(f"xdotool windowactivate --sync {writer}"))
        machine.sleep(2)
        machine.screenshot("older-shelf")
        # The Apps button opens the card of apps and games; Escape closes it.
        machine.succeed(in_max_x(f"xdotool mousemove 60 {top + int(box['HEIGHT']) // 2} click 1"))
        machine.wait_until_succeeds(in_max_x('xdotool search --onlyvisible --name "^Apps$"'))
        machine.sleep(2)
        # Tiles say what an app is for in a kid's words, not "Word Processor".
        machine.wait_for_text("Write stories", timeout=60)
        machine.screenshot("older-apps-card")
        machine.succeed(in_max_x("xdotool key Escape"))
        machine.wait_until_fails(in_max_x('xdotool search --onlyvisible --name "^Apps$"'))

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

    with subtest("grown-ups can take older kids offline"):
        policy = json.loads(machine.succeed("cat /var/lib/zoomies/policy.json"))
        off = {"on": False, "days": [True] * 7}
        write_state("policy", {**policy, "kids": {"max": {"internet": off}}})
        offline_now(machine, "max")
        write_state("policy", policy)
        online(machine, "max")

    with subtest("rules that cannot be read end a running session"):
        log_out("max")
        policy = machine.succeed("cat /var/lib/zoomies/policy.json")
        for broken in ('{"kids": {"ben": {"schedule": []}}}', "{broken"):
            machine.send_key("right")
            machine.sleep(1)
            machine.send_key("ret")
            wait_for_ready("zoomies-launcher", "ben")
            machine.succeed(f"echo '{broken}' > /var/lib/zoomies/policy.json")
            machine.wait_until_fails("pgrep -u ben cage", timeout=60)
            machine.fail("greetd-try ben")
            machine.succeed(f"echo '{policy.strip()}' > /var/lib/zoomies/policy.json")
            wait_for_greeter()
            # The greeter would send a kid still marked as resting outside.
            machine.wait_until_succeeds("zoomies-time status | grep -q '^ben: ok'")

    with subtest("screen time fails closed when it cannot be saved"):
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

    # The two kiosk sessions never overlap, so they need not compete for RAM.
    machine.shutdown()
    fresh.start()

    with subtest("the first boot offers Wi-Fi before any PIN exists"):
        fresh.wait_for_unit("greetd.service")
        fresh.wait_for_unit("hostapd.service")
        wait_for_greeter(fresh)
        fresh.wait_for_text("online first", timeout=90)
        # Only the greeter and the grown-up reach the admin service.
        fresh.fail("runuser -u nobody -- zoomies-profile wifi scan")
        fresh.wait_until_succeeds(
            "runuser -u greeter -- zoomies-profile wifi scan | grep -q 'Zoomies Home'", timeout=90
        )
        scan = json.loads(fresh.succeed("runuser -u greeter -- zoomies-profile wifi scan"))
        assert any(n["ssid"] == "Zoomies Home" and n["secure"] for n in scan["networks"]), scan
        # The list looks again by itself while it finds nothing.
        fresh.wait_for_text("Zoomies Home", timeout=90)
        fresh.screenshot("wizard-wifi")
        # A wrong password fails and is not kept to be retried at every boot.
        wrong = fresh.execute(
            "printf 'not-the-password\\n' | runuser -u greeter --"
            " zoomies-profile wifi connect 'Zoomies Home' --password-stdin 2>&1"
        )
        assert wrong[0] != 0 and "check the password" in wrong[1], wrong
        fresh.fail("nmcli -t -f NAME connection show | grep -qx 'Zoomies Home'")
        fresh.succeed(
            "printf 'zoomies-home\\n' | runuser -u greeter --"
            " zoomies-profile wifi connect 'Zoomies Home' --password-stdin"
        )
        fresh.succeed("nmcli -t -f GENERAL.STATE device show wlan0 | grep -q '(connected)'")
        # Saved for the whole computer, with the password out of any
        # keyring, so it comes back at every boot for everyone.
        fresh.succeed("[ -z \"$(nmcli -g connection.permissions connection show 'Zoomies Home')\" ]")
        fresh.succeed("[ \"$(nmcli -g 802-11-wireless-security.psk-flags connection show 'Zoomies Home')\" = 0 ]")

    with subtest("the first boot asks for a PIN, then for the kids"):
        fresh.succeed("zoomies-profile status | grep -q '\"pinSet\": false'")
        fresh.fail('greetd-try parent ""')
        # Skip has the focus on the Wi-Fi step.
        fresh.send_key("ret")
        fresh.wait_for_text("secret PIN", timeout=60)
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

    with subtest("once a PIN exists, Wi-Fi changes need it"):
        fresh.fail("runuser -u greeter -- zoomies-profile wifi scan")
        fresh.fail("printf '1111\\n' | runuser -u greeter -- zoomies-profile wifi scan --pin-stdin")
        fresh.succeed("printf '2468\\n' | runuser -u greeter -- zoomies-profile wifi scan --pin-stdin")
        fresh.succeed(as_parent("zoomies-profile wifi status") + " | grep -q '\"connected\": \"Zoomies Home\"'")

    with subtest("the grown-ups panel shows the week, the internet and Wi-Fi"):
        date = fresh.succeed("date -d '+3 days' +%F").strip()
        school = {"blocks": [["07:00", "07:30"], ["17:00", "19:30"]], "minutes": 60}
        weekend = {"blocks": [["09:00", "12:00"], ["14:00", "20:00"]], "minutes": 180}
        fresh.succeed(
            "echo '" + json.dumps({"kids": {"kim": {
                "schedule": {"days": [school] * 5 + [weekend, None]},
                "internet": {"on": True, "days": [False] * 4 + [True] * 3},
                "special": {date: "off"},
            }}}) + "' > /var/lib/zoomies/policy.json"
        )
        fresh.send_key("ctrl-alt-p")
        fresh.sleep(2)
        fresh.send_chars("2468\n")
        wait_for_ready("zoomies-parent", "parent", fresh)
        fresh.wait_for_text("Max a day", timeout=60)
        fresh.screenshot("parent-week")
        # The focus starts on the Kids tab; Wi-Fi and System follow.
        fresh.send_key("tab")
        fresh.send_key("spc")
        fresh.wait_for_text("Zoomies Home", timeout=90)
        fresh.screenshot("parent-wifi")
        fresh.send_key("tab")
        fresh.send_key("spc")
        fresh.wait_for_text("Calm screen", timeout=60)
        fresh.screenshot("parent-system")
        fresh.send_key("shift-tab")
        fresh.send_key("shift-tab")
        fresh.send_key("spc")
        fresh.wait_for_text("Max a day", timeout=60)
        # Past Wi-Fi, System, Kim's chip, Add a kid, +15 min, Stop, Edit,
        # Remove and the Week tab.
        for _ in range(10):
            fresh.send_key("tab")
        fresh.send_key("spc")
        fresh.wait_for_text("Online during play time", timeout=30)
        fresh.screenshot("parent-internet")
        fresh.send_key("tab")
        fresh.send_key("spc")
        fresh.wait_for_text("No play", timeout=30)
        fresh.screenshot("parent-special-days")
        log_out("parent", fresh)

    with subtest("the cable and a Wi-Fi network take a fixed address"):
        def method_of(device):
            """A shell command that prints how a device's connection gets
            its address."""
            name = f"$(nmcli -g GENERAL.CONNECTION device show {device})"
            return f'nmcli -g ipv4.method connection show "{name}"'

        def method(device):
            return fresh.succeed(method_of(device)).strip()

        # The cable's network has no router, so a fixed address is its way in.
        fresh.succeed(as_parent("zoomies-profile address --fixed 10.9.8.7 --dns 10.9.8.1"))
        fresh.wait_until_succeeds("ip -4 addr show eth2 | grep -q 'inet 10.9.8.7/24'", timeout=60)
        assert method("eth2") == "manual", method("eth2")
        cable = json.loads(fresh.succeed(as_parent("zoomies-profile address")))
        assert cable["fixed"] and cable["now"]["address"] == "10.9.8.7", cable
        # Kids cannot change it; the greeter only with the PIN.
        fresh.fail("runuser -u kim -- zoomies-profile address --auto")
        fresh.fail("runuser -u greeter -- zoomies-profile address --auto")
        # Mistakes are refused before NetworkManager sees them.
        wrong = fresh.execute(
            as_parent("zoomies-profile address --fixed 10.9.8.7 --gateway 10.1.1.1 2>&1")
        )
        assert wrong[0] != 0 and "same network" in wrong[1], wrong

        fresh.succeed(
            as_parent(
                "zoomies-profile address 'Zoomies Home' --fixed 192.168.77.60 --gateway 192.168.77.1"
            )
        )
        fresh.wait_until_succeeds("ip -4 addr show wlan0 | grep -q 'inet 192.168.77.60/24'", timeout=60)
        fresh.succeed("ping -c1 -W5 192.168.77.1")
        fresh.succeed(as_parent("zoomies-profile address 'Zoomies Home' --auto"))
        fresh.wait_until_succeeds(
            "ip -4 addr show wlan0 | grep -q 'inet 192.168.77.[1-5][0-9]/24'", timeout=60
        )
        assert method("wlan0") == "auto", method("wlan0")

    with subtest("a template replaces the week and the internet days, not special days"):
        fresh.send_key("ctrl-alt-p")
        fresh.sleep(2)
        fresh.send_chars("2468\n")
        wait_for_ready("zoomies-parent", "parent", fresh)
        fresh.wait_for_text("Max a day", timeout=60)
        # From the Kids tab: Wi-Fi, System, Kim's chip, Add a kid, then
        # Kim's +15 min, Stop, Edit, Remove and the three tabs of the card
        # come before the week's template button.
        for _ in range(12):
            fresh.send_key("tab")
        fresh.send_key("spc")
        fresh.wait_for_text("week for Kim", timeout=60)
        # The first template has the focus.
        fresh.send_key("spc")
        fresh.wait_for_text("Use School week", timeout=30)
        fresh.screenshot("parent-templates")
        # Past the four other templates and Cancel.
        for _ in range(6):
            fresh.send_key("tab")
        fresh.send_key("spc")
        fresh.wait_until_succeeds("grep -q '\"19:00\"' /var/lib/zoomies/policy.json", timeout=30)
        kim = json.loads(fresh.succeed("cat /var/lib/zoomies/policy.json"))["kids"]["kim"]
        school = {"blocks": [["17:00", "19:00"]], "minutes": 60}
        weekend = {"blocks": [["09:00", "12:00"], ["15:00", "19:00"]], "minutes": 120}
        assert kim["schedule"]["days"] == [school] * 5 + [weekend] * 2, kim
        assert kim["internet"] == {"on": True, "days": [False] * 5 + [True] * 2}, kim
        assert kim["special"] == {date: "off"}, kim
        fresh.wait_for_text("Start from a template", timeout=30)
        fresh.screenshot("parent-template-applied")
        log_out("parent", fresh)

    with subtest("once set, the first-boot PIN cannot be replaced without it"):
        fresh.fail("printf '\\n1111\\n' | runuser -u greeter -- zoomies-profile set-pin --stdin")
        fresh.succeed("greetd-try parent 2468")

    with subtest("the nftables rules keep little kids offline too"):
        offline(fresh, "kim")

    with subtest("with nftables, kids online drop out unless renewed"):
        fresh.succeed(
            "echo '" + json.dumps({"kids": {"kim": {"internet": {"on": True, "days": [True] * 7}}}})
            + "' > /var/lib/zoomies/policy.json"
        )
        online(fresh, "kim")
        fresh.succeed("nft list set inet zoomies online | grep -q 'expires'")
        fresh.succeed("systemctl stop zoomies-timekeeper")
        offline_now(fresh, "kim")
        fresh.succeed("systemctl start zoomies-timekeeper")
        online(fresh, "kim")

    with subtest("without older kids, none can be added"):
        fresh.fail("zoomies-profile add --name Teen --kind older")
        fresh.fail("id teen")
  '';
}
