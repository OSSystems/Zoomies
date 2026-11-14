"""Widgets and input handling shared by the greeter, launcher and parent app."""

import datetime
import os
import subprocess
import xml.etree.ElementTree as ET

import gi

from . import state

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


def when_ready(window, name, *conditions):
    """Leave a mark once the window has focus and every condition holds.

    Keys pressed before that are lost, so tests (and anything else
    scripting the kiosk) wait for the mark instead of guessing with sleeps.
    The mark holds the pid, so a mark left by a previous run never counts.
    """
    pending = set(conditions) | {"focus"}

    def done(condition):
        pending.discard(condition)
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if pending or not runtime:
            return
        path = os.path.join(runtime, f"{name}-ready")
        with open(path + ".tmp", "w") as f:
            f.write(str(os.getpid()))
        os.replace(path + ".tmp", path)

    def active(*_):
        if window.is_active():
            done("focus")

    window.connect("notify::is-active", active)
    return done


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


SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# Zip's poses: lift-off for resting screens, flying for when something starts.
POSES = {"rest": "zip.svg", "fly": "zip-flying.svg"}


def mascot_frames(path, height):
    """Textures for every frame of the SVG's <animate> loops.

    librsvg draws only the first frame of an SVG animation, so the frames
    are rendered one by one and shown in turn.
    """
    tree = ET.parse(path)
    animated = []
    for element in tree.iter():
        for animation in element.findall(f"{{{SVG}}}animate"):
            if animation.get("attributeName") == "d":
                values = animation.get("values").split(";")
                # A loop repeats its first frame at the end.
                if len(values) > 1 and values[-1] == values[0]:
                    values.pop()
                animated.append((element, values))
            element.remove(animation)
    count = min((len(values) for _, values in animated), default=1)
    textures = []
    for frame in range(count):
        for element, values in animated:
            element.set("d", values[frame])
        stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(ET.tostring(tree.getroot())))
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, -1, height, True, None)
        textures.append(Gdk.Texture.new_for_pixbuf(pixbuf))
    return textures


class Mascot(Gtk.Picture):
    FRAME_MS = 100

    def __init__(self, config, size, pose="rest"):
        super().__init__(can_shrink=False, valign=Gtk.Align.CENTER)
        self.add_css_class("mascot")
        self.assets = config.get("assets", "")
        self.size = size
        self.poses = {}
        self.frames = []
        self.frame = 0
        self.timer = None
        self.connect("unrealize", lambda *_: self._stop())
        self.set_pose(pose)

    def _load(self, pose):
        if pose not in self.poses:
            try:
                self.poses[pose] = mascot_frames(
                    os.path.join(self.assets, POSES[pose]), self.size
                )
            except (GLib.Error, OSError, ET.ParseError):
                self.poses[pose] = []
        return self.poses[pose]

    def set_pose(self, pose):
        self._stop()
        self.frames = self._load(pose)
        self.frame = 0
        self.set_paintable(self.frames[0] if self.frames else None)
        if len(self.frames) > 1:
            self.timer = GLib.timeout_add(self.FRAME_MS, self._next)

    def _next(self):
        self.frame = (self.frame + 1) % len(self.frames)
        self.set_paintable(self.frames[self.frame])
        return GLib.SOURCE_CONTINUE

    def _stop(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None


def mascot(config, size, pose="rest"):
    # Rendered at the wanted height: a Picture of the SVG itself would ask
    # for the SVG's large natural size and squeeze everything around it.
    return Mascot(config, size, pose)


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


class KidForm(Gtk.Box):
    """Name, avatar, colour and kind of a kid, for adding or editing."""

    KIND_LABELS = {
        "little": ("🧸", "Little kid", "Just the games"),
        "older": ("🎒", "Older kid", "A desktop for study and play"),
    }

    def __init__(self, kid=None, older=True, used_avatars=()):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        kid = kid or {}
        free = [a for a in state.AVATARS if a not in used_avatars] or state.AVATARS
        self.avatar = kid.get("avatar") or free[0]
        self.color = kid.get("color") or state.COLORS[len(used_avatars) % len(state.COLORS)]
        self.kind = kid.get("kind") or "little"

        self.name = Gtk.Entry(text=kid.get("name", ""), placeholder_text="Name")
        self.name.add_css_class("name-entry")
        self.append(self.name)

        avatars = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=8,
            min_children_per_line=8,
            homogeneous=True,
        )
        self.avatar_buttons = {}
        for emoji in state.AVATARS:
            button = Gtk.ToggleButton(label=emoji, active=emoji == self.avatar)
            button.add_css_class("avatar-choice")
            button.connect("toggled", self._pick_avatar, emoji)
            self.avatar_buttons[emoji] = button
            avatars.append(button)
        self.append(avatars)

        colors = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        self.color_buttons = {}
        for color in state.COLORS:
            button = Gtk.ToggleButton(active=color == self.color)
            button.add_css_class("color-choice")
            button.add_css_class(f"color-{color}")
            button.set_tooltip_text(color)
            button.connect("toggled", self._pick_color, color)
            self.color_buttons[color] = button
            colors.append(button)
        self.append(colors)

        kinds = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER, homogeneous=True)
        self.kind_buttons = {}
        for kind, (emoji, title, hint) in self.KIND_LABELS.items():
            if kind == "older" and not older:
                continue
            button = Gtk.ToggleButton(active=kind == self.kind)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            label = Gtk.Label(label=f"{emoji} {title}")
            label.add_css_class("kind-title")
            box.append(label)
            box.append(Gtk.Label(label=hint))
            button.set_child(box)
            button.add_css_class("kind-choice")
            button.connect("toggled", self._pick_kind, kind)
            self.kind_buttons[kind] = button
            kinds.append(button)
        self.append(kinds)

    def _pick(self, buttons, value, attribute):
        if not buttons[value].get_active():
            # Keep one choice selected: clicking the active one again
            # should not leave nothing chosen.
            if getattr(self, attribute) == value:
                buttons[value].set_active(True)
            return
        setattr(self, attribute, value)
        for other, button in buttons.items():
            if other != value and button.get_active():
                button.set_active(False)

    def _pick_avatar(self, _button, emoji):
        self._pick(self.avatar_buttons, emoji, "avatar")

    def _pick_color(self, _button, color):
        self._pick(self.color_buttons, color, "color")

    def _pick_kind(self, _button, kind):
        self._pick(self.kind_buttons, kind, "kind")

    def values(self):
        return {
            "avatar": self.avatar,
            "color": self.color,
            "kind": self.kind,
            "name": self.name.get_text().strip(),
        }


def pin_entry(placeholder):
    entry = Gtk.PasswordEntry(placeholder_text=placeholder, show_peek_icon=False)
    entry.set_size_request(340, -1)
    entry.add_css_class("pin")
    entry.set_halign(Gtk.Align.CENTER)
    return entry


def message_label():
    label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
    label.add_css_class("pin-message")
    return label
