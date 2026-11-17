"""Grown-ups' panel: kids and their week, the internet, Wi-Fi, the PIN,
and the way out."""

import subprocess

from . import admin, state, ui, wifi_page, week
from .i18n import _
from .ui import GLib, Gtk


def why(error):
    return getattr(error, "strerror", None) or error


class KidRow(Gtk.Box):
    def __init__(self, panel, kid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.panel = panel
        self.kid = kid
        self.add_css_class("parent-row")

        header = Gtk.Box(spacing=20)
        header.append(ui.avatar(kid, "small"))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        line = Gtk.Box(spacing=12)
        line.append(Gtk.Label(label=kid["name"], xalign=0, css_classes=["kid-name"]))
        emoji, title, _hint = ui.KidForm.KIND_LABELS[kid.get("kind", "little")]
        line.append(Gtk.Label(label=f"{emoji} {title}", valign=Gtk.Align.CENTER, css_classes=["tag"]))
        names.append(line)
        self.played = Gtk.Label(xalign=0)
        names.append(self.played)
        header.append(names)
        extra = ui.big_button(_("+15 min"), "yes", "⏳")
        extra.connect("clicked", lambda *_args: self.grant(15))
        header.append(extra)
        self.stop = ui.big_button(_("Stop for today"), "on", "🛑")
        self.stop.connect("clicked", lambda *_args: self.toggle_stop())
        header.append(self.stop)
        # Kids from the system configuration are changed there, not here.
        if not kid.get("declared"):
            edit = ui.big_button(None, "subtle", "✏️")
            edit.set_tooltip_text(_("Edit"))
            edit.connect("clicked", lambda *_args: panel.edit_kid(kid))
            header.append(edit)
            remove = ui.big_button(None, "subtle", "🗑️")
            remove.set_tooltip_text(_("Remove"))
            remove.connect("clicked", lambda *_args: panel.remove_kid(kid))
            header.append(remove)
        self.append(header)
        self.message = ui.message_label()
        self.message.set_visible(False)
        self.append(self.message)

        try:
            sections = [
                week.WeekGrid(panel, kid),
                week.InternetBox(panel, kid),
                week.SpecialDays(panel, kid),
            ]
        except (KeyError, TypeError, ValueError) as error:
            # Broken rules keep the kid out until fixed; say why here.
            self.show_message(
                _("The rules of {name} cannot be read: {reason}.").format(
                    name=kid["name"], reason=error
                )
            )
            sections = []
        self.grid = next((s for s in sections if isinstance(s, week.WeekGrid)), None)
        self.internet = next((s for s in sections if isinstance(s, week.InternetBox)), None)
        for section in sections:
            section.add_css_class("section")
            self.append(section)
        self.refresh()

    def show_message(self, text):
        self.message.set_label(text)
        self.message.set_visible(True)

    def grant(self, minutes):
        try:
            state.grant_bonus(self.kid["user"], minutes)
        except (OSError, ValueError) as error:
            self.show_message(_("Could not save: {reason}.").format(reason=why(error)))
            return
        # The timekeeper picks it up within seconds; say so right away.
        self.played.set_label(_("+{minutes} min added for today").format(minutes=minutes))

    def toggle_stop(self):
        try:
            stopped = state.stopped_today(self.kid["user"], state.load_policy())
            state.stop_today(self.kid["user"], not stopped)
        except (OSError, ValueError) as error:
            self.show_message(_("Could not save: {reason}.").format(reason=why(error)))
            return
        self.refresh()

    def refresh(self):
        try:
            self.update()
        except ValueError as error:
            self.show_message(
                _("The rules of {name} cannot be read: {reason}.").format(
                    name=self.kid["name"], reason=error
                )
            )
        return GLib.SOURCE_CONTINUE

    def update(self):
        status = state.read_status().get(self.kid["user"], {})
        used = status.get("used", 0) // 60
        remaining = status.get("remaining")
        text = _("Played {minutes} min today").format(minutes=used)
        if remaining is not None:
            text += _(", {time} left").format(time=state.format_duration(remaining))
        elif status:
            text += _(", no limit")
        if status and not status["allowed"]:
            text += _(" (resting)")
        self.played.set_label(text)
        stopped = state.stopped_today(self.kid["user"], state.load_policy())
        label = self.stop.get_child().get_last_child()
        label.set_label(_("Let play today") if stopped else _("Stop for today"))
        if self.grid is not None:
            # The line that marks the time now moves along.
            self.grid.redraw()
        if self.internet is not None:
            self.internet.refresh()


class Parent(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title=_("Zoomies grown-ups"))
        self.config = config
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.add_css_class("page")
        self.overlay = ui.Overlay(page)
        self.set_child(self.overlay)

        self.pages = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        top = Gtk.Box(spacing=20)
        top.append(ui.Mascot(config, 72))
        top.append(Gtk.Label(label=_("Grown-ups"), xalign=0, css_classes=["title"]))
        tabs = Gtk.Box(spacing=12, hexpand=True, halign=Gtk.Align.CENTER)
        first = None
        for name, emoji, title in (
            ("kids", "🧒", _("Kids")),
            ("wifi", "📶", _("Wi-Fi")),
            ("system", "⚙️", _("System")),
        ):
            tab = Gtk.ToggleButton(active=first is None)
            box = Gtk.Box(spacing=10)
            box.append(Gtk.Label(label=emoji, css_classes=["button-emoji"]))
            box.append(Gtk.Label(label=title))
            tab.set_child(box)
            tab.add_css_class("tab")
            if first is None:
                first = tab
            else:
                tab.set_group(first)
            tab.connect("toggled", self.switch_page, name)
            tabs.append(tab)
        top.append(tabs)
        top.append(ui.clock())
        page.append(top)
        page.append(self.pages)

        self.pages.add_named(self.kids_page(), "kids")
        self.wifi = wifi_page.WifiPage(self.overlay, config)
        self.pages.add_named(self.wifi, "wifi")
        self.pages.add_named(self.system_page(), "system")

        bottom = Gtk.Box(spacing=16)
        back = ui.big_button(_("Back to the kids"), "yes", "🐧")
        back.connect("clicked", lambda *_args: app.quit())
        bottom.append(back)
        page.append(bottom)

        self.populate()
        GLib.timeout_add_seconds(5, self.refresh)
        # The keyboard starts on the tabs, a known place to move from.
        first.grab_focus()
        ui.when_ready(self, "zoomies-parent")

    def switch_page(self, tab, name):
        if tab.get_active():
            self.pages.set_visible_child_name(name)
            if name == "wifi":
                self.wifi.refresh()

    def kids_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        actions = Gtk.Box(spacing=16, halign=Gtk.Align.END)
        add = ui.big_button(_("Add a kid"), "yes", "➕")
        add.connect("clicked", lambda *_args: self.edit_kid(None))
        actions.append(add)
        box.append(actions)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.scroller = Gtk.ScrolledWindow(
            vexpand=True, child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER
        )
        box.append(self.scroller)
        return box

    def system_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        def row(emoji, title, *widgets):
            line = Gtk.Box(spacing=16, css_classes=["parent-row"])
            line.append(Gtk.Label(label=emoji, css_classes=["button-emoji"]))
            line.append(
                Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["section-title"])
            )
            for widget in widgets:
                line.append(widget)
            box.append(line)

        pin = ui.big_button(_("Change PIN"), "subtle", "🔑")
        pin.connect("clicked", lambda *_args: self.change_pin())
        row("🔑", _("PIN"), pin)
        # Moving clouds and capes can distract some kids, and cost old PCs
        # without a GPU a lot of work.
        calm = Gtk.Switch(active=state.calm_screen(), valign=Gtk.Align.CENTER)
        calm.connect("notify::active", lambda switch, _pspec: state.set_calm_screen(switch.get_active()))
        row("☁️", _("Calm screen"), calm)
        terminal = ui.big_button(_("Open"), "subtle", "⌨")
        terminal.connect("clicked", lambda *_args: subprocess.Popen(["foot"]))
        row("⌨", _("Terminal"), terminal)
        row(
            "💻",
            _("Computer"),
            ui.system_button(self.overlay, "reboot", _("Restart")),
            ui.system_button(self.overlay, "poweroff", _("Power off")),
        )
        return box

    def populate(self):
        self.config = state.load_config()
        while child := self.list.get_first_child():
            self.list.remove(child)
        self.rows = [KidRow(self, kid) for kid in self.config["kids"]]
        for row in self.rows:
            self.list.append(row)
        if not self.rows:
            self.list.append(
                Gtk.Label(label=_("No kids yet. Press ➕ Add a kid."), css_classes=["dialog-title"])
            )

    def show_error(self, error):
        text = _("Could not save: {reason}.").format(reason=why(error))
        self.ask(Gtk.Label(label=text, wrap=True, css_classes=["dialog-title"]), [], _("OK"))

    def schedule_changed(self, kid, rebuild=False):
        """Show a kid's new rules; after a template, every section of the
        kid's card is new, so the card is made again."""
        for i, row in enumerate(self.rows):
            if row.kid["user"] != kid["user"]:
                continue
            if not rebuild:
                row.refresh()
                continue
            fresh = KidRow(self, row.kid)
            self.list.insert_child_after(fresh, row)
            self.list.remove(row)
            self.rows[i] = fresh
            # The old card had the focus; a stray key must not land on the
            # new card's +15 min.
            if fresh.grid is not None:
                fresh.grid.start.grab_focus()

    def ask(self, body, actions, cancel=None):
        """A dialog with a Cancel button and actions that close it when
        they return True."""
        cancel = cancel or _("Cancel")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.append(body)
        row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
        close = ui.big_button(cancel, "subtle", "✖")
        close.connect("clicked", lambda *_args: self.overlay.close())
        row.append(close)
        for text, css, emoji, run in actions:
            button = ui.big_button(text, css, emoji)

            def clicked(_button, run=run):
                if run():
                    self.overlay.close()

            button.connect("clicked", clicked)
            row.append(button)
        box.append(row)
        self.overlay.show(box)
        close.grab_focus()

    def menu(self, title, actions):
        """A list of big buttons; each closes the menu, then acts."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(title)
        for text, css, emoji, run in actions:
            button = ui.big_button(text, css, emoji)
            button.set_halign(Gtk.Align.FILL)

            def clicked(_button, run=run):
                self.overlay.close()
                run()

            button.connect("clicked", clicked)
            box.append(button)
        close = ui.big_button(_("Close"), "subtle", "✖")
        close.set_halign(Gtk.Align.CENTER)
        close.connect("clicked", lambda *_args: self.overlay.close())
        box.append(close)
        self.overlay.show(box)

    def dialog(self, title, body, action, on_accept):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.append(
            Gtk.Label(label=title, justify=Gtk.Justification.CENTER, css_classes=["dialog-title"])
        )
        box.append(body)
        message = ui.message_label()
        box.append(message)
        row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
        cancel = ui.big_button(_("Cancel"), "no", "✖")
        cancel.connect("clicked", lambda *_args: self.overlay.close())
        accept = ui.big_button(action, "yes", "✔")

        def run(*_):
            try:
                on_accept()
            except admin.Refused as error:
                message.set_label(ui.reason(error))
                return
            self.overlay.close()
            self.populate()

        accept.connect("clicked", run)
        row.append(cancel)
        row.append(accept)
        box.append(row)
        self.overlay.show(box)
        return run

    def edit_kid(self, kid):
        form = ui.KidForm(
            kid,
            older=self.config.get("olderEnabled", False),
            used_avatars=[k["avatar"] for k in self.config["kids"] if k is not kid],
        )
        if kid is None:

            def add():
                user = admin.request("add-kid", **form.values())["user"]
                # Every kid starts with the week for their kind; the
                # grown-up then sees the others and can pick one.
                try:
                    state.apply_template(user, state.default_template(form.kind))
                except (OSError, ValueError) as error:
                    GLib.idle_add(lambda e=error: self.show_error(e) and False)
                    return
                GLib.idle_add(lambda: self.pick_week(user) and False)

            run = self.dialog(_("Add a kid"), form, _("Add"), add)
        else:
            run = self.dialog(
                _("Edit {name}").format(name=kid["name"]),
                form,
                _("Save"),
                lambda: admin.request("edit-kid", user=kid["user"], **form.values()),
            )
        form.name.connect("activate", run)
        form.name.grab_focus()

    def pick_week(self, user):
        kid = next((k for k in self.config["kids"] if k["user"] == user), None)
        if kid is not None:
            week.template_picker(self, kid, lambda: self.schedule_changed(kid, True), new=True)

    def remove_kid(self, kid):
        warning = Gtk.Label(
            label=_("{avatar} {name}'s saved games and files will be deleted.").format(
                avatar=kid["avatar"], name=kid["name"]
            ),
            wrap=True,
        )
        self.dialog(
            _("Remove {name}?").format(name=kid["name"]),
            warning,
            _("Remove"),
            lambda: admin.request("remove-kid", user=kid["user"]),
        )

    def change_pin(self):
        fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        old = ui.pin_entry(_("Current PIN"))
        new = ui.pin_entry(_("New PIN"))
        again = ui.pin_entry(_("New PIN again"))
        for entry in (old, new, again):
            fields.append(entry)

        def accept():
            if new.get_text() != again.get_text():
                raise admin.Refused(_("the new PINs are different"))
            admin.request("set-pin", old=old.get_text(), new=new.get_text())

        run = self.dialog(_("🔑 Change the PIN"), fields, _("Save"), accept)
        old.connect("activate", lambda *_args: new.grab_focus())
        new.connect("activate", lambda *_args: again.grab_focus())
        again.connect("activate", run)
        old.grab_focus()

    def refresh(self):
        if not self.overlay.open:
            for row in self.rows:
                row.refresh()
        return GLib.SOURCE_CONTINUE


def main():
    config = state.load_config()
    ui.run("org.zoomies.Parent", lambda app: Parent(app, config))
