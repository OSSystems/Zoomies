{
  flake,
  lib,
  pkgs,
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
  # prompt; PAM's notes, such as a lock, get no answer, so they cannot
  # use it up.
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
    while reply["type"] == "auth_message":
        if reply["auth_message_type"] in ("info", "error"):
            response = None
        elif secret is not None:
            response, secret = secret, None
        else:
            break
        reply = send({"type": "post_auth_message_response", "response": response})
    send({"type": "cancel_session"})
    print(reply)
    sys.exit(0 if reply["type"] == "success" else 1)
  '';

  # Runs a command as a kid, in the environment the launcher gives games.
  asGame = pkgs.writeShellScript "as-game" ''
    user=$1
    shift
    # The newest match: cage and its logger name the launcher too.
    mapfile -d "" vars < "/proc/$(pgrep -u "$user" -n -f zoomies-launcher)/environ"
    exec runuser -u "$user" -- env -i "''${vars[@]}" "$@"
  '';

  # As heavy as a page of the NixOS manual, over 1 MB and 20,000 elements
  # that scripts then highlight and link; generated, so the check does not
  # need the systems to carry documentation.
  longDocument = pkgs.runCommand "long-document" { } ''
    mkdir $out
    awk 'BEGIN {
      print "<!doctype html><title>long document</title>"
      print "<style>body { font: 16px/1.5 serif; margin: 2em auto; max-width: 50em }"
      print "pre { background: #eee; padding: 1em } td { border: 1px solid #999 }</style>"
      text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
      for (s = 1; s <= 700; s++) {
        printf "<section id=\"s%d\"><h2>Section %d</h2>\n", s, s
        for (p = 1; p <= 3; p++)
          printf "<p>%s <a href=\"#s%d\">See %d</a>, <code>option.%d.%d</code> and <em>%s</em></p>\n", text, s + p, s + p, s, p, text
        print "<ul>"
        for (i = 1; i <= 5; i++) printf "<li>Item %d of section %d</li>\n", i, s
        print "</ul><table>"
        for (r = 1; r <= 4; r++) printf "<tr><td>row %d</td><td>%d</td><td>%s</td></tr>\n", r, s * r, substr(text, 1, 40)
        print "</table><pre><code>"
        for (l = 1; l <= 8; l++) printf "  services.example%d.setting%d = \"value %d\";\n", s, l, l
        print "</code></pre></section>"
      }
    }' > $out/document.html
    cat >> $out/document.html <<'EOF'
    <script>
      for (const code of document.querySelectorAll("pre code"))
        code.innerHTML = code.textContent.replace(/[\w.]+|"[^"]*"/g, (t) => `<span class="t">''${t}</span>`);
      for (const heading of document.querySelectorAll("h2")) {
        const anchor = document.createElement("a");
        anchor.href = `#''${heading.parentNode.id}`;
        anchor.textContent = "#";
        heading.append(anchor);
      }
    </script>
    EOF
  '';

  # Static documents are lighter than the sites kids use; these stand in for
  # a video or document app: a large JS heap and a page that keeps repainting.
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
    "file://${longDocument}/document.html"
    "file://${longDocument}/document.html?2"
    "file://${webApp}/app.html"
    "file://${webApp}/app.html?2"
  ];

  common = {
    environment.systemPackages = [
      greetdTry
      pkgs.curl
    ];
    imports = [
      flake.nixosModules.zoomies
      # The kernel, zram and memory tuning of a real install, not its disk layout.
      ../../modules/nixos/platform/hardware.nix
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
      games = [ game ];
      older.apps = [ pkgs.libreoffice ];
    };
  };
in
{
  inherit asGame pages;
  helpers = ''
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


    WRITER_SEARCH = in_max_x('xdotool search --onlyvisible --name "LibreOffice Writer"')


    def find_window(name):
        return machine.wait_until_succeeds(in_max_x(f'xdotool search --name "{name}"')).split()[0]


    def window_box(window):
        geometry = machine.succeed(in_max_x(f"xdotool getwindowgeometry --shell {window}"))
        return dict(line.split("=") for line in geometry.split())


    def display_size():
        return list(map(int, machine.succeed(in_max_x("xdotool getdisplaygeometry")).split()))


    def quit(user, name):
        machine.succeed(f"pkill -u {user} -f {name}")
        machine.wait_until_fails(f"pgrep -u {user} -f {name}")


    def wait_for_greeter(node=machine):
        wait_for_ready("zoomies-greeter", "greeter", node)


    def greeter_environ():
        # The ready PID identifies the greeter itself, rather than its logger or cage.
        return "/proc/$(cat /run/user/$(id -u greeter)/zoomies-greeter-ready)/environ"


    def restart_greeter(node=machine):
        node.succeed("systemctl restart greetd")
        wait_for_greeter(node)


    def log_out(user, node=machine):
        node.succeed(f"loginctl terminate-user {user}")
        node.wait_until_fails(f"pgrep -u {user} -f 'cage|xinit'")
        wait_for_greeter(node)


    def as_parent(command):
        return f"runuser -u parent -- {command}"
  '';
  machine =
    { ... }:
    {
      environment.systemPackages = [
        pkgs.dig
        pkgs.e2fsprogs
        pkgs.pam
        pkgs.xdotool
        # Started by hand, not from the launcher, which would shift the
        # tiles the other subtests pick by position.
        (import ../../modules/nixos/zoomies/games.nix { inherit lib pkgs; } pkgs.neverball)
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
        parent.initialHashedPassword = "$y$j9T$3WW/k1HS/Ed6c6kwRa2ZP/$rNZyoGDfB9pcnRP3J/BeYYy2AjCMPPQ4CVQgZnLVdz3";
      };
    };
  node = common;
}
