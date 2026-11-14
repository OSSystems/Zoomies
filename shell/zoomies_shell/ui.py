"""Widgets and input handling shared by the greeter, launcher and parent app."""

import datetime
import os
import subprocess

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Manette", "0.2")
    from gi.repository import Manette  # noqa: E402
except (ValueError, ImportError):
    Manette = None

# Linux input event codes, which libmanette reports after applying its
# controller mappings, so every gamepad uses the same numbers.
BTN_SOUTH, BTN_EAST, BTN_START, BTN_MODE = 304, 305, 315, 316
BTN_DPAD = {
    544: Gtk.DirectionType.UP,
    545: Gtk.DirectionType.DOWN,
    546: Gtk.DirectionType.LEFT,
    547: Gtk.DirectionType.RIGHT,
}
ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y = 0, 1, 16, 17

SOUNDS = "/run/current-system/sw/share/sounds/freedesktop/stereo"


def load_css():
    provider = Gtk.CssProvider()
    provider.load_from_path(os.path.join(os.path.dirname(__file__), "style.css"))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def play(name):
    path = os.path.join(SOUNDS, f"{name}.oga")
    if os.path.exists(path):
        subprocess.Popen(
            ["pw-play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )


def avatar(kid, size="big"):
    label = Gtk.Label(label=kid.get("avatar", "🙂"))
    label.add_css_class("avatar")
    label.add_css_class(f"avatar-{size}")
    label.add_css_class(f"color-{kid.get('color', 'sky')}")
    label.set_halign(Gtk.Align.CENTER)
    label.set_valign(Gtk.Align.CENTER)
    return label


def mascot(config, size):
    # Rendered at the wanted size: a Picture of the SVG itself would ask for
    # the SVG's large natural size and squeeze everything around it.
    path = os.path.join(config.get("assets", ""), "zip.svg")
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
        picture = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
    except GLib.Error:
        picture = Gtk.Picture()
    picture.set_can_shrink(False)
    picture.set_valign(Gtk.Align.CENTER)
    picture.add_css_class("mascot")
    return picture


def clock():
    label = Gtk.Label(valign=Gtk.Align.CENTER)
    label.add_css_class("clock")

    def tick():
        label.set_label(datetime.datetime.now().strftime("%H:%M"))
        return GLib.SOURCE_CONTINUE

    tick()
    GLib.timeout_add_seconds(5, tick)
    return label


def big_button(text, css=None, emoji=None):
    button = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    if emoji:
        icon = Gtk.Label(label=emoji)
        icon.add_css_class("button-emoji")
        box.append(icon)
    if text:
        box.append(Gtk.Label(label=text))
    button.set_child(box)
    button.add_css_class("big-button")
    button.set_valign(Gtk.Align.CENTER)
    if css:
        button.add_css_class(css)
    return button


class Overlay(Gtk.Overlay):
    """A full-window layer for dialogs; cage shows one window, so popups
    would otherwise take over the whole screen."""

    def __init__(self, content):
        super().__init__()
        self.set_child(content)
        self._layer = None
        self._previous_focus = None
        self.modal = False

    def show(self, child, modal=False):
        if self._layer is None:
            self._previous_focus = self.get_root().get_focus()
        else:
            self.remove_overlay(self._layer)
        layer = Gtk.Box(halign=Gtk.Align.FILL, valign=Gtk.Align.FILL)
        layer.add_css_class("scrim")
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.CENTER)
        child.set_hexpand(True)
        child.add_css_class("dialog")
        layer.append(child)
        # The scrim only stops the pointer; without this, the keyboard and
        # the gamepad could still move focus to buttons behind the dialog.
        self.get_child().set_sensitive(False)
        self.add_overlay(layer)
        self._layer = layer
        self.modal = modal
        layer.child_focus(Gtk.DirectionType.TAB_FORWARD)

    def close(self, force=False):
        """Close the dialog; a modal one only goes away when forced."""
        if self._layer is None or (self.modal and not force):
            return
        self.remove_overlay(self._layer)
        self._layer = None
        self.modal = False
        self.get_child().set_sensitive(True)
        if self._previous_focus is not None:
            self._previous_focus.grab_focus()

    @property
    def open(self):
        return self._layer is not None

    def confirm(self, question, emoji, on_yes):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        title = Gtk.Label(label=f"{emoji}\n{question}", justify=Gtk.Justification.CENTER)
        title.add_css_class("dialog-title")
        box.append(title)
        row = Gtk.Box(spacing=24, halign=Gtk.Align.CENTER, homogeneous=True)
        no = big_button("No", "no", "✖")
        yes = big_button("Yes", "yes", "✔")
        no.connect("clicked", lambda *_: self.close())

        def accept(*_):
            self.close()
            on_yes()

        yes.connect("clicked", accept)
        row.append(no)
        row.append(yes)
        box.append(row)
        self.show(box)
        no.grab_focus()


class Gamepad:
    """Turns gamepad input into focus moves and clicks.

    The stick needs to return to centre before it moves focus again, so a
    held stick does not race across the grid.
    """

    DEADZONE = 0.6

    def __init__(self, window, on_back=None, on_home=None, enabled=lambda: True):
        self.window = window
        self.on_back = on_back
        self.on_home = on_home
        self.enabled = enabled
        self._centred = {ABS_X: True, ABS_Y: True}
        if Manette is None:
            return
        self.monitor = Manette.Monitor.new()
        self.monitor.connect("device-connected", lambda _m, d: self._attach(d))
        iterator = self.monitor.iterate()
        while True:
            ok, device = iterator.next()
            if not ok:
                break
            self._attach(device)

    def _attach(self, device):
        device.connect("button-press-event", self._button)
        device.connect("absolute-axis-event", self._axis)
        device.connect("hat-axis-event", self._hat)

    def _move(self, direction):
        if self.enabled():
            self.window.child_focus(direction)

    def _button(self, _device, event):
        ok, button = event.get_button()
        if not ok:
            return
        if button == BTN_MODE and self.on_home:
            self.on_home()
        if not self.enabled():
            return
        if button in BTN_DPAD:
            self._move(BTN_DPAD[button])
        elif button in (BTN_SOUTH, BTN_START):
            focus = self.window.get_focus()
            if focus is not None:
                focus.activate()
        elif button == BTN_EAST and self.on_back:
            self.on_back()

    def _axis(self, _device, event):
        ok, axis, value = event.get_absolute()
        if not ok or axis not in self._centred:
            return
        if abs(value) < self.DEADZONE / 2:
            self._centred[axis] = True
            return
        if abs(value) < self.DEADZONE or not self._centred[axis]:
            return
        self._centred[axis] = False
        if axis == ABS_X:
            self._move(Gtk.DirectionType.RIGHT if value > 0 else Gtk.DirectionType.LEFT)
        else:
            self._move(Gtk.DirectionType.DOWN if value > 0 else Gtk.DirectionType.UP)

    def _hat(self, _device, event):
        ok, axis, value = event.get_hat()
        if not ok or value == 0:
            return
        if axis == ABS_HAT0X:
            self._move(Gtk.DirectionType.RIGHT if value > 0 else Gtk.DirectionType.LEFT)
        elif axis == ABS_HAT0Y:
            self._move(Gtk.DirectionType.DOWN if value > 0 else Gtk.DirectionType.UP)
