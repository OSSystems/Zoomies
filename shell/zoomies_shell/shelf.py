"""The older kids' shelf, the bar along the bottom of their desktop. It
takes the place of the Xfce panel, which is made for grown-ups.

The Apps button opens the apps a kid may start, the games on a page of
their own. The apps running sit next to it, the one in front with its
name; tapping another brings it to the front. Every app fills the screen
above the shelf and stays that way: kids find their way between full screen
apps more easily than between overlapping windows. The remaining time, the
clock, switching player and turning off sit on the right.
"""

import os
import subprocess
import sys

import gi

from . import apps, art, state
from .i18n import N_, _, ngettext

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkPixbuf, GdkX11, Gio, GLib, Gtk, Pango, Wnck  # noqa: E402
from Xlib import Xatom  # noqa: E402
from Xlib import display as xdisplay  # noqa: E402

HEIGHT = 80
ICON = 48
TILE_ICON = 64
GAME_ICON = 96
GAP = 16
# Desktop entry categories, in the order the panel shows them; apps in none
# of them land in the last group.
GROUPS = (
    (N_("Write and study"), {"Office", "Education", "Science", "Math", "Languages", "Geography"}),
    (N_("Create"), {"Graphics", "AudioVideo", "Audio", "Video"}),
)
# What the default apps are for, in a kid's words: their own generic names
# ("Word Processor", "Spreadsheet") are written for grown-ups. Apps a parent
# adds fall back to theirs. Keyed by desktop entry file name.
WHAT = {
    "calc.desktop": N_("Make tables"),
    "firefox.desktop": N_("Visit websites"),
    "impress.desktop": N_("Make slideshows"),
    "org.audacityteam.Audacity.desktop": N_("Record sounds"),
    "org.kde.kgeography.desktop": N_("Learn about countries"),
    "org.kde.krita.desktop": N_("Paint pictures"),
    "org.kde.ktouch.desktop": N_("Learn to type"),
    "org.stellarium.Stellarium.desktop": N_("Explore the sky"),
    "thunar.desktop": N_("Find your files"),
    "writer.desktop": N_("Write stories"),
}


def css():
    provider = Gtk.CssProvider()
    provider.load_from_path(os.path.join(os.path.dirname(__file__), "shelf.css"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def monitor():
    display = Gdk.Display.get_default()
    return display.get_primary_monitor() or display.get_monitor(0)


def now(window):
    """The X server time: window managers ignore requests without one."""
    return GdkX11.x11_get_server_time(window.get_window())


def label(text, css_class, **kwargs):
    widget = Gtk.Label(label=text, **kwargs)
    widget.get_style_context().add_class(css_class)
    return widget


def icon(info, size, fallback="application-x-executable"):
    image = Gtk.Image()
    gicon = info.get_icon() if info else None
    # A themed name nobody ships would show the broken-image icon.
    theme = Gtk.IconTheme.get_default()
    if gicon is None or (isinstance(gicon, Gio.ThemedIcon) and not theme.lookup_by_gicon(gicon, size, 0)):
        image.set_from_icon_name(fallback, Gtk.IconSize.DIALOG)
    else:
        image.set_from_gicon(gicon, Gtk.IconSize.DIALOG)
    image.set_pixel_size(size)
    return image


def tile(info, size, name=None, what=None, fallback="application-x-executable"):
    button = Gtk.Button()
    button.get_style_context().add_class("tile")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.pack_start(icon(info, size, fallback), False, False, 0)
    text = label(name or info.get_name(), "tile-name", justify=Gtk.Justification.CENTER)
    text.set_line_wrap(True)
    text.set_max_width_chars(12)
    box.pack_start(text, False, False, 0)
    if what is None and info is not None:
        what = WHAT.get(os.path.basename(info.get_filename() or ""))
        what = _(what) if what else info.get_generic_name() or ""
    if what:
        # Two lines fit the longer translations without cutting them.
        note = label(what, "tile-what", ellipsize=Pango.EllipsizeMode.END, justify=Gtk.Justification.CENTER)
        note.set_line_wrap(True)
        note.set_lines(2)
        note.set_max_width_chars(14)
        box.pack_start(note, False, False, 0)
    button.add(box)
    return button


def tiles():
    return Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        homogeneous=True,
        min_children_per_line=3,
        max_children_per_line=6,
        column_spacing=GAP,
        row_spacing=GAP,
    )


class Popup(Gtk.Window):
    """A rounded card above the shelf that goes away when the kid clicks
    elsewhere or presses Escape."""

    def __init__(self, shelf, title):
        super().__init__(title=title)
        self.shelf = shelf
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_transient_for(shelf)
        self.hidden_at = 0
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)
        else:
            self.get_style_context().add_class("flat")
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.card.get_style_context().add_class("card")
        self.add(self.card)
        self.connect("key-press-event", self._key)
        self.connect("focus-out-event", lambda *_args: self.close_card())
        self.connect("delete-event", lambda *_args: self.close_card() or True)

    def _key(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close_card()
            return True
        return False

    def open_card(self):
        geometry = monitor().get_geometry()
        self.card.show_all()
        width = min(self.get_preferred_width()[1], geometry.width - 2 * GAP)
        height = min(self.get_preferred_height_for_width(width)[1], geometry.height - HEIGHT - 2 * GAP)
        self.resize(width, height)
        self.move(
            geometry.x + (geometry.width - width) // 2,
            geometry.y + geometry.height - HEIGHT - GAP - height,
        )
        self.show()
        self.present_with_time(now(self.shelf))

    def close_card(self):
        if self.get_visible():
            self.hidden_at = GLib.get_monotonic_time()
            self.hide()

    def just_closed(self):
        """Clicking the shelf takes the focus first: a click on the button
        that opened the card closes it rather than opening it again."""
        return GLib.get_monotonic_time() - self.hidden_at < 300_000


class AppsPanel(Popup):
    def __init__(self, shelf, entries, games):
        super().__init__(shelf, _("Apps"))
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        # Small screens scroll the card rather than lose its bottom.
        scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
            propagate_natural_width=True,
        )
        scroller.add(self.stack)
        self.card.pack_start(scroller, True, True, 0)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.pack_start(label(_("What do you want to do?"), "card-title", xalign=0), False, False, 0)
        groups = [(_(name), cats, []) for name, cats in GROUPS]
        rest = []
        for info in entries:
            categories = set(filter(None, (info.get_categories() or "").split(";")))
            target = next((g for _name, cats, g in groups if categories & cats), rest)
            target.append(info)
        last = _("Internet, files and games") if games else _("Internet and files")
        self.first = None
        for name, _cats, members in [*groups, (last, None, rest)]:
            extra = name == last and games
            if not members and not extra:
                continue
            page.pack_start(label(name, "group-title", xalign=0), False, False, 0)
            flow = tiles()
            for info in members:
                button = tile(info, TILE_ICON)
                button.connect("clicked", lambda _b, i=info: self.start(i))
                flow.add(button)
                self.first = self.first or button
            if extra:
                inside = ngettext("{count} game inside", "{count} games inside", len(games)).format(count=len(games))
                button = tile(None, TILE_ICON, _("Games ›"), inside, "applications-games")
                button.get_style_context().add_class("games")
                button.connect("clicked", lambda *_args: self.show_games())
                flow.add(button)
                self.games_button = button
                self.first = self.first or button
            page.pack_start(flow, False, False, 0)
        # As wide as the biggest group, so a few apps do not sit in a wide
        # empty card.
        flows = [c for c in page.get_children() if isinstance(c, Gtk.FlowBox)]
        columns = max([3, *(min(6, len(f.get_children())) for f in flows)])
        for flow in flows:
            flow.set_min_children_per_line(columns)
            flow.set_max_children_per_line(columns)
        if self.first is None:
            page.pack_start(
                label(_("No apps here yet.\nAsk a grown-up to add some!"), "group-title"), False, False, 0
            )
        self.stack.add_named(page, "apps")

        if games:
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            top = Gtk.Box(spacing=16)
            back = Gtk.Button(label=_("← All apps"))
            back.get_style_context().add_class("back")
            back.connect("clicked", lambda *_args: self.show_apps())
            top.pack_start(back, False, False, 0)
            top.pack_start(label(_("Games"), "card-title", xalign=0), False, False, 0)
            page.pack_start(top, False, False, 0)
            flow = tiles()
            flow.set_min_children_per_line(min(4, max(3, len(games))))
            flow.set_max_children_per_line(min(4, max(3, len(games))))
            self.first_game = None
            for info in games:
                button = tile(info, GAME_ICON, what="")
                button.get_style_context().add_class("game")
                button.connect("clicked", lambda _b, i=info: self.start(i))
                flow.add(button)
                self.first_game = self.first_game or button
            page.pack_start(flow, False, False, 0)
            self.stack.add_named(page, "games")

    def _key(self, window, event):
        if event.keyval == Gdk.KEY_Escape and self.stack.get_visible_child_name() == "games":
            self.show_apps()
            return True
        return super()._key(window, event)

    def open_card(self):
        self.stack.set_visible_child_name("apps")
        super().open_card()
        if self.first:
            self.first.grab_focus()

    def show_games(self):
        self.stack.set_visible_child_name("games")
        self.first_game.grab_focus()

    def show_apps(self):
        self.stack.set_visible_child_name("apps")
        self.games_button.grab_focus()

    def start(self, info):
        context = Gdk.Display.get_default().get_app_launch_context()
        context.set_timestamp(now(self.shelf))
        try:
            info.launch([], context)
        except GLib.Error as error:
            print(f"cannot start {info.get_name()}: {error.message}", file=sys.stderr)
            return
        self.close_card()


class Ask(Popup):
    def __init__(self, shelf, question, yes, on_yes):
        super().__init__(shelf, question)
        self.card.pack_start(label(question, "card-title"), False, False, 0)
        buttons = Gtk.Box(spacing=GAP, halign=Gtk.Align.CENTER)
        no = Gtk.Button(label=_("No"))
        no.get_style_context().add_class("answer")
        no.connect("clicked", lambda *_args: self.close_card())
        button = Gtk.Button(label=yes)
        button.get_style_context().add_class("answer")
        button.get_style_context().add_class("yes")
        button.connect("clicked", lambda *_args: self.close_card() or on_yes())
        buttons.pack_start(no, False, False, 0)
        buttons.pack_start(button, False, False, 0)
        self.card.pack_start(buttons, False, False, 0)
        self.no = no

    def open_card(self):
        super().open_card()
        self.no.grab_focus()


class Running(Gtk.Button):
    """A running app on the shelf; the one in front shows its name too."""

    def __init__(self, shelf, window):
        super().__init__()
        self.shelf = shelf
        self.window = window
        self.get_style_context().add_class("running")
        self.box = Gtk.Box(spacing=8)
        self.image = None
        self.name = label("", "running-name", ellipsize=Pango.EllipsizeMode.END)
        self.name.set_max_width_chars(16)
        self.name.set_no_show_all(True)
        self.box.pack_end(self.name, False, False, 0)
        self.add(self.box)
        self._identify()
        # LibreOffice changes its class once it knows which app it is.
        window.connect("class-changed", lambda *_args: self._identify())
        window.connect("icon-changed", lambda *_args: self._identify())
        self.set_tooltip_text(window.get_name())
        window.connect("name-changed", lambda w: self.set_tooltip_text(w.get_name()))
        self.connect("clicked", lambda *_args: window.activate(now(shelf)))

    def _identify(self):
        info = self.shelf.app_for(self.window)
        if info is not None:
            image = icon(info, ICON)
            name = info.get_name()
        else:
            image = Gtk.Image()
            pixbuf = self.window.get_icon()
            if pixbuf is not None:
                image.set_from_pixbuf(pixbuf.scale_simple(ICON, ICON, GdkPixbuf.InterpType.BILINEAR))
            name = self.window.get_class_group_name() or self.window.get_name()
        if self.image is not None:
            self.image.destroy()
        self.image = image
        self.box.pack_start(image, False, False, 0)
        image.show()
        self.name.set_label(name)

    def front(self, active):
        style = self.get_style_context()
        if active:
            style.add_class("front")
        else:
            style.remove_class("front")
        self.name.set_visible(active)


class Shelf(Gtk.Window):
    def __init__(self, config, kid):
        super().__init__(title="Zoomies shelf")
        self.set_name("shelf")
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.stick()
        self.kid = kid
        self.x = xdisplay.Display()

        for path in apps.icon_dirs(config.get("olderApps", []) + kid["games"]):
            Gtk.IconTheme.get_default().append_search_path(path)
        entries = apps.entries(config.get("olderApps", []), set(config.get("olderHiddenApps", [])))
        games = apps.entries(kid["games"])
        self.known = {}
        for info in [*Gio.AppInfo.get_all(), *entries, *games]:
            if not isinstance(info, Gio.DesktopAppInfo):
                continue
            desktop_id = (info.get_id() or os.path.basename(info.get_filename() or "")).lower()
            keys = [desktop_id.removesuffix(".desktop"), desktop_id.removesuffix(".desktop").split(".")[-1]]
            if info.get_startup_wm_class():
                keys.insert(0, info.get_startup_wm_class().lower())
            for key in keys:
                self.known.setdefault(key, info)

        bar = Gtk.Box(spacing=12)
        bar.get_style_context().add_class("bar")
        self.add(bar)

        self.apps_button = Gtk.Button()
        self.apps_button.get_style_context().add_class("apps")
        inside = Gtk.Box(spacing=6)
        zip_art = os.path.join(config.get("assets", ""), "zip.svg")
        if os.path.exists(zip_art):
            loader = GdkPixbuf.PixbufLoader()
            loader.set_size(int(ICON * 1.15), int(ICON * 1.15))
            loader.write(art.svg_frames(zip_art)[0])
            loader.close()
            inside.pack_start(Gtk.Image.new_from_pixbuf(loader.get_pixbuf()), False, False, 0)
        inside.pack_start(label(_("Apps"), "apps-label"), False, False, 0)
        self.apps_button.add(inside)
        self.apps_button.connect("clicked", self._toggle_apps)
        bar.pack_start(self.apps_button, False, False, 0)
        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        self.running = Gtk.Box(spacing=10)
        bar.pack_start(self.running, True, True, 0)
        self.hint = label(_("Press Apps to start something!"), "hint", xalign=0)
        self.running.pack_start(self.hint, False, False, 0)

        self.time_left = label("", "time-pill", valign=Gtk.Align.CENTER)
        self.time_left.set_no_show_all(True)
        bar.pack_start(self.time_left, False, False, 0)
        self.clock = label("", "clock")
        bar.pack_start(self.clock, False, False, 0)
        switch = Gtk.Button(label="👋", tooltip_text=_("Switch player"))
        power = Gtk.Button(label="⏻", tooltip_text=_("Turn off"))
        for button in (switch, power):
            button.get_style_context().add_class("round")
            bar.pack_start(button, False, False, 0)
        self.switch = Ask(self, _("Stop and switch player?"), _("Switch"), lambda: self._session("--logout"))
        self.power = Ask(self, _("Turn the computer off?"), _("Turn off"), lambda: self._session("--halt"))
        switch.connect("clicked", lambda *_args: self._ask(self.switch))
        power.connect("clicked", lambda *_args: self._ask(self.power))

        self.panel = AppsPanel(self, entries, games)

        self.connect("realize", lambda *_args: self.place())
        Gdk.Screen.get_default().connect("monitors-changed", lambda *_args: self.place())
        Gdk.Screen.get_default().connect("size-changed", lambda *_args: self.place())

        self.buttons = {}
        self.front = None
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        self.screen = Wnck.Screen.get_default()
        self.screen.connect("window-opened", lambda _s, w: self._opened(w))
        self.screen.connect("window-closed", lambda _s, w: self._closed(w))
        self.screen.connect("active-window-changed", lambda *_args: self._front())
        self.screen.force_update()
        for window in self.screen.get_windows():
            self._opened(window)

        self.tick()
        GLib.timeout_add_seconds(5, self.tick)

    def place(self):
        """Along the bottom of the main monitor, with the space kept free of
        maximized apps."""
        geometry = monitor().get_geometry()
        self.set_size_request(geometry.width, HEIGHT)
        self.resize(geometry.width, HEIGHT)
        self.move(geometry.x, geometry.y + geometry.height - HEIGHT)
        if not self.get_realized():
            return
        scale = monitor().get_scale_factor()
        screen = self.get_screen()
        root_height = screen.get_root_window().get_height() * scale
        bottom = root_height - (geometry.y + geometry.height) * scale + HEIGHT * scale
        left, right = geometry.x * scale, (geometry.x + geometry.width) * scale - 1
        strut = [0, 0, 0, bottom, 0, 0, 0, 0, 0, 0, left, right]
        window = self.x.create_resource_object("window", self.get_window().get_xid())
        window.change_property(self.x.intern_atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL, 32, strut)
        window.change_property(self.x.intern_atom("_NET_WM_STRUT"), Xatom.CARDINAL, 32, strut[:4])
        self.x.flush()

    def app_for(self, window):
        for name in (window.get_class_group_name(), window.get_class_instance_name()):
            if name and name.lower() in self.known:
                return self.known[name.lower()]
        return None

    @staticmethod
    def _ours(window):
        return (
            window.get_window_type() == Wnck.WindowType.NORMAL
            and not window.is_skip_tasklist()
            and window.get_transient() is None
        )

    def _opened(self, window):
        if not self._ours(window) or window in self.buttons:
            return
        window.connect("state-changed", lambda w, *_args: self._fit(w))
        self._fit(window)
        button = Running(self, window)
        self.buttons[window] = button
        self.running.pack_start(button, False, False, 0)
        button.show_all()
        self.hint.hide()
        self._front()

    def _closed(self, window):
        button = self.buttons.pop(window, None)
        if button is not None:
            button.destroy()
        if not self.buttons:
            self.hint.show()

    def _fit(self, window):
        """Full screen above the shelf, never minimized: an app that is
        shrunk or minimized is put back."""
        if window.is_minimized():
            window.unminimize(now(self))
        if window.is_fullscreen():
            return
        if window.get_actions() & Wnck.WindowActions.MAXIMIZE and not window.is_maximized():
            window.maximize()

    def _front(self):
        active = self.screen.get_active_window()
        # A dialog stands for the app it belongs to.
        while active is not None and active.get_transient() is not None:
            active = active.get_transient()
        # With the Apps card or a question open, the app stays in front.
        if active not in self.buttons and self.front in self.buttons:
            active = self.front
        self.front = active
        for window, button in self.buttons.items():
            button.front(window == active)

    def _toggle_apps(self, *_args):
        if self.panel.get_visible() or self.panel.just_closed():
            self.panel.close_card()
        else:
            self.panel.open_card()

    def _ask(self, popup):
        if not popup.just_closed():
            popup.open_card()

    @staticmethod
    def _session(action):
        # Through the session, so apps get to ask about unsaved work.
        subprocess.Popen(["xfce4-session-logout", action])

    def tick(self):
        self.clock.set_label(GLib.DateTime.new_now_local().format("%H:%M"))
        status = state.read_status().get(self.kid["user"])
        remaining = status and status.get("remaining")
        if remaining is None:
            self.time_left.hide()
        else:
            self.time_left.set_label(f"⏳ {state.format_duration(remaining)}")
            style = self.time_left.get_style_context()
            if remaining <= 300:
                style.add_class("low")
            else:
                style.remove_class("low")
            self.time_left.show()
        return GLib.SOURCE_CONTINUE


def main():
    config = state.load_config()
    kid = state.current_kid(config)
    css()
    shelf = Shelf(config, kid)
    shelf.show_all()
    Gtk.main()
