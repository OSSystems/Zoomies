"""The kid's home screen: big game tiles, remaining time, and nothing else.

It runs as the only client of cage, so a started game covers it and quitting
the game brings the kid straight back here.
"""

import os
import pwd
import re
import shlex
import signal
import subprocess
import sys

from . import apps, state, ui
from .ui import Gio, GLib, Gtk, Pango

# Desktop entry field codes; games start without files or URLs.
FIELD_CODE = re.compile(r"%[fFuUdDnNickvm]")


def games_for(kid):
    """The games on the kid's home screen, their icons made findable."""
    theme = Gtk.IconTheme.get_for_display(ui.Gdk.Display.get_default())
    for path in apps.icon_dirs(kid["games"]):
        theme.add_search_path(path)
    return apps.entries(kid["games"])


class Launcher(Gtk.ApplicationWindow):
    def __init__(self, app, config, kid):
        super().__init__(application=app, title="Zoomies")
        self.config = config
        self.kid = kid
        self.game = None
        self.warned = False

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.add_css_class("page")

        top = Gtk.Box(spacing=20)
        top.append(ui.avatar(kid, "small"))
        hello = Gtk.Label(label=f"Hi, {kid['name']}!", xalign=0, hexpand=True)
        hello.set_ellipsize(Pango.EllipsizeMode.END)
        hello.add_css_class("title")
        top.append(hello)
        self.time_left = Gtk.Label(valign=Gtk.Align.CENTER)
        self.time_left.add_css_class("time-pill")
        top.append(self.time_left)
        top.append(ui.clock())
        page.append(top)

        self.grid = Gtk.Grid(
            row_spacing=28,
            column_spacing=28,
            # Room for the focus ring, which the scroller would clip.
            margin_top=14,
            margin_bottom=14,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            row_homogeneous=True,
            column_homogeneous=True,
        )
        games = games_for(kid)
        columns = 4 if len(games) > 6 else 3 if len(games) > 4 else max(1, len(games))
        if not games:
            empty = Gtk.Label(label="No games here yet.\nAsk a grown-up to add some!")
            empty.set_justify(Gtk.Justification.CENTER)
            empty.add_css_class("dialog-title")
            self.grid.attach(empty, 0, 0, 1, 1)
        for index, info in enumerate(games):
            self.grid.attach(self._tile(info), index % columns, index // columns, 1, 1)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=self.grid)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page.append(scroller)

        bottom = Gtk.Box(spacing=16)
        self.zip = ui.mascot(config, 88)
        bottom.append(self.zip)
        self.bubble = Gtk.Label(
            label="Pick a game!", xalign=0, hexpand=True, valign=Gtk.Align.CENTER, wrap=True
        )
        self.bubble.add_css_class("bubble")
        bottom.append(self.bubble)
        switch = ui.big_button("Switch player", "subtle", "👋")
        switch.connect(
            "clicked",
            lambda *_args: self.overlay.confirm("Stop playing and switch player?", "👋", self.leave),
        )
        bottom.append(switch)
        power = ui.big_button(None, "subtle", "⏻")
        power.connect(
            "clicked",
            lambda *_args: self.overlay.confirm(
                "Turn the computer off?", "🌙", lambda: subprocess.Popen(["systemctl", "poweroff"])
            ),
        )
        bottom.append(power)
        page.append(bottom)

        self.overlay = ui.Overlay(page, ui.sky(60, strength=0.6))
        self.set_child(self.overlay)
        self.gamepad = ui.Gamepad(
            self,
            on_back=self.overlay.close,
            on_home=self.stop_game,
            enabled=lambda: not self.running(),
        )
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)

        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)
        ui.when_ready(self, "zoomies-launcher")
        first = self.grid.get_child_at(0, 0)
        if first:
            first.grab_focus()

    def _tile(self, info):
        button = Gtk.Button()
        button.add_css_class("game-tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        image = Gtk.Image(pixel_size=128)
        icon = info.get_icon()
        theme = Gtk.IconTheme.get_for_display(ui.Gdk.Display.get_default())
        # A themed name nobody ships would show the broken-image icon.
        if icon is None or (isinstance(icon, Gio.ThemedIcon) and not theme.has_gicon(icon)):
            image.set_from_icon_name("applications-games")
        else:
            image.set_from_gicon(icon)
        box.append(image)
        name = Gtk.Label(label=info.get_name(), wrap=True, justify=Gtk.Justification.CENTER)
        name.set_max_width_chars(14)
        name.add_css_class("game-name")
        box.append(name)
        button.set_child(box)
        button.connect("clicked", lambda *_args: self.start_game(info))
        return button

    def _key(self, _controller, keyval, _code, _modifiers):
        if ui.Gdk.keyval_name(keyval) == "Escape" and self.overlay.open:
            self.overlay.close()
            return True
        return False

    def start_game(self, info):
        if self.running():
            return
        try:
            command = shlex.split(FIELD_CODE.sub("", info.get_commandline() or ""))
            command = [part.replace("%%", "%") for part in command]
            if not command:
                raise ValueError("empty command")
            # Its own process group, so the gamepad home button can stop
            # the game together with any helpers it spawned.
            self.game = subprocess.Popen(
                command, cwd=os.path.expanduser("~"), start_new_session=True
            )
        except (OSError, ValueError) as error:
            print(f"cannot start {info.get_name()}: {error}", file=sys.stderr)
            self.bubble.set_label(f"{info.get_name()} would not start. Pick another one!")
            return
        ui.play("complete")
        self.bubble.set_label(f"Starting {info.get_name()}…")
        self.zip.set_pose("fly")
        # The game soon covers the launcher; no point animating behind it.
        GLib.timeout_add_seconds(6, lambda: self.zip.set_pose("rest") or GLib.SOURCE_REMOVE)
        GLib.timeout_add(500, self._watch_game)

    def running(self):
        """The game counts as running while anything in its process group
        lives: some games start through a script that exits right away."""
        if self.game is None:
            return False
        self.game.poll()
        try:
            os.killpg(self.game.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _watch_game(self):
        if self.running():
            return GLib.SOURCE_CONTINUE
        self.game = None
        self.zip.set_pose("rest")
        self.bubble.set_label("Pick a game!")
        return GLib.SOURCE_REMOVE

    def stop_game(self):
        if not self.running():
            return
        pgid = self.game.pid
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return

        # A hung game may ignore the polite request.
        def kill():
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return GLib.SOURCE_REMOVE

        GLib.timeout_add_seconds(3, kill)

    def leave(self):
        self.stop_game()
        self.get_application().quit()

    def refresh(self):
        status = state.read_status().get(self.kid["user"])
        remaining = status and status.get("remaining")
        if remaining is None:
            self.time_left.set_visible(False)
        else:
            self.time_left.set_visible(True)
            self.time_left.set_label(f"⏳ {state.format_duration(remaining)}")
            low = remaining <= 300
            if low:
                self.time_left.add_css_class("low")
            else:
                self.time_left.remove_css_class("low")
            if low and not self.warned and self.game is None:
                self.warned = True
                self.bubble.set_label("Almost time to stop. Pick something quick!")
        return GLib.SOURCE_CONTINUE


def main():
    config = state.load_config()
    user = pwd.getpwuid(os.getuid()).pw_name
    kid = state.kids_by_user(config).get(user)
    if kid is None:
        sys.exit(f"{user} has no Zoomies profile")
    app = Gtk.Application(application_id="org.zoomies.Launcher")

    def activate(app):
        ui.load_css()
        window = Launcher(app, config, kid)
        window.fullscreen()
        window.present()

    app.connect("activate", activate)
    sys.exit(app.run(None))
