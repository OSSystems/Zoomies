{
  flake,
  lib,
  pkgs,
  ...
}:

pkgs.testers.runNixOSTest {
  extraPythonPackages = p: [ p.pillow ];
  globalTimeout = 900;
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-preview";
  nodes.machine = {
    boot.consoleLogLevel = lib.mkForce 3;
    boot.loader.efi.canTouchEfiVariables = false;
    boot.loader.grub = {
      device = "nodev";
      efiSupport = true;
      efiInstallAsRemovable = true;
      timeoutStyle = lib.mkForce "menu";
    };
    boot.loader.timeout = lib.mkOverride 5 8;
    imports = [
      flake.nixosModules.zoomies
      ../modules/nixos/platform/splash.nix
      ../modules/nixos/platform/boot-menu.nix
    ];
    virtualisation = {
      useBootLoader = true;
      useEFIBoot = true;
      memorySize = 2048;
      qemu.options = [
        "-vga none"
        "-device virtio-vga"
      ];
    };
    zoomies = {
      enable = true;
      games = lib.mkForce [ ];
      kids.ana.name = "Ana";
      kids.ben.name = "Ben";
      older.apps = lib.mkForce [ ];
      parent.initialHashedPassword = "$y$j9T$3WW/k1HS/Ed6c6kwRa2ZP/$rNZyoGDfB9pcnRP3J/BeYYy2AjCMPPQ4CVQgZnLVdz3";
    };
  };
  testScript = ''
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor

    frames = os.path.join(machine.out_dir, "frames")
    os.makedirs(frames)
    times = []
    start = time.monotonic()
    marks = []

    def shot():
        name = os.path.join(frames, f"{len(times):05}.png")
        times.append(time.monotonic() - start)
        try:
            machine.screenshot(name)
        except Exception:
            times.pop()
            time.sleep(0.05)

    from PIL import Image, ImageStat

    def level():
        name = os.path.join(frames, sorted(os.listdir(frames))[-1])
        return ImageStat.Stat(Image.open(name).convert("L")).mean[0]

    def record_until_menu(limit=120):
        # The menu's sky is the first bright screen after the firmware's text.
        end = time.monotonic() + limit
        while time.monotonic() < end:
            shot()
            if times and level() > 120:
                return
        raise Exception("no boot menu")

    def record_until_dark(limit=60):
        end = time.monotonic() + limit
        while time.monotonic() < end:
            shot()
            if times and level() < 40:
                return

    def record_until_off(limit=60):
        # The test VM quits instead of rebooting.
        end = time.monotonic() + limit
        while time.monotonic() < end and machine.process is not None and machine.process.poll() is None:
            shot()
        machine.wait_for_shutdown()

    def record(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            shot()

    def record_while(fn, limit=180):
        with ThreadPoolExecutor(max_workers=1) as executor:
            job = executor.submit(fn)
            end = time.monotonic() + limit
            while not job.done() and time.monotonic() < end:
                shot()
            return job.result(timeout=0)

    def mark(text):
        marks.append((time.monotonic() - start, text))

    greeter = 'kill -0 "$(cat /run/user/$(id -u greeter)/zoomies-greeter-ready)"'

    machine.start()
    mark("boot menu")
    record_until_menu()
    record(3)
    mark("boot")
    record_while(lambda: machine.wait_until_succeeds(greeter, timeout=180))
    record(4)

    mark("reboot")
    machine.succeed("rm -f /run/user/*/zoomies-greeter-ready")
    machine.succeed("systemd-run --on-active=1 systemctl reboot")
    record_until_off()
    machine.start()
    record_until_menu()
    record(2)
    record_while(lambda: machine.wait_until_succeeds(greeter, timeout=180))
    record(3)

    mark("power off")
    machine.succeed("systemd-run --on-active=1 systemctl poweroff")
    record_until_off()

    with open(os.path.join(machine.out_dir, "frames.txt"), "w") as listing:
        names = sorted(os.listdir(frames))
        for i, name in enumerate(names):
            after = times[min(i + 1, len(times) - 1)]
            listing.write(f"file 'frames/{name}'\nduration {max(after - times[i], 0.01):.3f}\n")
    with open(os.path.join(machine.out_dir, "marks.txt"), "w") as f:
        for at, text in marks:
            f.write(f"{at:.2f} {text}\n")
  '';
}
