"""Network screens: the grown-ups' page and the first-boot wizard's Wi-Fi list.

Both ask the admin service, which talks to NetworkManager as root. Scans and
connections take seconds, so requests run off the main thread and the
screens stay responsive.
"""

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

    def __init__(self, overlay, on_connected=lambda: None, back=None, settings=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.overlay = overlay
        self.on_connected = on_connected
        # Opens a saved network's address settings, where there are any.
        self.settings = settings
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
            self.message.set_label(_("Zoomies cannot join this kind of network."))
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
        if self.settings is not None:
            settings = ui.big_button(_("Settings"), "subtle", "⚙️")
            settings.connect("clicked", lambda *_args: self.settings(network))
            row.append(settings)
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


def address_dialog(overlay, fields, title, done=lambda: None):
    """How a connection gets its address: from the router, or fixed."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, css_classes=["address"])
    box.append(Gtk.Label(label=title, css_classes=["dialog-title"]))
    modes = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER, css_classes=["subtabs"])
    automatic = Gtk.ToggleButton(label=_("Automatic"), css_classes=["subtab"], active=True)
    fixed = Gtk.ToggleButton(label=_("Fixed address"), css_classes=["subtab"], group=automatic)
    modes.append(automatic)
    modes.append(fixed)
    box.append(modes)
    pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=True)
    box.append(pages)

    now = Gtk.Grid(column_spacing=24, row_spacing=10, halign=Gtk.Align.CENTER)
    now.attach(Gtk.Label(label=_("Given by the router:"), css_classes=["hint"]), 0, 0, 2, 1)
    pages.add_named(now, "auto")
    entries = Gtk.Grid(column_spacing=16, row_spacing=10, halign=Gtk.Align.CENTER)
    pages.add_named(entries, "fixed")
    names = (_("Address"), _("Router"), _("DNS"))
    shown = []
    for row, name in enumerate(names):
        now.attach(Gtk.Label(label=name, xalign=1, css_classes=["field-name"]), 0, row + 1, 1, 1)
        value = Gtk.Label(xalign=0)
        now.attach(value, 1, row + 1, 1, 1)
        shown.append(value)
    placeholders = ("192.168.1.50", "192.168.1.1", "1.1.1.1, 8.8.8.8")
    typed = []
    for row, (name, example) in enumerate(zip(names, placeholders, strict=True)):
        entries.attach(Gtk.Label(label=name, xalign=1, css_classes=["field-name"]), 0, row, 1, 1)
        entry = Gtk.Entry(placeholder_text=example, width_chars=18, css_classes=["field"])
        entries.attach(entry, 1, row, 1, 1)
        typed.append(entry)
    address, gateway, dns = typed

    message = ui.message_label()
    box.append(message)
    row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
    cancel = ui.big_button(_("Cancel"), "no", "✖")
    cancel.connect("clicked", lambda *_args: overlay.close())
    save = ui.big_button(_("Save"), "yes", "✔")
    save.set_sensitive(False)
    row.append(cancel)
    row.append(save)
    box.append(row)

    def switched(*_args):
        pages.set_visible_child_name("fixed" if fixed.get_active() else "auto")

    fixed.connect("toggled", switched)

    def loaded(reply, error):
        if error is not None:
            message.set_label(ui.reason(error))
            return
        current = reply["now"]
        if current is None:
            for label in shown:
                label.set_label("—")
            message.set_label(_("Not connected now."))
        else:
            shown[0].set_label(current["address"] or "—")
            shown[1].set_label(current["gateway"] or "—")
            shown[2].set_label(", ".join(current["dns"]) or "—")
        saved = reply["saved"]
        # A grown-up who switches to a fixed address usually keeps the one
        # the router gave, so that is where the fields start.
        start = saved if reply["fixed"] else (current or saved)
        address.set_text(start["address"] or "")
        gateway.set_text(start["gateway"] or "")
        dns.set_text(", ".join(start["dns"]))
        fixed.set_active(reply["fixed"])
        save.set_sensitive(True)

    def submit(*_args):
        message.set_label(_("Saving…"))
        save.set_sensitive(False)
        values = {"fixed": fixed.get_active()}
        if fixed.get_active():
            values.update(
                address=address.get_text(), gateway=gateway.get_text(), dns=dns.get_text()
            )

        def saved(_reply, error):
            save.set_sensitive(True)
            if error is not None:
                message.set_label(ui.reason(error))
                return
            overlay.close()
            done()

        in_background(lambda: admin.request("set-address", **fields, **values), saved)

    save.connect("clicked", submit)
    for entry in typed:
        entry.connect("activate", submit)
    overlay.show(box)
    automatic.grab_focus()
    in_background(lambda: admin.request("address", **fields), loaded)


class NetworkPage(Gtk.Box):
    """The grown-ups' page: the cable, and Wi-Fi on or off with its networks."""

    def __init__(self, overlay):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.overlay = overlay
        self.updating = False

        self.cable = Gtk.Box(spacing=16, css_classes=["parent-row"])
        self.cable.append(Gtk.Label(label="🔌", css_classes=["button-emoji"]))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        names.append(Gtk.Label(label=_("Cable"), xalign=0, css_classes=["section-title"]))
        self.wired = Gtk.Label(xalign=0)
        names.append(self.wired)
        self.cable.append(names)
        settings = ui.big_button(_("Settings"), "subtle", "⚙️")
        settings.connect(
            "clicked",
            lambda *_args: address_dialog(overlay, {"cable": True}, _("🔌 Cable"), self.refresh),
        )
        self.cable.append(settings)
        self.append(self.cable)

        wifi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, vexpand=True)
        wifi.add_css_class("parent-row")
        header = Gtk.Box(spacing=16)
        header.append(Gtk.Label(label="📶", css_classes=["button-emoji"]))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        names.append(Gtk.Label(label=_("Wi-Fi"), xalign=0, css_classes=["section-title"]))
        self.status = Gtk.Label(xalign=0)
        names.append(self.status)
        header.append(names)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.switch.connect("notify::active", self.toggled)
        header.append(self.switch)
        wifi.append(header)
        self.networks = NetworkList(overlay, on_connected=self.refresh, settings=self.settings)
        self.scroller = ui.scroller(self.networks, vexpand=True)
        wifi.append(self.scroller)
        self.append(wifi)
        self.message = ui.message_label()
        self.append(self.message)

    def settings(self, network):
        address_dialog(
            self.overlay, NetworkList.which(network), f"📶 {network['ssid']}", self.refresh
        )

    def refresh(self):
        in_background(lambda: admin.request("wifi-status"), self.show_status)

    def show_status(self, reply, error):
        if error is not None:
            self.status.set_label(ui.reason(error))
            self.scroller.set_visible(False)
            self.switch.set_visible(False)
            self.cable.set_visible(False)
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
            text = _("Connected to {network}").format(network=reply["connected"])
            self.status.set_label(connected(text, reply["wifiAddress"]))
        else:
            self.status.set_label(_("Not connected"))
        self.cable.set_visible(reply["cable"])
        self.wired.set_label(
            connected(_("Connected"), reply["wiredAddress"])
            if reply["wired"]
            else _("Not plugged in")
        )
        show = reply["wifi"] and reply["enabled"]
        self.scroller.set_visible(show)
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


def connected(text, address):
    """A connection's state with its address, which grown-ups need when
    they set up a router or a printer."""
    return f"{text} · {address}" if address else text
