"""Wi-Fi screens: the grown-ups' page and the first-boot wizard's list.

Both ask the admin service, which talks to NetworkManager as root. Scans and
connections take seconds, so requests run off the main thread and the
screens stay responsive.
"""

import subprocess
import threading

from . import admin, ui
from .i18n import _
from .ui import GLib, Gtk


RESCAN_SECONDS = 5


def in_background(call, done):
    """Run call() in a thread and done(reply, error) back on the screen."""

    def work():
        try:
            reply, error = call(), None
        except admin.Refused as refused:
            reply, error = None, refused
        GLib.idle_add(lambda: done(reply, error) and False)

    threading.Thread(target=work, daemon=True).start()


def bars(strength):
    return "▂▄▆█"[: max(1, min(4, (strength + 24) // 25))].ljust(4, "·")


class NetworkList(Gtk.Box):
    """Networks nearby; picking one asks for its password and connects."""

    def __init__(self, overlay, on_connected=lambda: None, back=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.overlay = overlay
        self.on_connected = on_connected
        # Where closing one of its dialogs goes: in the wizard, the list
        # itself sits in a dialog, which must come back.
        self.go_back = back or overlay.close
        self.modal = back is not None
        # The connection being waited for; a reply to any other, from a
        # dialog the grown-up left, must not close what is shown now.
        self.pending = None
        top = Gtk.Box(spacing=12)
        self.title = Gtk.Label(
            label=_("Networks nearby"), xalign=0, hexpand=True, css_classes=["section-title"]
        )
        top.append(self.title)
        self.again = ui.big_button(_("Look again"), "subtle", "🔄")
        self.again.add_css_class("small")
        self.again.connect("clicked", lambda *_args: self.scan())
        top.append(self.again)
        self.append(top)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.rows)
        other = Gtk.Button(css_classes=["network"])
        other.set_child(Gtk.Label(label=_("➕ Other network…"), xalign=0))
        other.connect("clicked", lambda *_args: self.ask_password(None))
        self.append(other)
        self.message = ui.message_label()
        self.append(self.message)

    def show(self, box):
        self.overlay.show(box, modal=self.modal)

    def back(self):
        self.abandon()
        self.go_back()

    def abandon(self):
        """Forget the connection being waited for: its screen is gone."""
        self.pending = None

    def request(self, action, done, **fields):
        in_background(lambda: admin.request(action, **fields), done)

    def scan(self):
        self.again.set_sensitive(False)
        self.title.set_label(_("Looking for networks…"))
        self.request("wifi-scan", self.scanned)

    def scanned(self, reply, error):
        self.again.set_sensitive(True)
        self.title.set_label(_("Networks nearby"))
        while child := self.rows.get_first_child():
            self.rows.remove(child)
        if error is not None:
            self.message.set_label(ui.reason(error))
            return
        self.message.set_label("")
        for network in reply["networks"]:
            row = Gtk.Button(css_classes=["network"])
            line = Gtk.Box(spacing=14)
            line.append(Gtk.Label(label=bars(network["strength"]), css_classes=["signal"]))
            line.append(
                Gtk.Label(
                    label=network["ssid"], xalign=0, hexpand=True, css_classes=["network-name"]
                )
            )
            if network["connected"]:
                line.append(Gtk.Label(label=_("connected"), css_classes=["hint"]))
            elif network["known"]:
                line.append(Gtk.Label(label=_("saved"), css_classes=["hint"]))
            line.append(
                Gtk.Label(label="🔒" if network["secure"] else "", css_classes=["button-emoji"])
            )
            row.set_child(line)
            row.connect("clicked", lambda _b, n=network: self.pick(n))
            self.rows.append(row)
        if not reply["networks"]:
            self.rows.append(Gtk.Label(label=_("No networks found."), css_classes=["hint"]))
            # Radios take a while to wake up, and routers to come back on.
            GLib.timeout_add_seconds(RESCAN_SECONDS, self.rescan)

    def rescan(self):
        if self.get_mapped() and self.again.get_sensitive():
            self.scan()
        return GLib.SOURCE_REMOVE

    def pick(self, network):
        if not network["supported"]:
            self.message.set_label(_("Set this network up with More settings."))
        elif network["connected"] or network["known"]:
            self.saved_menu(network)
        elif network["password"]:
            self.ask_password(network)
        else:
            self.connect_to(network, None, False)

    def saved_menu(self, network):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.append(Gtk.Label(label=f"📶 {network['ssid']}", css_classes=["dialog-title"]))
        row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
        close = ui.big_button(_("Close"), "subtle", "✖")
        close.connect("clicked", lambda *_args: self.back())
        row.append(close)
        forget = ui.big_button(_("Forget"), "no", "🗑️")
        forget.connect("clicked", lambda *_args: self.forget(network))
        row.append(forget)
        if not network["connected"]:
            join = ui.big_button(_("Connect"), "yes", "✔")
            join.connect("clicked", lambda *_args: self.connect_to(network, None, False))
            row.append(join)
        box.append(row)
        self.show(box)
        close.grab_focus()

    def ask_password(self, network):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        name = None
        if network is None:
            box.append(Gtk.Label(label=_("📶 Other network"), css_classes=["dialog-title"]))
            name = Gtk.Entry(placeholder_text=_("Network name"))
            name.add_css_class("name-entry")
            box.append(name)
        else:
            box.append(Gtk.Label(label=f"📶 {network['ssid']}", css_classes=["dialog-title"]))
        password = Gtk.PasswordEntry(placeholder_text=_("Password"), show_peek_icon=True)
        password.add_css_class("name-entry")
        box.append(password)
        if network is None:
            box.append(
                Gtk.Label(
                    label=_("Leave the password empty for an open network."), css_classes=["hint"]
                )
            )
        message = ui.message_label()
        box.append(message)
        row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
        cancel = ui.big_button(_("Cancel"), "no", "✖")
        cancel.connect("clicked", lambda *_args: self.back())
        join = ui.big_button(_("Connect"), "yes", "✔")
        row.append(cancel)
        row.append(join)
        box.append(row)

        def submit(*_):
            target = {"ssid": name.get_text().strip()} if name else network
            secret = password.get_text() or None
            if not target["ssid"]:
                message.set_label(_("Type the network's name."))
                return
            if secret is not None and not 8 <= len(secret) <= 63:
                message.set_label(_("Wi-Fi passwords have 8 to 63 characters."))
                return
            self.connect_to(target, secret, network is None, message, join)

        join.connect("clicked", submit)
        password.connect("activate", submit)
        self.show(box)
        (name or password).grab_focus()

    def connect_to(self, network, password, hidden, message=None, button=None):
        if message is None:
            # A small dialog that says it is busy, then why it failed.
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            box.append(Gtk.Label(label=f"📶 {network['ssid']}", css_classes=["dialog-title"]))
            message = ui.message_label()
            box.append(message)
            close = ui.big_button(_("Close"), "subtle", "✖")
            close.set_halign(Gtk.Align.CENTER)
            close.connect("clicked", lambda *_args: self.back())
            box.append(close)
            self.show(box)
        message.set_label(_("Connecting…"))
        if button is not None:
            button.set_sensitive(False)

        token = self.pending = object()

        def done(_reply, error):
            if token is not self.pending:
                return
            self.pending = None
            if button is not None:
                button.set_sensitive(True)
            if error is not None:
                message.set_label(ui.reason(error))
                return
            self.overlay.close(force=True)
            self.scan()
            self.on_connected()

        self.request("wifi-connect", done, hidden=hidden, **self.which(network, password))

    @staticmethod
    def which(network, password=None):
        """The fields that name a network for the admin service."""
        fields = {"id": network["id"]} if "id" in network else {"ssid": network["ssid"]}
        if password:
            fields["password"] = password
        return fields

    def forget(self, network):
        self.back()
        self.request(
            "wifi-forget",
            lambda _r, error: (
                self.scan() if error is None else self.message.set_label(ui.reason(error))
            ),
            **self.which(network),
        )


class WifiPage(Gtk.Box):
    """The grown-ups' page: Wi-Fi on or off, networks, and the cable."""

    def __init__(self, overlay, config):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.overlay = overlay
        self.updating = False

        header = Gtk.Box(spacing=16, css_classes=["parent-row"])
        header.append(Gtk.Label(label="📶", css_classes=["button-emoji"]))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        names.append(Gtk.Label(label=_("Wi-Fi"), xalign=0, css_classes=["section-title"]))
        self.status = Gtk.Label(xalign=0)
        names.append(self.status)
        header.append(names)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("notify::active", self.toggled)
        header.append(self.switch)
        self.append(header)

        self.networks = NetworkList(overlay, on_connected=self.refresh)
        self.networks.add_css_class("parent-row")
        scroller = ui.scroller(self.networks, vexpand=True)
        self.append(scroller)

        cable = Gtk.Box(spacing=16, css_classes=["parent-row"])
        cable.append(Gtk.Label(label="🔌", css_classes=["button-emoji"]))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        names.append(Gtk.Label(label=_("Cable"), xalign=0, css_classes=["section-title"]))
        self.wired = Gtk.Label(xalign=0)
        names.append(self.wired)
        cable.append(names)
        editor = config.get("networkEditor")
        if editor:
            more = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            button = ui.big_button(_("More settings"), "subtle", "🛠️")
            button.connect("clicked", lambda *_args: subprocess.Popen([editor]))
            more.append(button)
            more.append(Gtk.Label(label=_("IP address, proxy, VPN"), css_classes=["hint"]))
            cable.append(more)
        self.append(cable)
        self.message = ui.message_label()
        self.append(self.message)

    def refresh(self):
        in_background(lambda: admin.request("wifi-status"), self.show_status)

    def show_status(self, reply, error):
        if error is not None:
            self.status.set_label(ui.reason(error))
            self.networks.set_visible(False)
            self.switch.set_visible(False)
            self.wired.set_label("")
            return
        self.updating = True
        self.switch.set_visible(reply["wifi"])
        self.switch.set_active(reply["enabled"])
        self.updating = False
        if not reply["wifi"]:
            self.status.set_label(_("This computer has no Wi-Fi."))
        elif not reply["enabled"]:
            self.status.set_label(_("Off"))
        elif reply["connected"]:
            self.status.set_label(_("Connected to {network}").format(network=reply["connected"]))
        else:
            self.status.set_label(_("Not connected"))
        self.wired.set_label(_("Connected") if reply["wired"] else _("Not plugged in"))
        show = reply["wifi"] and reply["enabled"]
        self.networks.set_visible(show)
        if show:
            self.networks.scan()

    def toggled(self, switch, _pspec):
        if self.updating:
            return

        def done(_reply, error):
            if error is not None:
                self.message.set_label(ui.reason(error))
            self.refresh()

        in_background(lambda: admin.request("wifi-enable", on=switch.get_active()), done)
