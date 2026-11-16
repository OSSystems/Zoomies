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
      kids.ana.name = "Ana";
    };
  };
  testScript = ''
    import os
    import shutil
    import subprocess
    import time

    from PIL import Image, ImageStat

    frames = os.path.join(machine.out_dir, "frames")
    os.makedirs(frames)


    start = time.monotonic()
    times = {}


    def record(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            name = f"{len(os.listdir(frames)):04}.png"
            times[name] = time.monotonic() - start
            machine.screenshot(os.path.join(frames, name))


    machine.start()
    record(40)
    machine.wait_for_unit("greetd.service")
    machine.wait_until_succeeds("pgrep -f zoomies-greeter")
    record(6)


    def brightness(name):
        image = Image.open(os.path.join(frames, name)).convert("L")
        return ImageStat.Stat(image).mean[0]


    names = sorted(os.listdir(frames))
    levels = [brightness(name) for name in names]

    # A video of the boot to look at; the frames would fill the store.
    with open(os.path.join(machine.out_dir, "frames.txt"), "w") as listing:
        for name, after in zip(names, names[1:] + names[-1:]):
            listing.write(f"file 'frames/{name}'\nduration {max(times[after] - times[name], 0.01):.3f}\n")
    subprocess.run(
        ["${lib.getExe pkgs.ffmpeg-headless}", "-loglevel", "error", "-f", "concat",
         "-i", "frames.txt", "-vf", "fps=30,scale=-2:540", "-pix_fmt", "yuv420p", "boot.mp4"],
        cwd=machine.out_dir,
        check=True,
    )
    shutil.rmtree(frames)
    os.remove(os.path.join(machine.out_dir, "frames.txt"))

    # The sky is bright; the firmware and the kernel's first moments are
    # dark. After that, only the GPU's mode set as cage takes the screen may
    # blank it, for a frame or two.
    first = next(i for i, level in enumerate(levels) if level > 150)
    dark_since = None
    for name, level in zip(names[first:], levels[first:]):
        if level >= 100:
            dark_since = None
        elif dark_since is None:
            dark_since = times[name]
        else:
            assert times[name] - dark_since < 0.3, f"the screen went dark at {dark_since:.2f}s"
    # The recording reached the greeter, so the handover was really checked.
    assert any(150 < level < 200 for level in levels[-10:]), "the greeter never showed"
  '';
}
