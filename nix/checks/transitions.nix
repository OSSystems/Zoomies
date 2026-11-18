# Films every handover the kids can see, under BIOS and UEFI, through the
# real boot menu: power on to the greeter, the greeter to a desktop, a
# grown-up restarting and a kid powering off. Each firmware's output keeps a
# video, a brightness chart with the guest's journal on the same clock,
# filmstrips of each transition and of every dark moment, and a report.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  node =
    { efi }:
    {
      boot.consoleLogLevel = lib.mkForce 3;
      boot.loader.efi.canTouchEfiVariables = false;
      boot.loader.grub = lib.mkIf efi {
        device = "nodev";
        efiInstallAsRemovable = true;
        efiSupport = true;
      };
      imports = [
        flake.nixosModules.zoomies
        ../modules/nixos/platform/boot-menu.nix
        ../modules/nixos/platform/splash.nix
      ];
      # The journal reaches the host as it is written, through the shutdown:
      # without the default dependencies the stream runs until the last
      # processes are killed. It starts once the journal is on disk, as
      # following it loses track when the journal moves there.
      systemd.services.zoomies-journal-stream = {
        after = [ "systemd-journal-flush.service" ];
        description = "Stream the journal to the test host";
        script = ''
          until [ -e /dev/virtio-ports/zoomies.events ]; do sleep 0.05; done
          exec journalctl -b -f -n all -o json \
            --output-fields=_SOURCE_MONOTONIC_TIMESTAMP,MESSAGE,SYSLOG_IDENTIFIER,UNIT,USER_UNIT,JOB_TYPE,JOB_RESULT,_TRANSPORT \
            > /dev/virtio-ports/zoomies.events
        '';
        unitConfig = {
          DefaultDependencies = false;
          IgnoreOnIsolate = true;
        };
        wantedBy = [ "sysinit.target" ];
      };
      virtualisation = {
        memorySize = 2048;
        qemu.options = [
          "-vga none"
          "-device virtio-vga"
          "-vnc unix:$TMPDIR/vnc"
          "-device virtio-serial-pci,id=zoomies-events"
          "-chardev socket,id=zoomies-events,path=$TMPDIR/events,server=on,wait=off"
          "-device virtserialport,bus=zoomies-events.0,chardev=zoomies-events,name=zoomies.events"
        ];
        useBootLoader = true;
        useEFIBoot = efi;
      };
      zoomies = {
        enable = true;
        # Nobody plays here, so games and apps would only slow the build.
        games = lib.mkForce [ ];
        kids.ana.name = "Ana";
        older.apps = lib.mkForce [ ];
        parent.initialHashedPassword = "$y$j9T$3WW/k1HS/Ed6c6kwRa2ZP/$rNZyoGDfB9pcnRP3J/BeYYy2AjCMPPQ4CVQgZnLVdz3";
      };
    };
in
pkgs.testers.runNixOSTest {
  extraPythonPackages = p: [ p.pillow ];
  globalTimeout = 1200;
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-transitions";
  nodes = {
    bios = node { efi = false; };
    uefi = node { efi = true; };
  };
  testScript = builtins.readFile ./transitions/recorder.py + ''
    from typing import Any


    def ready(node, screen, user):
        return f"kill -0 \"$(cat /run/user/$(id -u {user})/{screen}-ready)\""


    def click(node, x, y, width=1280, height=800):
        # HMP moves the mouse only relatively, and the absolute vmmouse,
        # which QEMU picks first, means nothing to cage: the tablet gets
        # absolute QMP events, scaled to its 0 to 0x7fff range.
        tablet = re.search(r"Mouse #(\d+): QEMU HID Tablet", node.send_monitor_command("info mice"))
        assert tablet
        node.send_monitor_command(f"mouse_set {tablet.group(1)}")
        events: Any = [
            {"type": "abs", "data": {"axis": "x", "value": x * 0x7FFF // (width - 1)}},
            {"type": "abs", "data": {"axis": "y", "value": y * 0x7FFF // (height - 1)}},
        ]
        assert node.qmp_client
        node.qmp_client.send("input-send-event", {"events": events})
        for down in (True, False):
            button: Any = [{"type": "btn", "data": {"down": down, "button": "left"}}]
            node.qmp_client.send("input-send-event", {"events": button})
            time.sleep(0.05)


    def answer_yes(node, rec, what):
        # The question starts on No; Yes is to its right.
        time.sleep(1.5)
        node.screenshot(f"{rec.name}-{what}-question")
        rec.mark(f"{what}: yes")
        asked = rec.now()
        node.send_key("right")
        node.send_key("ret")
        # A missed key would otherwise wait out the whole test's timeout.
        rec.wait_for_journal(r"The system will (reboot|power off) now|Reached target System Shutdown", timeout=60)
        return asked


    def film(node, name):
        rec = Recorder(node, name, "${lib.getExe pkgs.ffmpeg-headless}")
        rec.begin(allow_reboot=True)
        node.wait_until_succeeds(ready(node, "zoomies-greeter", "greeter"), timeout=180)
        rec.mark("greeter ready")
        boot = (0.0, rec.now() + 3)
        time.sleep(3)

        rec.mark("grown-up's PIN")
        pin = rec.now()
        node.send_key("ctrl-alt-p")
        time.sleep(2)
        node.send_chars("1234\n")
        node.wait_until_succeeds(ready(node, "zoomies-parent", "parent"), timeout=120)
        rec.mark("grown-ups ready")
        grown_up = (pin - 1, rec.now() + 3)
        time.sleep(2)
        # The focus starts on the Kids tab; Wi-Fi and System follow.
        node.send_key("tab")
        node.send_key("spc")
        node.send_key("tab")
        node.send_key("spc")
        time.sleep(2)
        click(node, 900, 485)
        yes = restarting = answer_yes(node, rec, "restart")
        node.connected = False
        node.wait_until_succeeds(ready(node, "zoomies-greeter", "greeter"), timeout=180)
        rec.mark("greeter ready")
        restart = (yes - 1, rec.now() + 3)
        time.sleep(3)

        rec.mark("Ana")
        ana = rec.now()
        node.send_key("ret")
        node.wait_until_succeeds(ready(node, "zoomies-launcher", "ana"), timeout=120)
        rec.mark("launcher ready")
        kid = (ana - 1, rec.now() + 3)
        time.sleep(3)
        node.screenshot(f"{name}-launcher")
        click(node, 1200, 740)
        yes = powering_off = answer_yes(node, rec, "power off")
        rec.wait_for_power_off()
        spans = rec.finish([
            ("1-power-on", *boot),
            ("2-grown-up-logs-in", *grown_up),
            ("3-restart", *restart),
            ("4-kid-logs-in", *kid),
            ("5-power-off", yes - 1, rec.now()),
        ])
        # From the question to the firmware, the screen goes from the
        # desktop to the sky to Zip landing, never through black.
        rec.assert_never_dark(spans, restarting, rec.kernel_says("reboot: Restarting system", restarting), "restarting")
        rec.assert_never_dark(spans, powering_off, rec.kernel_says("reboot: Power down", powering_off), "powering off")


    for node, name in ((uefi, "uefi"), (bios, "bios")):
        with subtest(f"film every transition under {name}"):
            film(node, name)
  '';
}
