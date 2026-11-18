"""Grown-ups' panel: kids and their week, the internet, Wi-Fi, the PIN,
and the way out."""

import subprocess

from . import admin, state, ui, wifi_page, week
from .i18n import _
from .ui import GLib, Gtk


def why(error):
    return getattr(error, "strerror", None) or error


def chip_status(status, stopped):
    """A few words on where a kid stands today, and their mood: playing,
    free to play, resting or stopped."""
    if stopped:
        return _("Stopped for today"), "stopped"
    if not status:
        return "", "free"
    if not status["allowed"]:
        return ui.when_back(status), "resting"
    playing = status.get("playing")
    mood = "playing" if playing else "free"
    remaining = status["remaining"]
    if remaining is None:
        return (_("Playing, no limit") if playing else _("No limit")), mood
    text = _("Playing, {time} left") if playing else _("{time} left")
    return text.format(time=state.format_duration(remaining)), mood


class KidChip(Gtk.ToggleButton):
    """A kid to pick in the panel, with how their day goes so far."""

    def __init__(self, kid):
        super().__init__(css_classes=["kid-chip"])
        self.kid = kid
        box = Gtk.Box(spacing=12)
        box.append(ui.avatar(kid, "chip"))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        names.append(Gtk.Label(label=kid["name"], xalign=0, css_classes=["chip-name"]))
        line = Gtk.Box(spacing=6)
        self.mood = Gtk.Box(valign=Gtk.Align.CENTER, css_classes=["mood"])
        line.append(self.mood)
        self.status = Gtk.Label(xalign=0, css_classes=["chip-status"])
        line.append(self.status)
        names.append(line)
        box.append(names)
        self.set_child(box)

    def show_status(self, status, stopped):
        text, mood = chip_status(status, stopped)
        self.status.set_label(text)
        self.mood.set_css_classes(["mood", mood])


class KidCard(Gtk.Box):
    def __init__(self, panel, kid, chip=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.panel = panel
        self.kid = kid
        self.chip = chip or KidChip(kid)
        self.add_css_class("parent-row")

        header = Gtk.Box(spacing=20)
        header.append(ui.avatar(kid, "chip"))
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
        if sections:
            self.append(self.tabbed(sections))
        self.refresh()

    TABS = (("📅", _("Week")), ("🌐", _("Internet")), ("⭐", _("Special days")))

    def tabbed(self, sections):
        """The sections, one at a time behind tabs, so the week has the
        card's whole height; the tab's own button sits on the right."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        line = Gtk.Box(spacing=12)
        tabs = Gtk.Box(spacing=8, hexpand=True, halign=Gtk.Align.START, css_classes=["subtabs"])
        line.append(tabs)
        tools = Gtk.Stack(hhomogeneous=False, interpolate_size=True)
        line.append(tools)
        box.append(line)
        pages = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        box.append(pages)
        first = None
        for (emoji, title), section in zip(self.TABS, sections, strict=True):
            tab = Gtk.ToggleButton(css_classes=["subtab"])
            label = Gtk.Box(spacing=8)
            label.append(Gtk.Label(label=emoji, css_classes=["subtab-emoji"]))
            label.append(Gtk.Label(label=title))
            tab.set_child(label)
            if first is None:
                first = tab
            else:
                tab.set_group(first)
            tabs.append(tab)
            page = ui.scroller(section)
            pages.add_named(page, title)
            tool = section.tool or Gtk.Box()
            tools.add_named(tool, title)

            def toggled(tab, page=page, tool=tool):
                if tab.get_active():
                    pages.set_visible_child(page)
                    tools.set_visible_child(tool)

            tab.connect("toggled", toggled)
        first.set_active(True)
        return box

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
        self.chip.show_status(status, stopped)
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
            ("network", "📡", _("Network")),
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

        self.selected = None
        self.pages.add_named(self.kids_page(), "kids")
        self.network = wifi_page.NetworkPage(self.overlay)
        self.pages.add_named(self.network, "network")
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
            if name == "network":
                self.network.refresh()
            elif name == "system" and self.config.get("remoteAccess"):
                # The address may have changed since the panel opened.
                self.show_remote_access(self.ask_remote_access("remote-access"))

    def kids_page(self):
        """One kid at a time, picked from a chip for each kid at the top."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        # Many kids wrap onto a second line rather than hide off screen.
        self.chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["kid-chips"])
        box.append(self.chips)
        self.cards = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        box.append(self.cards)
        return box

    def add_chip(self, widget):
        self.chips.append(widget)
        # The chip itself takes the focus, not the box around it.
        widget.get_parent().set_focusable(False)

    def show_kid(self, chip):
        if chip.get_active():
            self.selected = chip.kid["user"]
            card = next(row for row in self.rows if row.chip is chip)
            self.cards.set_visible_child(card)

    def system_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        def row(emoji, title, *widgets, detail=None):
            line = Gtk.Box(spacing=16, css_classes=["parent-row"])
            line.append(Gtk.Label(label=emoji, css_classes=["button-emoji"]))
            words = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER
            )
            words.append(Gtk.Label(label=title, xalign=0, css_classes=["section-title"]))
            if detail is not None:
                words.append(detail)
            line.append(words)
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
        if self.config.get("remoteAccess"):
            self.remote_detail = Gtk.Label(xalign=0, wrap=True, css_classes=["hint"])
            self.remote = Gtk.Switch(valign=Gtk.Align.CENTER)
            self.remote.connect("state-set", self.set_remote_access)
            row("🌍", _("Remote access"), self.remote, detail=self.remote_detail)
            self.show_remote_access(self.ask_remote_access("remote-access"))
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

    def ask_remote_access(self, action, **fields):
        try:
            return admin.request(action, **fields)
        except admin.Refused as error:
            return {"error": error}

    def show_remote_access(self, reply):
        if "error" in reply:
            self.remote.set_active(self.remote.get_state())
            self.remote_detail.set_label(ui.reason(reply["error"]))
            return
        on = bool(reply["on"])
        self.remote.set_state(on)
        self.remote.set_active(on)
        if not on:
            text = _("Off: nobody can log in to this computer from another one.")
        elif reply["addresses"]:
            # Translators: {command} is what to type on another computer, such as "ssh parent@192.168.1.20".
            text = _("On: from a computer at home, type {command} and the PIN.").format(
                command=f"ssh {reply['user']}@{reply['addresses'][0]}"
            )
        else:
            text = _("On, but this computer is not connected to a network.")
        self.remote_detail.set_label(text)

    def set_remote_access(self, _switch, on):
        if on != self.remote.get_state():
            self.show_remote_access(self.ask_remote_access("set-remote-access", on=on))
        # The switch shows what the service did, not what was asked.
        return True

    def populate(self):
        self.config = state.load_config()
        self.chips.remove_all()
        while child := self.cards.get_first_child():
            self.cards.remove(child)
        self.rows = [KidCard(self, kid) for kid in self.config["kids"]]
        users = [row.kid["user"] for row in self.rows]
        if self.selected not in users:
            self.selected = users[0] if users else None
        first = None
        for row in self.rows:
            if first is None:
                first = row.chip
            else:
                row.chip.set_group(first)
            row.chip.connect("toggled", self.show_kid)
            self.add_chip(row.chip)
            self.cards.add_child(row)
        add = ui.big_button(_("Add a kid"), "subtle", "➕")
        add.add_css_class("add-chip")
        add.add_css_class("small")
        add.connect("clicked", lambda *_args: self.edit_kid(None))
        self.add_chip(add)
        for row in self.rows:
            if row.kid["user"] == self.selected:
                row.chip.set_active(True)
                self.cards.set_visible_child(row)
        if not self.rows:
            self.cards.add_child(
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
            fresh = KidCard(self, row.kid, row.chip)
            self.rows[i] = fresh
            self.cards.add_child(fresh)
            self.cards.set_visible_child(fresh)
            self.cards.remove(row)
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
                self.selected = user
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
