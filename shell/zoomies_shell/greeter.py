"""Profile picker: the greetd greeter for Zoomies.

Kids pick their avatar and go straight in (PAM lets the kids group through
without a password). The parent tile needs a long press, then the parent
account's password typed on a PIN pad, so the PIN is never part of the image.
"""

import json
import os
import socket
import struct
import sys

from . import admin, state, ui, wifi_page
from .i18n import _
from .ui import GLib, Gtk


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

    def login(self, user, command, secret=None, session_type="wayland"):
        """Return None on success or a short reason on failure."""
        if self.path is None:
            print(f"(no greetd) would start {command} for {user}", file=sys.stderr)
            return None
        try:
            return self._login(user, command, secret, session_type)
        except (OSError, ValueError, KeyError, struct.error) as error:
            print(f"greetd: {error!r}", file=sys.stderr)
            return "error"

    def _login(self, user, command, secret, session_type):
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
                    "env": [f"XDG_SESSION_TYPE={session_type}"],
                }
            )
            if reply["type"] == "error":
                send({"type": "cancel_session"})
                return reply.get("error_type", "error")
            return None


def describe(status):
    if not status:
        return _("Let's play!")
    if not status["allowed"]:
        return ui.when_back(status)
    if status["remaining"] is None:
        return _("Let's play!")
    return _("{time} to play").format(time=state.format_duration(status["remaining"]))


class Greeter(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title="Zoomies")
        self.config = config
        self.greetd = Greetd()
        self.tiles = {}

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page.add_css_class("page")
        self.overlay = ui.Overlay(page, ui.sky(40))
        self.set_child(self.overlay)

        top = Gtk.CenterBox()
        top.set_start_widget(ui.Mascot(config, 120))
        title = Gtk.Label(label=_("Who's playing?"), css_classes=["title"])
        top.set_center_widget(title)
        top.set_end_widget(ui.clock())
        page.append(top)

        self.kids = Gtk.Grid(
            column_spacing=24,
            row_spacing=24,
            column_homogeneous=True,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            # Room for the focus ring, which the scroller would clip.
            margin_top=14,
            margin_bottom=14,
            margin_start=14,
            margin_end=14,
        )
        # A big family must not push the grown-ups and power buttons away.
        scroller = ui.scroller(self.kids, vexpand=True)
        page.append(scroller)

        bottom = Gtk.Box(spacing=16)
        parent = ui.big_button(_("Grown-ups"), "subtle", "🔒")
        hold = Gtk.GestureLongPress(delay_factor=3.0)
        hold.connect("pressed", lambda *_args: self.ask_pin())
        parent.add_controller(hold)
        # A tap does nothing on purpose, so tell grown-ups what to do;
        # tooltips never show on touch screens.
        parent.connect("clicked", lambda *_args: self.hint(_("Keep holding 🔒 to open")))
        bottom.append(parent)
        self.hint_label = Gtk.Label(hexpand=True, xalign=0, css_classes=["kid-note"])
        bottom.append(self.hint_label)
        bottom.append(ui.system_button(self.overlay, "poweroff"))
        page.append(bottom)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.gamepad = ui.Gamepad(self, on_back=self.overlay.close)

        self.populate()
        GLib.timeout_add_seconds(5, self.refresh)
        self.ready = ui.when_ready(self, "zoomies-greeter", "setup")
        GLib.idle_add(self.maybe_set_up)

    def populate(self):
        self.config = state.load_config()
        while child := self.kids.get_first_child():
            self.kids.remove(child)
        self.tiles = {}
        kids = self.config["kids"]
        columns = 5 if len(kids) > 6 or len(kids) == 5 else 4 if len(kids) > 4 else len(kids)
        for index, kid in enumerate(kids):
            self.kids.attach(self._kid_tile(kid), index % columns, index // columns, 1, 1)
        if not self.tiles:
            empty = Gtk.Label(
                label=_("No kids yet.\nGrown-ups can add them with the 🔒 button."),
                justify=Gtk.Justification.CENTER,
                css_classes=["dialog-title"],
            )
            self.kids.attach(empty, 0, 0, 1, 1)
        self.refresh()
        first = next(iter(self.tiles.values()), None)
        if first:
            first.grab_focus()

    def hint(self, text):
        self.hint_label.set_label(text)

        def clear():
            self.hint_label.set_label("")
            return GLib.SOURCE_REMOVE

        GLib.timeout_add_seconds(3, clear)

    def pin_set(self):
        """True, False, or None when the admin service cannot tell."""
        try:
            return bool(admin.request("status").get("pinSet"))
        except admin.Refused as error:
            print(f"setup check failed: {error}", file=sys.stderr)
            return None

    def pin_locked(self):
        """Whether PAM locked the grown-ups out after too many wrong PINs."""
        try:
            return bool(admin.request("pin-locked").get("locked"))
        except admin.Refused as error:
            print(f"lock check failed: {error}", file=sys.stderr)
            return False

    def maybe_set_up(self, tries=10):
        if not self.config.get("parent"):
            self.ready("setup")
            return GLib.SOURCE_REMOVE
        pin_set = self.pin_set()
        if pin_set is None and tries > 1:
            # The service may still be starting on a slow first boot.
            GLib.timeout_add_seconds(3, self.maybe_set_up, tries - 1)
            return GLib.SOURCE_REMOVE
        if pin_set is False:
            Setup(self).start()
        self.ready("setup")
        return GLib.SOURCE_REMOVE

    def _kid_tile(self, kid):
        button = Gtk.Button()
        button.add_css_class("kid-tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(ui.avatar(kid))
        box.append(Gtk.Label(label=kid["name"], css_classes=["kid-name"]))
        note = Gtk.Label(css_classes=["kid-note"])
        box.append(note)
        button.set_child(box)
        button.note = note
        button.connect("clicked", lambda *_args: self.play(kid))
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
        return False

    def play(self, kid):
        status = state.read_status().get(kid["user"])
        if status and not status["allowed"]:
            self.send_outside(kid, status)
            return
        ui.play("service-login")
        if kid.get("kind") == "older":
            error = self.greetd.login(kid["user"], self.config["olderSession"], session_type="x11")
        else:
            error = self.greetd.login(kid["user"], self.config["kidSession"])
        if error is None:
            self.overlay.fade_to_sky(self.get_application().quit)
            return
        # PAM may know better than the last status the timekeeper wrote,
        # for example right as the allowed hours end.
        try:
            status = state.kid_status(kid, state.load_policy(), state.load_usage())
        except ValueError:
            # Rules that cannot be read keep everyone resting.
            status = {"allowed": False, "reason": "broken", "opensIn": None, "opensAt": None}
        if not status["allowed"]:
            self.send_outside(kid, status)
            self.refresh()
        else:
            self.say("🙈", _("Oops, that did not work.\nAsk a grown-up for help."))

    def send_outside(self, kid, status):
        text = _("{status}, {name}!\nZip says: go run around outside!").format(
            status=describe(status), name=kid["name"]
        )
        self.say(kid["avatar"], text, flying=True)

    def say(self, emoji, text, flying=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        if flying:
            # A vertical box would size the picture for the full dialog
            # width; a row gives it only its own width.
            row = Gtk.Box(halign=Gtk.Align.CENTER)
            row.append(ui.Mascot(self.config, 120, "fly"))
            box.append(row)
        box.append(
            Gtk.Label(
                label=f"{emoji}\n{text}",
                justify=Gtk.Justification.CENTER,
                css_classes=["dialog-title"],
            )
        )
        ok = ui.big_button(_("OK"), "yes", "👍")
        ok.set_halign(Gtk.Align.CENTER)
        ok.connect("clicked", lambda *_args: self.overlay.close())
        box.append(ok)
        self.overlay.show(box)
        ok.grab_focus()

    def ask_pin(self):
        parent = self.config.get("parent")
        if not parent or self.overlay.open:
            return
        if self.pin_set() is False:
            Setup(self).start()
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.append(
            Gtk.Label(
                label=_("🔒\nGrown-ups only"),
                justify=Gtk.Justification.CENTER,
                css_classes=["dialog-title"],
            )
        )
        entry = ui.pin_entry(_("PIN"))
        box.append(entry)
        message = ui.message_label()
        box.append(message)

        pad = Gtk.Grid(row_spacing=10, column_spacing=10, halign=Gtk.Align.CENTER)
        for index, key in enumerate("123456789⌫0✔"):
            button = Gtk.Button(label=key)
            button.add_css_class("pin-key")
            if key == "⌫":
                button.connect("clicked", lambda *_args: entry.set_text(entry.get_text()[:-1]))
            elif key == "✔":
                button.add_css_class("yes")
                button.connect("clicked", lambda *_args: submit())
            else:
                button.connect("clicked", lambda _b, k=key: entry.set_text(entry.get_text() + k))
            pad.attach(button, index % 3, index // 3, 1, 1)
        box.append(pad)
        cancel = ui.big_button(_("Cancel"), "no", "✖")
        cancel.set_halign(Gtk.Align.CENTER)
        cancel.connect("clicked", lambda *_args: self.overlay.close())
        box.append(cancel)

        def submit():
            if not entry.get_text():
                return
            error = self.greetd.login(
                parent["user"], self.config["parentSession"], secret=entry.get_text()
            )
            entry.set_text("")
            if error is None:
                self.overlay.fade_to_sky(self.get_application().quit)
                return
            # greetd answers a locked account like a wrong PIN.
            if self.pin_locked():
                message.set_label(
                    _("Too many tries. Ask a grown-up, or wait a little and try again.")
                )
            else:
                message.set_label(_("That is not the PIN."))

        entry.connect("activate", lambda *_args: submit())
        self.overlay.show(box)
        entry.grab_focus()


class Setup:
    """First boot: get online, create the grown-ups PIN, then add the kids.

    Runs in the greeter because nobody can log in yet; the admin service
    accepts Wi-Fi and the PIN without a PIN only while none is set, and
    kids only with that PIN.
    """

    def __init__(self, greeter):
        self.greeter = greeter
        self.overlay = greeter.overlay
        self.pin = None
        self.added = []

    def start(self):
        # Online already, from a cable or the installer's network, or no
        # Wi-Fi to set up: straight to the PIN.
        def checked(reply, error):
            if error is None and reply["wifi"] and reply["enabled"] and not reply["online"]:
                self.wifi()
            else:
                self.ask_pin()

        wifi_page.in_background(lambda: admin.request("wifi-status"), checked)

    def wifi(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.append(
            Gtk.Label(
                label=_("👋 Welcome to Zoomies!\nLet's get online first."),
                justify=Gtk.Justification.CENTER,
                css_classes=["dialog-title"],
            )
        )
        box.append(
            Gtk.Label(
                label=_("Pick your Wi-Fi. You can also do this later."),
                justify=Gtk.Justification.CENTER,
            )
        )
        networks = wifi_page.NetworkList(self.overlay, on_connected=self.ask_pin, back=self.wifi)
        networks.set_size_request(560, -1)
        box.append(networks)
        skip = ui.big_button(_("Skip"), "subtle", "➜")
        skip.set_halign(Gtk.Align.CENTER)
        # A connection still on its way must not move the wizard on later.
        skip.connect("clicked", lambda *_args: (networks.abandon(), self.ask_pin()))
        box.append(skip)
        self.overlay.show(box, modal=True)
        networks.scan()
        skip.grab_focus()

    def ask_pin(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        title = Gtk.Label(
            label=_("👋 Welcome to Zoomies!\nFirst, a grown-up picks a secret PIN."),
            justify=Gtk.Justification.CENTER,
            css_classes=["dialog-title"],
        )
        box.append(title)
        hint = Gtk.Label(label=_("4 to 12 digits. Kids should not see it!"))
        box.append(hint)
        first = ui.pin_entry(_("New PIN"))
        again = ui.pin_entry(_("Same PIN again"))
        box.append(first)
        box.append(again)
        message = ui.message_label()
        box.append(message)
        save = ui.big_button(_("Save the PIN"), "yes", "🔒")
        save.set_halign(Gtk.Align.CENTER)
        box.append(save)

        def submit(*_):
            if first.get_text() != again.get_text():
                message.set_label(_("The two PINs are different. Try again."))
                again.set_text("")
                again.grab_focus()
                return
            try:
                admin.request("set-pin", new=first.get_text())
            except admin.Refused as error:
                # The PIN may have been saved even though the answer got
                # lost; asking again would then need the "old" PIN.
                if self.greeter.pin_set() is not True:
                    message.set_label(ui.reason(error))
                    return
            self.pin = first.get_text()
            self.kids()

        first.connect("activate", lambda *_args: again.grab_focus())
        again.connect("activate", submit)
        save.connect("clicked", submit)
        # Nobody can log in before this is done, so it cannot be skipped.
        self.overlay.show(box, modal=True)
        first.grab_focus()

    def kids(self):
        config = state.load_config()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        title = Gtk.Label(
            label=_("Who will play?"), justify=Gtk.Justification.CENTER, css_classes=["dialog-title"]
        )
        box.append(title)
        added = Gtk.Label(
            label="  ".join(f"{k['avatar']} {k['name']}" for k in config["kids"])
            or _("Type a name, pick a face, then press Add."),
            wrap=True,
            css_classes=["kid-note"],
        )
        box.append(added)
        form = ui.KidForm(
            older=config.get("olderEnabled", False),
            used_avatars=[k["avatar"] for k in config["kids"]],
        )
        box.append(form)
        message = ui.message_label()
        box.append(message)
        row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
        add = ui.big_button(_("Add"), "yes", "➕")
        done = ui.big_button(_("Done"), "subtle", "✔")
        row.append(add)
        row.append(done)
        box.append(row)

        def submit(*_):
            values = form.values()
            if not values["name"]:
                if config["kids"]:
                    finish()
                else:
                    message.set_label(_("Type the kid's name first."))
                return
            try:
                admin.request("add-kid", pin=self.pin, **values)
            except admin.Refused as error:
                message.set_label(ui.reason(error))
                return
            self.kids()

        def finish(*_):
            self.overlay.close(force=True)
            self.greeter.populate()

        form.name.connect("activate", submit)
        add.connect("clicked", submit)
        done.connect("clicked", finish)
        self.overlay.show(box, modal=True)
        form.name.grab_focus()


def main():
    config = state.load_config()
    ui.run("org.zoomies.Greeter", lambda app: Greeter(app, config))
