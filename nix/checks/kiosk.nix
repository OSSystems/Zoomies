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
  # qemu-system-x86_64 under KVM.
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-kiosk";
  nodes = {
    # A fresh install that skipped the installer's PIN question. It also
    # covers the nftables firewall and a system without older kids.
    fresh = {
      imports = [ common.node ];
      networking.nftables.enable = true;
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


    def set_pin(old, new):
        return f"printf '{old}\\n{new}\\n' | " + as_parent("zoomies-profile set-pin --stdin")


    def offline(node, kid):
        node.succeed("curl -sf --max-time 5 http://server/")
        node.fail(f"runuser -u {kid} -- curl -sf --max-time 5 http://server/")


    def hour():
        return int(machine.succeed("date +%H"))


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
        machine.wait_for_text("Quem vai jogar")
        machine.screenshot("greeter-pt-br")
        machine.succeed(
            "systemctl show -p EnvironmentFiles zoomies-timekeeper | grep -q /var/lib/zoomies/locale.conf"
        )
        machine.succeed("rm /var/lib/zoomies/locale.conf")
        restart_greeter()
        machine.fail(f"grep -qz LANG=pt_BR {environ}")

    with subtest("a wrong PIN keeps grown-ups out"):
        enter_pin("9999")
        machine.sleep(5)
        machine.fail("pgrep -u parent zoomies-parent")
        machine.send_key("esc")

    with subtest("the PIN set in the configuration opens the grown-ups panel"):
        machine.succeed("zoomies-profile status | grep -q '\"pinSet\": true'")
        enter_pin("1234")
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
        machine.wait_for_text("Write stories")
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

    # The two kiosk sessions never overlap, so they need not compete for RAM.
    machine.shutdown()
    fresh.start()

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
        offline(fresh, "kim")

    with subtest("without older kids, none can be added"):
        fresh.fail("zoomies-profile add --name Teen --kind older")
        fresh.fail("id teen")
  '';
}
