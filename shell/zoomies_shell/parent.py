"""Grown-ups' panel: screen time rules, extra time, and the way out."""

import subprocess
import sys

from . import state, ui
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
    def __init__(self, kid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.kid = kid
        self.add_css_class("parent-row")

        header = Gtk.Box(spacing=20)
        header.append(ui.avatar(kid, "small"))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        name = Gtk.Label(label=kid["name"], xalign=0)
        name.add_css_class("kid-name")
        names.append(name)
        self.played = Gtk.Label(xalign=0)
        names.append(self.played)
        header.append(names)
        extra = ui.big_button("+15 min today", "yes", "⏳")
        extra.connect("clicked", lambda *_: self.grant(15))
        header.append(extra)
        self.append(header)

        policy = state.load_policy()
        minutes, hours, _bonus = state.effective_rules(kid, policy)

        rules = Gtk.Box(spacing=12)
        # A switch rather than "0 means no limit": parents stepping down to
        # 0 mean "no play today", and touch screens never show tooltips.
        self.limit_minutes = Gtk.Switch(active=minutes is not None, valign=Gtk.Align.CENTER)
        rules.append(self.limit_minutes)
        rules.append(Gtk.Label(label="Minutes a day"))
        self.minutes = spin(0, 24 * 60, 60 if minutes is None else minutes, 15)
        rules.append(self.minutes)
        rules.append(Gtk.Box(hexpand=True))
        self.limit_hours = Gtk.Switch(active=hours is not None, valign=Gtk.Align.CENTER)
        rules.append(self.limit_hours)
        rules.append(Gtk.Label(label="Only from"))
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
        self.limit_minutes.connect("notify::active", lambda *_: self.save_minutes())
        self.minutes.connect("value-changed", lambda *_: self.save_minutes())
        for widget in (self.start, self.end):
            widget.connect("value-changed", lambda *_: self.save_hours())
        self.limit_hours.connect("notify::active", lambda *_: self.save_hours())
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
            self.message.set_label("Pick different start and end times.")
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
            self.message.set_label(f"Could not save: {error.strerror}.")
            self.message.set_visible(True)
            return
        # The timekeeper picks it up within seconds; say so right away.
        self.played.set_label(f"+{minutes} min added for today")

    def refresh(self):
        status = state.read_status().get(self.kid["user"], {})
        used = status.get("used", 0) // 60
        remaining = status.get("remaining")
        text = f"Played {used} min today"
        if remaining is not None:
            text += f", {state.format_duration(remaining)} left"
        elif status:
            text += ", no limit"
        if status and not status["allowed"]:
            text += " (resting)"
        self.played.set_label(text)
        return GLib.SOURCE_CONTINUE


class Parent(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title="Zoomies grown-ups")
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.add_css_class("page")

        top = Gtk.Box(spacing=20)
        top.append(ui.mascot(config, 72))
        title = Gtk.Label(label="Grown-ups", xalign=0, hexpand=True)
        title.add_css_class("title")
        top.append(title)
        top.append(ui.clock())
        page.append(top)

        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.rows = [KidRow(kid) for kid in config["kids"]]
        for row in self.rows:
            rows.append(row)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=rows)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page.append(scroller)

        hint = Gtk.Label(
            label="To change the PIN, open the terminal and run passwd.",
            xalign=0,
        )
        hint.add_css_class("kid-note")
        page.append(hint)

        bottom = Gtk.Box(spacing=16)
        back = ui.big_button("Back to the kids", "yes", "🐧")
        back.connect("clicked", lambda *_: app.quit())
        bottom.append(back)
        terminal = ui.big_button("Terminal", "subtle", "⌨")
        terminal.connect("clicked", lambda *_: subprocess.Popen(["foot"]))
        bottom.append(terminal)
        bottom.append(Gtk.Box(hexpand=True))
        restart = ui.big_button("Restart", "subtle", "🔄")
        restart.connect(
            "clicked",
            lambda *_: self.overlay.confirm(
                "Restart the computer?", "🔄", lambda: subprocess.Popen(["systemctl", "reboot"])
            ),
        )
        bottom.append(restart)
        power = ui.big_button("Power off", "subtle", "⏻")
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
        GLib.timeout_add_seconds(5, self.refresh)

    def refresh(self):
        for row in self.rows:
            row.refresh()
        return GLib.SOURCE_CONTINUE


def main():
    config = state.load_config()
    app = Gtk.Application(application_id="org.zoomies.Parent")

    def activate(app):
        ui.load_css()
        window = Parent(app, config)
        window.fullscreen()
        window.present()

    app.connect("activate", activate)
    sys.exit(app.run(None))
