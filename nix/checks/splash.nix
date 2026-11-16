# Records the screen from power on to the greeter and fails if it goes
# black once the splash is up: a dark screen means a handover the kids can
# see. The output keeps a video of the boot for a look at the motion.
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
  name = "zoomies-splash";
  nodes.machine = {
    # As installed: test VMs print every kernel message to the screen, and
    # any text there wakes the text console, which then shows between the
    # splash and the greeter.
    boot.consoleLogLevel = lib.mkForce 3;
    imports = [
      flake.nixosModules.zoomies
      ../modules/nixos/platform/splash.nix
    ];
    virtualisation = {
      memorySize = 2048;
      # UEFI gives Linux the firmware's framebuffer, as on real PCs, so the
      # splash starts on it and moves to the GPU driver mid-boot.
      qemu.options = [
        "-bios ${pkgs.OVMF.fd}/FV/OVMF.fd"
        "-vga none"
        "-device virtio-vga"
      ];
    };
    zoomies = {
      enable = true;
      # This node never logs in, so application closures cannot affect the
      # splash-to-greeter handover it exercises.
      games = lib.mkForce [ ];
      kids.ana.name = "Ana";
      older.apps = lib.mkForce [ ];
    };
  };
  testScript = ''
    import csv
    import os
    import shutil
    import subprocess
    import time
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image, ImageStat

    frames = os.path.join(machine.out_dir, "frames")
    os.makedirs(frames)


    start = time.monotonic()
    times = {}
    capture_ends = {}


    def record(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            name = f"{len(times):04}.png"
            times[name] = time.monotonic() - start
            machine.screenshot(os.path.join(frames, name))
            capture_ends[name] = time.monotonic() - start


    machine.start()
    # Waiting on the guest shell can block during boot; recording must keep
    # running through the handover even when the host is busy.
    with ThreadPoolExecutor(max_workers=1) as executor:
        ready = executor.submit(
            machine.wait_until_succeeds,
            'kill -0 "$(cat /run/user/$(id -u greeter)/zoomies-greeter-ready)"',
            timeout=180,
        )
        deadline = time.monotonic() + 180
        while not ready.done() and time.monotonic() < deadline:
            record(1)
        ready.result(timeout=0)
    record(6)


    def brightness(name):
        image = Image.open(os.path.join(frames, name)).convert("L")
        return ImageStat.Stat(image).mean[0]


    names = sorted(os.listdir(frames))
    levels = [brightness(name) for name in names]

    # Capture latency belongs in the evidence: a busy host can spend longer
    # saving one screenshot than the blackout we are trying to detect.
    with open(os.path.join(machine.out_dir, "brightness.csv"), "w") as timeline:
        writer = csv.writer(timeline)
        writer.writerow(["frame", "start", "end", "brightness"])
        for name, level in zip(names, levels):
            writer.writerow([name, times[name], capture_ends[name], level])

    # A video makes the handover easier to inspect than individual frames.
    with open(os.path.join(machine.out_dir, "frames.txt"), "w") as listing:
        for name, after in zip(names, names[1:] + names[-1:]):
            listing.write(f"file 'frames/{name}'\nduration {max(times[after] - times[name], 0.01):.3f}\n")
    subprocess.run(
        ["${lib.getExe pkgs.ffmpeg-headless}", "-loglevel", "error", "-f", "concat",
         "-i", "frames.txt", "-vf", "fps=30,scale=-2:540", "-pix_fmt", "yuv420p", "boot.mp4"],
        cwd=machine.out_dir,
        check=True,
    )

    # The sky is bright; the firmware and the kernel's first moments are
    # dark. The handover may briefly blank during the GPU's mode set, but
    # a visible blackout must still fail on a busy host.
    first = next(i for i, level in enumerate(levels) if level > 150)
    dark_since = None
    for name, level in zip(names[first:], levels[first:]):
        if level >= 100:
            dark_since = None
        elif dark_since is None:
            # The actual capture falls somewhere inside the screenshot call.
            # Its end and the next dark capture's start give a lower bound
            # that does not charge screenshot latency to the blackout.
            dark_since = capture_ends[name]
        else:
            duration = times[name] - dark_since
            assert duration < 0.3, (
                f"the screen went dark at {dark_since:.2f}s "
                f"for at least {duration:.2f}s ({name})"
            )
    # The recording reached the greeter, so the handover was really checked.
    assert any(150 < level < 200 for level in levels[-10:]), "the greeter never showed"

    # Failed runs keep the originals; successful runs need only the video
    # and timeline, so hundreds of PNGs do not fill the store.
    shutil.rmtree(frames)
    os.remove(os.path.join(machine.out_dir, "frames.txt"))
  '';
}
