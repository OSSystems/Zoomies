# Records the screen while a kid logs in and out and fails if it goes dark:
# between two sessions nobody draws, and the kernel's console shows. The
# output keeps a video of each switch for a look at the motion.
{
  flake,
  lib,
  pkgs,
  ...
}:

pkgs.testers.runNixOSTest {
  extraPythonPackages = p: [ p.pillow ];
  # Several times a normal run: a stuck step fails the check instead of
  # holding an idle VM for the driver's default hour.
  globalTimeout = 600;
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-switch";
  nodes.machine = {
    boot = {
      consoleLogLevel = lib.mkForce 3;
      # A VM keeps the text console asleep and the splash's last frame on
      # the screen, so no switch would ever look dark; real PCs log a
      # message or two that wakes it.
      kernelParams = [ "fbcon=nodefer" ];
    };
    imports = [
      flake.nixosModules.zoomies
      ../modules/nixos/platform/splash.nix
    ];
    virtualisation = {
      memorySize = 2048;
      qemu.options = [
        "-bios ${pkgs.OVMF.fd}/FV/OVMF.fd"
        "-vga none"
        "-device virtio-vga"
      ];
    };
    zoomies = {
      enable = true;
      games = lib.mkForce [ ];
      kids.ana.name = "Ana";
      older.apps = lib.mkForce [ ];
      # Without the PIN the first boot asks for one instead of the kids.
      parent.initialHashedPassword = "$y$j9T$3WW/k1HS/Ed6c6kwRa2ZP/$rNZyoGDfB9pcnRP3J/BeYYy2AjCMPPQ4CVQgZnLVdz3";
    };
  };
  testScript = ''
    import os
    import shutil
    import subprocess
    import time
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image, ImageStat


    def ready(screen, user):
        return f'kill -0 "$(cat /run/user/$(id -u {user})/{screen}-ready)"'


    def record_until(label, condition):
        frames = os.path.join(machine.out_dir, label)
        os.makedirs(frames)
        start = time.monotonic()
        times = []

        def shot():
            name = os.path.join(frames, f"{len(times):04}.png")
            times.append(time.monotonic() - start)
            machine.screenshot(name)

        with ThreadPoolExecutor(max_workers=1) as executor:
            done = executor.submit(machine.wait_until_succeeds, condition, timeout=120)
            while not done.done():
                shot()
            done.result()
        for _ in range(10):
            shot()

        names = sorted(os.listdir(frames))
        with open(os.path.join(machine.out_dir, f"{label}.txt"), "w") as listing:
            for i, name in enumerate(names):
                after = times[min(i + 1, len(times) - 1)]
                listing.write(f"file '{label}/{name}'\nduration {max(after - times[i], 0.01):.3f}\n")
        subprocess.run(
            ["${lib.getExe pkgs.ffmpeg-headless}", "-loglevel", "error", "-f", "concat",
             "-i", f"{label}.txt", "-vf", "fps=30,scale=-2:540", "-pix_fmt", "yuv420p", f"{label}.mp4"],
            cwd=machine.out_dir,
            check=True,
        )

        # The sky is bright everywhere; the console is black.
        for name, at in zip(names, times):
            image = Image.open(os.path.join(frames, name)).convert("L")
            level = ImageStat.Stat(image).mean[0]
            assert level > 150, f"{label}: the screen went dark at {at:.2f}s ({name})"
        shutil.rmtree(frames)
        os.remove(os.path.join(machine.out_dir, f"{label}.txt"))


    machine.start()
    machine.wait_until_succeeds(ready("zoomies-greeter", "greeter"), timeout=180)
    # As on real hardware: an error message lands on the console.
    machine.succeed("echo '<3>zoomies: a hardware error' > /dev/kmsg")
    machine.wait_for_unit("zoomies-console-sky.service")

    with subtest("picking a kid never shows the console"):
        machine.send_key("ret")
        record_until("login", ready("zoomies-launcher", "ana"))

    with subtest("switching player never shows the console"):
        machine.succeed("rm /run/user/$(id -u greeter)/zoomies-greeter-ready")
        machine.succeed("pkill -u ana -f zoomies-launcher")
        record_until("logout", ready("zoomies-greeter", "greeter"))
  '';
}
