"""The grown-ups' week: when each kid may play, special days and internet.

The week grid shows a row per weekday, with blocks of play time on a line
from midnight to midnight. Parents drag on a row to add time, drag a block
to move it or its edges to resize it, and tap a block or a weekday for the
rest; every tap target also works with the keyboard.
"""

import datetime
import math

import gi

from . import state, ui
from .i18n import _
from .ui import GLib, Gtk

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

STEP = state.STEP
DAY = state.DAY
WORKDAYS = state.WORKDAYS
WEEKEND = state.WEEKEND

# Daily minutes the − and + buttons step through; past the last one there
# is no cap.
CAPS = [m for m in range(0, 4 * 60, 15)] + [m for m in range(4 * 60, 8 * 60 + 1, 30)]

PLAY = (0x8B / 255, 0xE2 / 255, 0x8B / 255)
INK = (0x1D / 255, 0x35 / 255, 0x57 / 255)
NO_PLAY = (1.0, 0x8A / 255, 0x80 / 255)
NOW = (0xE6 / 255, 0x39 / 255, 0x46 / 255)

# How long the offer to change the other days too stays up.
OFFER_SECONDS = 8


def weekday_name(index):
    return _(state.WEEKDAY_NAMES[index])


def short_weekday(index):
    return _(state.WEEKDAY_SHORT[index])


def cap_label(minutes):
    if minutes is None:
        return "∞"
    if minutes == 0:
        return "0"
    return state.format_duration(minutes * 60)


def next_cap(minutes, direction):
    if minutes is None:
        return CAPS[-1] if direction < 0 else None
    later = [m for m in CAPS if m > minutes]
    earlier = [m for m in CAPS if m < minutes]
    if direction > 0:
        return later[0] if later else None
    return earlier[-1] if earlier else 0


def time_spin(value, low=0, high=48):
    """Half-hour steps, shown as clock times; 48 is 24:00."""
    button = Gtk.SpinButton.new_with_range(low, high, 1)
    button.set_value(value / STEP)
    button.set_valign(Gtk.Align.CENTER)
    button.set_numeric(False)
    button.set_width_chars(5)

    def output(widget):
        widget.set_text(state.format_minutes_of_day(int(widget.get_value()) * STEP))
        return True

    def parse(widget):
        try:
            return True, state.minutes_of_day(widget.get_text()) / STEP
        except ValueError:
            return False, 0

    button.connect("output", output)
    button.connect("input", parse)
    output(button)
    return button


def rounded(cr, x, y, width, height, radius):
    radius = min(radius, width / 2, height / 2)
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def text(cr, label, x, y, width, height, size=11, bold=True, color=INK):
    """Centre a label in a box, or leave it out if it does not fit."""
    layout = PangoCairo.create_layout(cr)
    font = Pango.FontDescription.from_string(f"Andika {'Bold ' if bold else ''}{size}")
    layout.set_font_description(font)
    layout.set_text(label, -1)
    w, h = layout.get_pixel_size()
    if w > width - 6:
        return False
    cr.set_source_rgb(*color)
    cr.move_to(x + (width - w) / 2, y + (height - h) / 2)
    PangoCairo.show_layout(cr, layout)
    return True


class DayTrack(Gtk.DrawingArea):
    """One weekday's line of play time."""

    HANDLE = 16
    HEIGHT = 48

    def __init__(self, grid, index):
        super().__init__(hexpand=True, content_height=self.HEIGHT)
        self.grid = grid
        self.index = index
        self.preview = None
        self.drag = None
        self.set_draw_func(self.draw)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.begin)
        drag.connect("drag-update", self.update)
        drag.connect("drag-end", self.end)
        # The page took the touch to scroll.
        drag.connect("cancel", lambda *_args: setattr(self, "drag", None))
        self.add_controller(drag)

    @property
    def day(self):
        return self.grid.days[self.index]

    def x_of(self, minute):
        return minute / DAY * self.get_width()

    def minute_at(self, x):
        minute = round(x / max(1, self.get_width()) * DAY / STEP) * STEP
        return min(DAY, max(0, minute))

    def hit(self, x):
        """The block under x and which part of it: start, end or move."""
        for i, (start, end) in enumerate(self.day["blocks"]):
            left, right = self.x_of(start), self.x_of(end)
            if left - self.HANDLE / 2 <= x <= right + self.HANDLE / 2:
                # Small blocks keep a middle to move them by.
                handle = min(self.HANDLE, (right - left) / 3)
                if x <= left + handle:
                    return i, "start"
                if x >= right - handle:
                    return i, "end"
                return i, "move"
        return None, "new"

    def begin(self, gesture, x, _y):
        i, part = self.hit(x) if self.day is not None else (None, "menu")
        self.drag = {"x": x, "i": i, "part": part, "moved": False, "minute": self.minute_at(x)}

    def update(self, gesture, dx, dy):
        drag = self.drag
        if drag is None or drag["part"] == "menu":
            return
        if not drag["moved"]:
            if abs(dy) > 8 and abs(dy) > abs(dx):
                # Scrolling the page, not a tap.
                self.drag = None
                return
            if abs(dx) < 8:
                return
            drag["moved"] = True
            # A sideways drag is ours; up and down still scroll the page.
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        blocks = list(self.day["blocks"])
        minute = self.minute_at(drag["x"] + dx)
        if drag["part"] == "new":
            anchor = drag["minute"]
            # Started at the very end of the day, the block grows backwards.
            blocks.append(state.clamp_block(min(anchor, minute), max(anchor, minute)))
        else:
            start, end = blocks[drag["i"]]
            if drag["part"] == "start":
                start = min(minute, end - STEP)
            elif drag["part"] == "end":
                end = max(minute, start + STEP)
            else:
                shift = minute - drag["minute"]
                shift = min(DAY - end, max(-start, shift))
                start, end = start + shift, end + shift
            blocks[drag["i"]] = state.clamp_block(start, end)
        self.preview = blocks
        self.queue_draw()

    def end(self, _gesture, _dx, _dy):
        drag, self.drag = self.drag, None
        if drag is None:
            return
        if drag["part"] == "menu":
            self.grid.day_menu(self.index)
        elif drag["moved"]:
            blocks, self.preview = self.preview, None
            self.grid.set_blocks(self.index, blocks)
        elif drag["i"] is not None:
            self.grid.block_menu(self.index, drag["i"])
        else:
            # A tap on an empty spot adds an hour there.
            start = min(DAY - 60, drag["minute"] // 60 * 60)
            self.grid.set_blocks(self.index, [*self.day["blocks"], (start, start + 60)])

    def draw(self, _area, cr, width, height):
        rounded(cr, 0, 0, width, height, 14)
        if self.day is None:
            cr.set_source_rgba(*NO_PLAY, 0.25)
            cr.fill()
            text(cr, _("🚫 No play · tap to allow"), 0, 0, width, height, 12, color=(0.7, 0.23, 0.23))
            return
        cr.set_source_rgba(*INK, 0.06)
        cr.fill()
        cr.set_source_rgba(*INK, 0.12)
        for hour in range(1, 24):
            x = round(self.x_of(hour * 60)) + 0.5
            cr.move_to(x, 6)
            cr.line_to(x, height - 6)
        cr.set_line_width(1)
        cr.stroke()
        for start, end in self.preview or self.day["blocks"]:
            left, right = self.x_of(start), self.x_of(end)
            rounded(cr, left + 1, 5, right - left - 2, height - 10, 10)
            cr.set_source_rgb(*PLAY)
            cr.fill()
            begins = state.format_minutes_of_day(start)
            label = f"{begins}–{state.format_minutes_of_day(end)}"
            # Short blocks show when they start, if even that fits.
            if not text(cr, label, left, 5, right - left, height - 10, 10):
                text(cr, begins, left, 5, right - left, height - 10, 9)
            # The handles say the edges can be dragged.
            cr.set_source_rgba(*INK, 0.35)
            for x in (left + 6, right - 9):
                if right - left > 30:
                    rounded(cr, x, height * 0.35, 3, height * 0.3, 1.5)
                    cr.fill()
        now = datetime.datetime.now()
        if now.weekday() == self.index:
            x = self.x_of(now.hour * 60 + now.minute)
            cr.set_source_rgb(*NOW)
            cr.rectangle(x - 1.5, 0, 3, height)
            cr.fill()


class HourScale(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(hexpand=True, content_height=20)
        self.set_draw_func(self.draw)

    def draw(self, _area, cr, width, height):
        for hour in range(0, 25, 3):
            x = hour / 24 * width
            # The ends stay inside the line.
            left = min(max(0, x - 20), width - 40)
            text(cr, f"{hour}h", left, 0, 40, height, 9, bold=False, color=(0.24, 0.35, 0.5))


class WeekGrid(Gtk.Box):
    """A kid's week of play time; every change is saved at once."""

    # Fixed widths for the weekday and the cap, so the lines of every row
    # and the hour scale above them line up.
    LABEL_WIDTH = 84
    CAP_WIDTH = 190

    def __init__(self, panel, kid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.panel = panel
        self.kid = kid
        self.days = state.week(kid, state.load_policy())
        self.tracks = []
        self.caps = []
        self.offers = []
        self.offer_timer = None
        header = Gtk.Box(spacing=10)
        header.append(Gtk.Box(width_request=self.LABEL_WIDTH))
        header.append(HourScale())
        header.append(
            Gtk.Label(
                label=_("Max a day"), css_classes=["hint"], xalign=1, width_request=self.CAP_WIDTH
            )
        )
        self.append(header)
        today = datetime.date.today().weekday()
        for index in range(state.WEEKDAYS):
            row = Gtk.Box(spacing=10)
            label = Gtk.Button(
                label=short_weekday(index), valign=Gtk.Align.CENTER, width_request=self.LABEL_WIDTH
            )
            label.add_css_class("day-label")
            if index == today:
                label.add_css_class("today")
            label.set_tooltip_text(weekday_name(index))
            label.connect("clicked", lambda _b, i=index: self.day_menu(i))
            row.append(label)
            track = DayTrack(self, index)
            self.tracks.append(track)
            row.append(track)
            cap = Gtk.CenterBox(
                valign=Gtk.Align.CENTER, width_request=self.CAP_WIDTH, hexpand=False
            )
            less = Gtk.Button(label="−", css_classes=["cap-step"])
            value = Gtk.Label(css_classes=["cap"])
            more = Gtk.Button(label="+", css_classes=["cap-step"])
            less.connect("clicked", lambda _b, i=index: self.step_cap(i, -1))
            more.connect("clicked", lambda _b, i=index: self.step_cap(i, 1))
            cap.set_start_widget(less)
            cap.set_center_widget(value)
            cap.set_end_widget(more)
            self.caps.append((cap, value))
            row.append(cap)
            self.append(row)
            offer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
            self.offers.append(offer)
            self.append(offer)
        self.redraw()

    def redraw(self):
        for track, (cap, value), day in zip(self.tracks, self.caps, self.days, strict=True):
            track.queue_draw()
            cap.set_sensitive(day is not None)
            value.set_label("—" if day is None else cap_label(day["minutes"]))

    def fresh(self):
        """The week as saved now: another screen or a terminal may have
        changed it, and saving a stale copy would undo that."""
        try:
            self.days = state.week(self.kid, state.load_policy())
        except ValueError as error:
            self.panel.show_error(error)

    def save(self):
        try:
            state.save_week(self.kid["user"], self.days)
        except (OSError, ValueError) as error:
            self.panel.show_error(error)
            self.fresh()
        self.redraw()

    def set_blocks(self, index, blocks):
        self.fresh()
        day = self.days[index]
        if day is None:
            self.redraw()
            return
        blocks = [state.clamp_block(start, end) for start, end in blocks]
        self.days[index] = {"blocks": state.merge_blocks(blocks), "minutes": day["minutes"]}
        self.save()

    def step_cap(self, index, direction):
        self.fresh()
        day = self.days[index]
        if day is not None:
            self.days[index] = {**day, "minutes": next_cap(day["minutes"], direction)}
            self.save()
            self.offer_same(index)

    def offer_same(self, index):
        """After one day's time changes, offer it to the days of its kind:
        days of a kind usually share their time, and changing five days one
        by one is tedious."""
        self.hide_offers()
        if self.days[index] is None or not state.differing_minutes(self.days, index):
            return
        minutes = cap_label(self.days[index]["minutes"])
        question = (
            _("Every weekday {time}?") if index in WORKDAYS else _("Every weekend day {time}?")
        ).format(time=minutes)
        bar = Gtk.Box(spacing=12, css_classes=["offer"])
        bar.set_margin_start(self.LABEL_WIDTH + 10)
        bar.append(Gtk.Label(label=question, xalign=0, hexpand=True, css_classes=["offer-text"]))
        yes = ui.big_button(_("Yes"), "yes", "✔")
        yes.add_css_class("small")
        yes.connect("clicked", lambda *_args: self.same_minutes(index))
        bar.append(yes)
        only = ui.big_button(_("Only {day}").format(day=short_weekday(index)), "subtle")
        only.add_css_class("small")
        only.connect("clicked", lambda *_args: self.hide_offers())
        bar.append(only)
        self.offers[index].set_child(bar)
        self.offers[index].set_reveal_child(True)
        self.offer_timer = GLib.timeout_add_seconds(OFFER_SECONDS, self.hide_offers)

    def hide_offers(self):
        if self.offer_timer is not None:
            GLib.source_remove(self.offer_timer)
            self.offer_timer = None
        for offer in self.offers:
            offer.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def same_minutes(self, index):
        self.hide_offers()
        self.fresh()
        if self.days[index] is not None:
            self.days = state.with_minutes(self.days, index)
            self.save()

    def copy_day(self, index, targets):
        self.hide_offers()
        self.fresh()
        for target in targets:
            day = self.days[index]
            self.days[target] = None if day is None else dict(day, blocks=list(day["blocks"]))
        self.save()

    def day_menu(self, index):
        self.fresh()
        self.redraw()
        day = self.days[index]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(Gtk.Label(label=weekday_name(index), css_classes=["dialog-title"]))
        actions = []
        if day is not None:
            for i, (start, end) in enumerate(day["blocks"]):
                label = f"{state.format_minutes_of_day(start)}–{state.format_minutes_of_day(end)}"
                actions.append((label, "subtle", "✏️", lambda i=i: self.block_menu(index, i)))
            actions.append((_("Add play time"), "yes", "➕", lambda: self.add_block(index)))
        actions += [
            (_("Copy to Monday–Friday"), "subtle", "📋", lambda: self.copy_day(index, WORKDAYS)),
            (_("Copy to every day"), "subtle", "📋", lambda: self.copy_day(index, range(7))),
        ]
        if day is None:
            actions.append((_("Allow play this day"), "yes", "✅", lambda: self.allow_day(index)))
        else:
            actions.append((_("No play this day"), "no", "🚫", lambda: self.forbid_day(index)))
        self.panel.menu(box, actions)

    def allow_day(self, index):
        self.fresh()
        self.days[index] = state.like_neighbour(self.days, index)
        self.save()

    def forbid_day(self, index):
        self.fresh()
        self.days[index] = None
        self.save()

    def add_block(self, index):
        self.fresh()
        if self.days[index] is None:
            return
        blocks = self.days[index]["blocks"]
        # The first free hour from the afternoon on, else from the morning.
        for start in [*range(16 * 60, DAY, 60), *range(0, 16 * 60, 60)]:
            if all(end <= start or start + 60 <= s for s, end in blocks):
                self.set_blocks(index, [*blocks, (start, start + 60)])
                return

    def block_menu(self, index, i):
        start, end = self.days[index]["blocks"][i]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.append(Gtk.Label(label=weekday_name(index), css_classes=["dialog-title"]))
        times = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        start_spin = time_spin(start, 0, 47)
        end_spin = time_spin(end, 1, 48)
        times.append(start_spin)
        # Translators: between the start and the end of a time to play.
        times.append(Gtk.Label(label=_("to")))
        times.append(end_spin)
        box.append(times)
        group = state.same_kind(index)
        everywhere = Gtk.CheckButton(
            label=_("Same on every weekday")
            if index in WORKDAYS
            else _("Same on every weekend day"),
            halign=Gtk.Align.CENTER,
        )
        box.append(everywhere)
        message = ui.message_label()
        box.append(message)

        def save():
            new = (int(start_spin.get_value()) * STEP, int(end_spin.get_value()) * STEP)
            if new[1] <= new[0]:
                message.set_label(_("The end must come after the start."))
                return False
            targets = group if everywhere.get_active() else [index]
            self.fresh()
            blocks = self.days[index]["blocks"] if self.days[index] else []
            if (start, end) not in blocks:
                # Changed meanwhile somewhere else: show that instead.
                self.redraw()
                return True
            self.days = state.retime(self.days, index, blocks.index((start, end)), new, targets)
            self.save()
            return True

        def remove():
            self.fresh()
            blocks = list(self.days[index]["blocks"]) if self.days[index] else []
            if (start, end) in blocks:
                blocks.remove((start, end))
                self.set_blocks(index, blocks)
            return True

        self.panel.ask(box, [(_("Remove"), "no", "🗑️", remove), (_("Save"), "yes", "✔", save)])


class InternetBox(Gtk.Box):
    """Whether a kid may be online, on which days, or for a while now."""

    def __init__(self, panel, kid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.panel = panel
        self.kid = kid
        policy = state.load_policy()
        self.rules = state.internet_rules(kid, policy)

        top = Gtk.Box(spacing=12)
        top.append(Gtk.Label(label=_("🌐 Internet"), css_classes=["section-title"]))
        self.switch = Gtk.Switch(active=self.rules["on"], valign=Gtk.Align.CENTER)
        self.switch.connect("notify::active", lambda *_args: self.save())
        top.append(self.switch)
        self.summary = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        top.append(self.summary)
        self.append(top)

        self.chips = Gtk.Box(spacing=8)
        self.days = []
        for index in range(state.WEEKDAYS):
            chip = Gtk.ToggleButton(active=self.rules["days"][index])
            chip.add_css_class("chip")
            chip.set_child(Gtk.Label(label=short_weekday(index)))
            chip.set_tooltip_text(weekday_name(index))
            chip.connect("toggled", lambda *_args: self.save())
            self.days.append(chip)
            self.chips.append(chip)
        self.append(self.chips)

        unlock = Gtk.Box(spacing=12)
        self.status = Gtk.Label(xalign=0, css_classes=["net-status"])
        unlock.append(self.status)
        unlock.append(Gtk.Box(hexpand=True))
        self.open_buttons = []
        for text_, minutes in ((_("30 min"), 30), (_("1 hour"), 60), (_("Rest of today"), None)):
            button = ui.big_button(text_, "net", "🌐")
            button.add_css_class("small")
            button.connect("clicked", lambda _b, m=minutes: self.open_for(m))
            self.open_buttons.append(button)
            unlock.append(button)
        self.close_button = ui.big_button(_("Turn off now"), "no", "🔒")
        self.close_button.add_css_class("small")
        self.close_button.connect("clicked", lambda *_args: self.open_for(0))
        unlock.append(self.close_button)
        self.append(unlock)
        self.refresh()

    def save(self):
        self.rules = {"on": self.switch.get_active(), "days": [c.get_active() for c in self.days]}
        try:
            state.set_kid_rule(self.kid["user"], "internet", self.rules)
        except (OSError, ValueError) as error:
            self.panel.show_error(error)
        self.refresh()

    def open_for(self, minutes):
        now = datetime.datetime.now()
        if minutes == 0:
            until = None
        elif minutes is None:
            until = datetime.datetime.combine(
                now.date() + datetime.timedelta(days=1), datetime.time()
            )
        else:
            until = now + datetime.timedelta(minutes=minutes)
        try:
            state.open_internet(self.kid["user"], until)
        except (OSError, ValueError) as error:
            self.panel.show_error(error)
        self.refresh()

    def refresh(self):
        on = self.rules["on"]
        self.chips.set_visible(on)
        self.summary.set_label(
            _("Online during play time on these days:")
            if on
            else _("Off: only what is on this computer")
        )
        policy = state.load_policy()
        until = state.internet_until(self.kid, policy)
        now = datetime.datetime.now()
        opened = until is not None and until > now
        if opened:
            left = state.format_duration(int((until - now).total_seconds()))
            self.status.set_label(_("🌐 Open for {time} more").format(time=left))
        elif state.internet_today(self.kid, policy, now):
            self.status.set_label(_("🌐 Online today"))
        else:
            self.status.set_label(_("🎮 Offline today"))
        for button in self.open_buttons:
            button.set_visible(not opened)
        self.close_button.set_visible(opened)


class SpecialDays(Gtk.Box):
    """Dates that play like another weekday, or not at all."""

    def __init__(self, panel, kid):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.panel = panel
        self.kid = kid
        top = Gtk.Box(spacing=12)
        top.append(
            Gtk.Label(
                label=_("📅 Special days"), css_classes=["section-title"], hexpand=True, xalign=0
            )
        )
        add = ui.big_button(_("Add"), "subtle", "➕")
        add.add_css_class("small")
        add.connect("clicked", lambda *_args: self.add())
        top.append(add)
        self.append(top)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.list)
        self.populate()

    def special(self):
        return {
            d: like
            for d, like in state.special_days(self.kid, state.load_policy()).items()
            if d >= state.today()
        }

    def populate(self):
        while child := self.list.get_first_child():
            self.list.remove(child)
        special = self.special()
        if not special:
            self.list.append(
                Gtk.Label(
                    label=_("Holidays or trips: a special day replaces its weekday once."),
                    xalign=0,
                    css_classes=["hint"],
                )
            )
        for date, like in sorted(special.items()):
            row = Gtk.Box(spacing=12)
            day = datetime.date.fromisoformat(date)
            # The month by name, in the session's language: 03/04 reads
            # differently around the world.
            when = GLib.DateTime.new_local(day.year, day.month, day.day, 0, 0, 0).format("%a %e %b")
            row.append(Gtk.Label(label=when, css_classes=["tag"]))
            what = (
                _("🚫 No play")
                if like == "off"
                else _("Like a {day}").format(day=weekday_name(like))
            )
            row.append(Gtk.Label(label=what, hexpand=True, xalign=0))
            remove = ui.big_button(None, "subtle", "🗑️")
            remove.add_css_class("small")
            remove.set_tooltip_text(_("Remove"))
            remove.connect("clicked", lambda _b, d=date: self.remove(d))
            row.append(remove)
            self.list.append(row)

    def save(self, special):
        try:
            state.save_special_days(self.kid["user"], special)
        except (OSError, ValueError) as error:
            self.panel.show_error(error)
        self.populate()
        self.panel.schedule_changed(self.kid)

    def remove(self, date):
        special = self.special()
        special.pop(date, None)
        self.save(special)

    def add(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.append(
            Gtk.Label(
                label=_("📅 A special day for {name}").format(name=self.kid["name"]),
                css_classes=["dialog-title"],
            )
        )
        calendar = Gtk.Calendar(halign=Gtk.Align.CENTER)
        box.append(calendar)
        box.append(Gtk.Label(label=_("Plays like:")))
        choices = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        buttons = {}
        for like in [*range(state.WEEKDAYS), "off"]:
            button = Gtk.ToggleButton(label="🚫" if like == "off" else short_weekday(like))
            button.add_css_class("chip")
            if buttons:
                button.set_group(next(iter(buttons.values())))
            buttons[like] = button
            choices.append(button)
        buttons[5].set_active(True)
        box.append(choices)
        message = ui.message_label()
        box.append(message)

        def accept():
            picked = calendar.get_date()
            date = datetime.date(picked.get_year(), picked.get_month(), picked.get_day_of_month())
            if date.isoformat() < state.today():
                message.set_label(_("Pick today or a day to come."))
                return False
            like = next(k for k, b in buttons.items() if b.get_active())
            self.save({**self.special(), date.isoformat(): like})
            return True

        self.panel.ask(box, [(_("Add"), "yes", "✔", accept)])
