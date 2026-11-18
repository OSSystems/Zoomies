# Takes the READMEs' pictures from the real screens, once per language, so
# they can be retaken whenever a screen changes; DEVELOPMENT.md says how.
# CI leaves it out: it has nothing to fail on, and it brings every game.
{
  flake,
  lib,
  pkgs,
  ...
}:

let
  common = import ./kiosk/common.nix { inherit flake lib pkgs; };
in
pkgs.testers.runNixOSTest {
  globalTimeout = 1800;
  meta.platforms = [ "x86_64-linux" ];
  name = "zoomies-screenshots";
  nodes.machine = {
    environment.systemPackages = [ pkgs.xdotool ];
    i18n.supportedLocales = [
      "en_US.UTF-8/UTF-8"
      "es_ES.UTF-8/UTF-8"
      "pt_BR.UTF-8/UTF-8"
    ];
    imports = [
      flake.nixosModules.zoomies
      ../modules/nixos/platform/hardware.nix
    ];
    virtualisation = {
      cores = 4;
      diskSize = 8192;
      memorySize = 4096;
      qemu.options = [
        "-vga none"
        "-device virtio-vga"
      ];
    };
    zoomies = {
      enable = true;
      kids = {
        ana = {
          avatar = "🦊";
          color = "orange";
          dailyMinutes = 60;
          name = "Ana";
        };
        ben = {
          avatar = "🐼";
          color = "green";
          name = "Ben";
        };
        lia = {
          avatar = "🦄";
          color = "purple";
          name = "Lia";
        };
        max = {
          avatar = "🦉";
          kind = "older";
          name = "Max";
        };
      };
      parent.initialHashedPassword = "$y$j9T$3WW/k1HS/Ed6c6kwRa2ZP/$rNZyoGDfB9pcnRP3J/BeYYy2AjCMPPQ4CVQgZnLVdz3";
    };
  };
  testScript = common.helpers + ''
    import os

    LANGUAGES = {"en": "en_US", "pt-BR": "pt_BR", "es": "es_ES"}


    def shot(language, name):
        folder = os.path.join(machine.out_dir, language)
        os.makedirs(folder, exist_ok=True)
        machine.screenshot(os.path.join(folder, f"{name}.png"))


    machine.wait_for_unit("greetd.service")
    machine.wait_for_unit("zoomies-timekeeper.service")
    wait_for_greeter()

    for language, locale in LANGUAGES.items():
        machine.succeed(f"echo LANG={locale}.UTF-8 > /var/lib/zoomies/locale.conf")
        machine.succeed("systemctl restart zoomies-timekeeper")
        restart_greeter()
        machine.sleep(3)
        shot(language, "greeter")

        machine.send_key("ret")
        wait_for_ready("zoomies-launcher", "ana")
        machine.sleep(4)
        shot(language, "games")
        log_out("ana")

        machine.send_key("ctrl-alt-p")
        machine.sleep(2)
        machine.send_chars("1234\n")
        machine.wait_until_succeeds("pgrep -u parent -f zoomies-parent")
        machine.sleep(4)
        shot(language, "grown-ups")
        log_out("parent")

        for _ in range(3):
            machine.send_key("right")
            machine.sleep(1)
        machine.send_key("ret")
        machine.wait_until_succeeds("pgrep -u max xfce4-session", timeout=60)
        shelf = find_window("^Zoomies shelf$")
        find_window("^Zip$")
        box = window_box(shelf)
        middle = int(box["Y"]) + int(box["HEIGHT"]) // 2
        machine.succeed(in_max_x(f"xdotool mousemove 60 {middle} click 1"))
        machine.sleep(5)
        shot(language, "apps")
        log_out("max")
  '';
}
