"""Profile picker: the greetd greeter for Zoomies.

Kids pick their avatar and go straight in (PAM lets the kids group through
without a password). The parent tile needs a long press, then the parent
account's password typed on a PIN pad, so the PIN is never part of the image.
"""

import json
import os
import socket
import struct
import subprocess
import sys
import time

from . import state, ui
from .ui import GLib, Gtk

PIN_ATTEMPTS = 3
PIN_LOCKOUT = 30


class Greetd:
    def __init__(self):
        self.path = os.environ.get("GREETD_SOCK")

    @staticmethod
    def _read(sock, size):
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("greetd closed the connection")
            data += chunk
        return data

    def login(self, user, command, secret=None):
        """Return None on success or a short reason on failure."""
        if self.path is None:
            print(f"(no greetd) would start {command} for {user}", file=sys.stderr)
            return None
        try:
            return self._login(user, command, secret)
        except (OSError, ValueError, KeyError, struct.error) as error:
            print(f"greetd: {error!r}", file=sys.stderr)
            return "error"

    def _login(self, user, command, secret):
        # greetd keeps one pending session per connection across requests,
        # so every request reuses the same socket.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(self.path)

            def send(payload):
                data = json.dumps(payload).encode()
                sock.sendall(struct.pack("=I", len(data)) + data)
                size = struct.unpack("=I", self._read(sock, 4))[0]
                return json.loads(self._read(sock, size))

            reply = send({"type": "create_session", "username": user})
            while reply["type"] == "auth_message":
                if reply["auth_message_type"] == "secret" and secret is not None:
                    response = secret
                    secret = None
                elif reply["auth_message_type"] in ("info", "error"):
                    response = None
                else:
                    send({"type": "cancel_session"})
                    return "auth"
                reply = send({"type": "post_auth_message_response", "response": response})
            if reply["type"] == "error":
                send({"type": "cancel_session"})
                return reply.get("error_type", "error")
            reply = send(
                {
                    "type": "start_session",
                    "cmd": [command],
                    "env": ["XDG_SESSION_TYPE=wayland", "XDG_CURRENT_DESKTOP=Zoomies"],
                }
            )
            if reply["type"] == "error":
                send({"type": "cancel_session"})
                return reply.get("error_type", "error")
            return None


def describe(status):
    if not status:
        return "Let's play!"
    if not status["allowed"]:
        if status["reason"] == "hours":
            return f"Back at {status['opensAt']}"
        return "All done for today"
    if status["remaining"] is None:
        return "Let's play!"
    return f"{state.format_duration(status['remaining'])} to play"


class Greeter(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title="Zoomies")
        self.config = config
        self.greetd = Greetd()
        self.tiles = {}
        self.failures = 0
        self.locked_until = 0

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page.add_css_class("page")

        top = Gtk.CenterBox()
        top.set_start_widget(ui.mascot(config, 120))
        title = Gtk.Label(label="Who's playing?")
        title.add_css_class("title")
        top.set_center_widget(title)
        top.set_end_widget(ui.clock())
        page.append(top)

        kids = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=4,
            min_children_per_line=1,
            column_spacing=32,
            row_spacing=32,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            vexpand=True,
        )
        for kid in config["kids"]:
            tile = self._kid_tile(kid)
            kids.append(tile)
            tile.get_parent().set_focusable(False)
        page.append(kids)

        bottom = Gtk.Box(spacing=16)
        parent = ui.big_button("Grown-ups", "subtle", "🔒")
        hold = Gtk.GestureLongPress(delay_factor=3.0)
        hold.connect("pressed", lambda *_: self.ask_pin())
        parent.add_controller(hold)
        # A tap does nothing on purpose, so tell grown-ups what to do;
        # tooltips never show on touch screens.
        parent.connect("clicked", lambda *_: self.hint("Keep holding 🔒 to open"))
        bottom.append(parent)
        self.hint_label = Gtk.Label(hexpand=True, xalign=0)
        self.hint_label.add_css_class("kid-note")
        bottom.append(self.hint_label)
        power = ui.big_button(None, "subtle", "⏻")
        power.connect(
            "clicked",
            lambda *_: self.overlay.confirm(
                "Turn the computer off?", "🌙", lambda: subprocess.Popen(["systemctl", "poweroff"])
            ),
        )
        bottom.append(power)
        page.append(bottom)

        self.overlay = ui.Overlay(page)
        self.set_child(self.overlay)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.gamepad = ui.Gamepad(self, on_back=self.overlay.close)

        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)
        first = next(iter(self.tiles.values()), None)
        if first:
            first.grab_focus()

    def _kid_tile(self, kid):
        button = Gtk.Button()
        button.add_css_class("kid-tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(ui.avatar(kid))
        name = Gtk.Label(label=kid["name"])
        name.add_css_class("kid-name")
        box.append(name)
        note = Gtk.Label()
        note.add_css_class("kid-note")
        box.append(note)
        button.set_child(box)
        button.note = note
        button.connect("clicked", lambda *_: self.play(kid))
        self.tiles[kid["user"]] = button
        return button

    def refresh(self):
        statuses = state.read_status()
        for user, tile in self.tiles.items():
            status = statuses.get(user)
            tile.note.set_label(describe(status))
            if status and not status["allowed"]:
                tile.add_css_class("resting")
            else:
                tile.remove_css_class("resting")
        return GLib.SOURCE_CONTINUE

    def _key(self, _controller, keyval, _code, modifiers):
        name = ui.Gdk.keyval_name(keyval)
        ctrl_alt = ui.Gdk.ModifierType.CONTROL_MASK | ui.Gdk.ModifierType.ALT_MASK
        if name in ("p", "P") and modifiers & ctrl_alt == ctrl_alt:
            self.ask_pin()
            return True
        if name == "Escape" and self.overlay.open:
            self.overlay.close()
            return True
        return False

    def play(self, kid):
        status = state.read_status().get(kid["user"])
        if status and not status["allowed"]:
            self.say(kid["avatar"], f"{describe(status)}, {kid['name']}!\nZip says: go run around outside!")
            return
        ui.play("service-login")
        error = self.greetd.login(kid["user"], self.config["kidSession"])
        if error is None:
            self.get_application().quit()
            return
        # PAM may know better than the last status the timekeeper wrote,
        # for example right as the allowed hours end.
        status = state.kid_status(kid, state.load_policy(), state.load_usage())
        if not status["allowed"]:
            self.say(kid["avatar"], f"{describe(status)}, {kid['name']}!\nZip says: go run around outside!")
            self.refresh()
        else:
            self.say("🙈", "Oops, that did not work.\nAsk a grown-up for help.")

    def say(self, emoji, text):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        label = Gtk.Label(label=f"{emoji}\n{text}", justify=Gtk.Justification.CENTER)
        label.add_css_class("dialog-title")
        box.append(label)
        ok = ui.big_button("OK", "yes", "👍")
        ok.set_halign(Gtk.Align.CENTER)
        ok.connect("clicked", lambda *_: self.overlay.close())
        box.append(ok)
        self.overlay.show(box)
        ok.grab_focus()

    def ask_pin(self):
        parent = self.config.get("parent")
        if not parent or self.overlay.open:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        title = Gtk.Label(label="🔒\nGrown-ups only")
        title.set_justify(Gtk.Justification.CENTER)
        title.add_css_class("dialog-title")
        box.append(title)
        entry = Gtk.PasswordEntry()
        entry.add_css_class("pin")
        entry.set_halign(Gtk.Align.CENTER)
        box.append(entry)
        message = Gtk.Label()
        message.add_css_class("pin-message")
        box.append(message)

        pad = Gtk.Grid(row_spacing=10, column_spacing=10, halign=Gtk.Align.CENTER)
        for index, key in enumerate("123456789⌫0✔"):
            button = Gtk.Button(label=key)
            button.add_css_class("pin-key")
            if key == "⌫":
                button.connect("clicked", lambda *_: entry.set_text(entry.get_text()[:-1]))
            elif key == "✔":
                button.add_css_class("yes")
                button.connect("clicked", lambda *_: submit())
            else:
                button.connect("clicked", lambda _b, k=key: entry.set_text(entry.get_text() + k))
            pad.attach(button, index % 3, index // 3, 1, 1)
        box.append(pad)
        cancel = ui.big_button("Cancel", "no", "✖")
        cancel.set_halign(Gtk.Align.CENTER)
        cancel.connect("clicked", lambda *_: self.overlay.close())
        box.append(cancel)

        def submit():
            if not entry.get_text():
                return
            if time.monotonic() < self.locked_until:
                message.set_label("Too many tries. Wait a little.")
                return
            error = self.greetd.login(
                parent["user"], self.config["parentSession"], secret=entry.get_text()
            )
            entry.set_text("")
            if error is None:
                self.get_application().quit()
                return
            self.failures += 1
            if self.failures >= PIN_ATTEMPTS:
                self.failures = 0
                self.locked_until = time.monotonic() + PIN_LOCKOUT
                message.set_label("Too many tries. Wait a little.")
            else:
                message.set_label("That is not the PIN.")

        entry.connect("activate", lambda *_: submit())
        self.overlay.show(box)
        entry.grab_focus()


def main():
    config = state.load_config()
    app = Gtk.Application(application_id="org.zoomies.Greeter")

    def activate(app):
        ui.load_css()
        window = Greeter(app, config)
        window.fullscreen()
        window.present()

    app.connect("activate", activate)
    sys.exit(app.run(None))
