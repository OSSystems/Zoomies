"""Grown-ups' panel: kids, screen time rules, extra time, the PIN, and the way out."""

import subprocess

from . import admin, state, ui
from .i18n import _
from .ui import GLib, Gtk


def spin(low, high, value, step=1):
    button = Gtk.SpinButton.new_with_range(low, high, step)
    button.set_value(value)
    button.set_valign(Gtk.Align.CENTER)
    return button


def time_spin(low, high, value):
    button = spin(low, high, value)
    button.set_numeric(False)
    button.set_width_chars(5)

    def output(widget):
        widget.set_text(state.format_minutes_of_day(int(widget.get_value()) * 30))
        return True

    def parse(widget):
        try:
            return True, state.minutes_of_day(widget.get_text()) / 30
        except ValueError:
            return False, 0

    button.connect("output", output)
    button.connect("input", parse)
    output(button)
    return button


class KidRow(Gtk.Box):
    def __init__(self, panel, kid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.kid = kid
        self.add_css_class("parent-row")

        header = Gtk.Box(spacing=20)
        header.append(ui.avatar(kid, "small"))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        line = Gtk.Box(spacing=12)
        name = Gtk.Label(label=kid["name"], xalign=0)
        name.add_css_class("kid-name")
        line.append(name)
        emoji, title, _hint = ui.KidForm.KIND_LABELS[kid.get("kind", "little")]
        tag = Gtk.Label(label=f"{emoji} {title}", valign=Gtk.Align.CENTER)
        tag.add_css_class("tag")
        line.append(tag)
        names.append(line)
        self.played = Gtk.Label(xalign=0)
        names.append(self.played)
        header.append(names)
        extra = ui.big_button(_("+15 min"), "yes", "⏳")
        extra.connect("clicked", lambda *_args: self.grant(15))
        header.append(extra)
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

        policy = state.load_policy()
        minutes, hours, _bonus = state.effective_rules(kid, policy)

        rules = Gtk.Box(spacing=12)
        # A switch rather than "0 means no limit": parents stepping down to
        # 0 mean "no play today", and touch screens never show tooltips.
        self.limit_minutes = Gtk.Switch(active=minutes is not None, valign=Gtk.Align.CENTER)
        rules.append(self.limit_minutes)
        rules.append(Gtk.Label(label=_("Minutes a day")))
        self.minutes = spin(0, 24 * 60, 60 if minutes is None else minutes, 15)
        rules.append(self.minutes)
        rules.append(Gtk.Box(hexpand=True))
        self.limit_hours = Gtk.Switch(active=hours is not None, valign=Gtk.Align.CENTER)
        rules.append(self.limit_hours)
        rules.append(Gtk.Label(label=_("Only from")))
        hours = hours or {"start": "08:00", "end": "20:00"}
        # Half-hour steps, shown as clock times; the end can be 24:00.
        self.start = time_spin(0, 47, state.minutes_of_day(hours["start"]) // 30)
        self.end = time_spin(1, 48, state.minutes_of_day(hours["end"]) // 30)
        rules.append(self.start)
        rules.append(Gtk.Label(label="to"))
        rules.append(self.end)
        self.append(rules)
        self.message = ui.message_label()
        self.message.set_visible(False)
        self.append(self.message)

        self.minutes.set_sensitive(self.limit_minutes.get_active())
        self.limit_minutes.connect("notify::active", lambda *_args: self.save_minutes())
        self.minutes.connect("value-changed", lambda *_args: self.save_minutes())
        for widget in (self.start, self.end):
            widget.connect("value-changed", lambda *_args: self.save_hours())
        self.limit_hours.connect("notify::active", lambda *_args: self.save_hours())
        self.refresh()

    def _save(self, key, value):
        # Only the setting that changed is written: the other one keeps
        # following the configuration until a parent changes it here.
        policy = state.load_policy()
        policy.setdefault("kids", {}).setdefault(self.kid["user"], {})[key] = value
        state.save_policy(policy)

    def save_minutes(self):
        limited = self.limit_minutes.get_active()
        self.minutes.set_sensitive(limited)
        self._save("dailyMinutes", int(self.minutes.get_value()) if limited else None)

    def save_hours(self):
        self.message.set_visible(False)
        if not self.limit_hours.get_active():
            self._save("hours", None)
            return
        start, end = int(self.start.get_value()) * 30, int(self.end.get_value()) * 30
        if start == end:
            self.message.set_label(_("Pick different start and end times."))
            self.message.set_visible(True)
            return
        self._save(
            "hours",
            {"start": state.format_minutes_of_day(start), "end": state.format_minutes_of_day(end)},
        )

    def grant(self, minutes):
        try:
            state.grant_bonus(self.kid["user"], minutes)
        except OSError as error:
            self.message.set_label(_("Could not save: {reason}.").format(reason=error.strerror))
            self.message.set_visible(True)
            return
        # The timekeeper picks it up within seconds; say so right away.
        self.played.set_label(_("+{minutes} min added for today").format(minutes=minutes))

    def refresh(self):
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
        return GLib.SOURCE_CONTINUE


class Parent(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title=_("Zoomies grown-ups"))
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.add_css_class("page")

        top = Gtk.Box(spacing=20)
        top.append(ui.mascot(config, 72))
        title = Gtk.Label(label=_("Grown-ups"), xalign=0, hexpand=True)
        title.add_css_class("title")
        top.append(title)
        add = ui.big_button(_("Add a kid"), "yes", "➕")
        add.connect("clicked", lambda *_args: self.edit_kid(None))
        top.append(add)
        pin = ui.big_button(_("Change PIN"), "subtle", "🔑")
        pin.connect("clicked", lambda *_args: self.change_pin())
        top.append(pin)
        top.append(ui.clock())
        page.append(top)

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=self.list)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page.append(scroller)

        bottom = Gtk.Box(spacing=16)
        back = ui.big_button(_("Back to the kids"), "yes", "🐧")
        back.connect("clicked", lambda *_args: app.quit())
        bottom.append(back)
        terminal = ui.big_button(_("Terminal"), "subtle", "⌨")
        terminal.connect("clicked", lambda *_args: subprocess.Popen(["foot"]))
        bottom.append(terminal)
        bottom.append(Gtk.Box(hexpand=True))
        # Moving clouds and capes can distract some kids, and cost old PCs
        # without a GPU a lot of work.
        calm = Gtk.Switch(active=state.calm_screen(), valign=Gtk.Align.CENTER)
        calm.connect("notify::active", lambda switch, _pspec: state.set_calm_screen(switch.get_active()))
        bottom.append(calm)
        bottom.append(Gtk.Label(label=_("Calm screen")))
        restart = ui.big_button(_("Restart"), "subtle", "🔄")
        restart.connect(
            "clicked",
            lambda *_args: self.overlay.confirm(
                _("Restart the computer?"), "🔄", lambda: subprocess.Popen(["systemctl", "reboot"])
            ),
        )
        bottom.append(restart)
        power = ui.big_button(_("Power off"), "subtle", "⏻")
        power.connect(
            "clicked",
            lambda *_args: self.overlay.confirm(
                _("Turn the computer off?"), "🌙", lambda: subprocess.Popen(["systemctl", "poweroff"])
            ),
        )
        bottom.append(power)
        page.append(bottom)

        self.overlay = ui.Overlay(page)
        self.set_child(self.overlay)
        self.populate()
        GLib.timeout_add_seconds(5, self.refresh)

    def populate(self):
        self.config = state.load_config()
        while child := self.list.get_first_child():
            self.list.remove(child)
        self.rows = [KidRow(self, kid) for kid in self.config["kids"]]
        for row in self.rows:
            self.list.append(row)
        if not self.rows:
            empty = Gtk.Label(label=_("No kids yet. Press ➕ Add a kid."))
            empty.add_css_class("dialog-title")
            self.list.append(empty)

    def dialog(self, title, body, action, on_accept):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        label = Gtk.Label(label=title, justify=Gtk.Justification.CENTER)
        label.add_css_class("dialog-title")
        box.append(label)
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
            run = self.dialog(
                _("Add a kid"), form, _("Add"), lambda: admin.request("add-kid", **form.values())
            )
        else:
            run = self.dialog(
                _("Edit {name}").format(name=kid["name"]),
                form,
                _("Save"),
                lambda: admin.request("edit-kid", user=kid["user"], **form.values()),
            )
        form.name.connect("activate", run)
        form.name.grab_focus()

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
        for row in self.rows:
            row.refresh()
        return GLib.SOURCE_CONTINUE


def main():
    config = state.load_config()
    ui.run("org.zoomies.Parent", lambda app: Parent(app, config))
