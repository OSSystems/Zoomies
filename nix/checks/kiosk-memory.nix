# Keep the full settling periods under the minimum supported RAM: software
# rendering and zram must not hide an app being killed under memory pressure.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  common = import ./kiosk/common.nix { inherit flake lib pkgs; };
  inherit (common) pages;
in
pkgs.testers.runNixOSTest {
  # Three times a normal run: a stuck step fails the check instead of
  # holding an idle VM for the driver's default hour.
  globalTimeout = 720;
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-kiosk-memory";
  nodes.machine = {
    imports = [ common.machine ];
    zoomies.games = [ pkgs.supertuxkart ];
  };
  testScript = common.helpers + ''
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


    machine.start()
    machine.wait_for_unit("greetd.service")
    machine.wait_for_unit("zoomies-timekeeper.service")
    wait_for_greeter()
    machine.succeed("swapon --show | grep -q zram")
    sample_memory("greeter")
    machine.send_key("ret")
    wait_for_ready("zoomies-launcher", "ana")

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
        quit("ana", "supertuxkart")

    log_out("ana")
    machine.succeed(as_parent("zoomies-profile add --name Max --avatar 🦉 --kind older"))
    restart_greeter()
    for _ in range(3):
        machine.send_key("right")
    machine.send_key("ret")
    machine.wait_until_succeeds("pgrep -u max xfce4-session", timeout=60)
    find_window("^Zoomies shelf$")
    find_window("^Zip$")

    with subtest("Firefox and LibreOffice run together in 2 GiB"):
        sample_memory("older kids' desktop")
        machine.succeed(in_max_x("setsid firefox ${lib.escapeShellArgs pages} >/dev/null 2>&1 &"))
        machine.wait_until_succeeds(in_max_x("xdotool search --onlyvisible --class firefox"), timeout=300)
        machine.sleep(60)
        sample_memory("Firefox, 4 tabs")
        machine.succeed(in_max_x("setsid soffice --writer >/dev/null 2>&1 &"))
        machine.wait_until_succeeds(WRITER_SEARCH, timeout=300)
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

  '';
}
