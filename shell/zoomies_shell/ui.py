"""Widgets and input handling shared by the greeter, launcher and parent app."""

import datetime
import os
import subprocess
import sys

import gi

from . import art, state
from .i18n import N_, _

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Graphene, Gtk  # noqa: E402

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
        # The session before keeps its last frame up until then.
        if os.path.isdir(SPLASH_HANDOVER):
            try:
                os.utime(touch(os.path.join(SPLASH_HANDOVER, f"drawn-{os.getuid()}")))
            except OSError:
                pass

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


def run(app_id, make_window):
    """Run a fullscreen app whose one window make_window(app) builds."""
    app = Gtk.Application(application_id=app_id)

    def activate(app):
        load_css()
        window = make_window(app)
        window.fullscreen()
        window.present()

    app.connect("activate", activate)
    sys.exit(app.run(None))


def reason(error):
    """The admin service's refusal as a sentence for the screen."""
    return _(str(error)).capitalize() + "."


def play(name):
    path = os.path.join(SOUNDS, f"{name}.oga")
    if os.path.exists(path):
        subprocess.Popen(
            ["pw-play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )


def when_back(status):
    days, time = status.get("opensIn"), status.get("opensAt")
    if status["reason"] == "hours" and days == 0:
        return _("Back at {time}").format(time=time)
    if days == 1:
        return _("Back tomorrow at {time}").format(time=time)
    if days is not None and days < 7:
        weekday = (datetime.date.today() + datetime.timedelta(days=days)).weekday()
        return _("Back on {day}").format(day=_(state.WEEKDAY_NAMES[weekday]))
    return _("All done for today")


def avatar(kid, size="big"):
    return Gtk.Label(
        label=kid.get("avatar", "🙂"),
        css_classes=["avatar", f"avatar-{size}", f"color-{kid.get('color', 'sky')}"],
        halign=Gtk.Align.CENTER,
        valign=Gtk.Align.CENTER,
    )


# Zip's poses: waving hello on resting screens, flying for when something starts.
POSES = {"rest": "zip.svg", "fly": "zip-flying.svg"}


def mascot_frames(path, height):
    # Rendered at the wanted height: a Picture of the SVG itself would ask
    # for the SVG's large natural size and squeeze everything around it.
    return [
        Gdk.Texture.new_for_pixbuf(art.pixbuf(data, height=height))
        for data in art.svg_frames(path)
    ]


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
        self.connect("unrealize", lambda *_args: self._stop())
        self.set_pose(pose)

    def _load(self, pose):
        if pose not in self.poses:
            try:
                self.poses[pose] = mascot_frames(
                    os.path.join(self.assets, POSES[pose]), self.size
                )
            except (GLib.Error, OSError, art.ET.ParseError):
                self.poses[pose] = []
        return self.poses[pose]

    def set_pose(self, pose):
        self._stop()
        self.frames = self._load(pose)
        self.frame = 0
        self.set_paintable(self.frames[0] if self.frames else None)
        if len(self.frames) > 1 and not state.calm_screen():
            self.timer = GLib.timeout_add(self.FRAME_MS, self._next)

    def _next(self):
        self.frame = (self.frame + 1) % len(self.frames)
        self.set_paintable(self.frames[self.frame])
        return GLib.SOURCE_CONTINUE

    def _stop(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None


def clock():
    label = Gtk.Label(valign=Gtk.Align.CENTER, css_classes=["clock"])

    def tick():
        label.set_label(datetime.datetime.now().strftime("%H:%M"))
        return GLib.SOURCE_CONTINUE

    tick()
    GLib.timeout_add_seconds(5, tick)
    return label


def scroller(child, **properties):
    """A scrolled area whose scrollbar never hides, wide enough to grab: a
    bar that only shows while scrolling leaves no hint of more below."""
    window = Gtk.ScrolledWindow(
        child=child,
        hscrollbar_policy=Gtk.PolicyType.NEVER,
        overlay_scrolling=False,
        **properties,
    )
    window.add_css_class("scroller")
    return window


def big_button(text, css=None, emoji=None):
    button = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    if emoji:
        box.append(Gtk.Label(label=emoji, css_classes=["button-emoji"]))
    if text:
        box.append(Gtk.Label(label=text))
    button.set_child(box)
    button.add_css_class("big-button")
    button.set_valign(Gtk.Align.CENTER)
    if css:
        button.add_css_class(css)
    return button


SYSTEM_ACTIONS = {
    "poweroff": ("⏻", "🌙", N_("Turn the computer off?")),
    "reboot": ("🔄", "🔄", N_("Restart the computer?")),
}


# Where the platform's splash and cage meet to hand the screen over at power
# off and restart; it only exists when that splash is installed.
SPLASH_HANDOVER = "/run/zoomies-splash"


def touch(path):
    open(path, "a").close()
    return path


def power(action):
    """Runs systemctl's action, asking cage to hand the screen to the splash."""
    if os.path.isdir(SPLASH_HANDOVER):
        try:
            touch(os.path.join(SPLASH_HANDOVER, "requested"))
        except OSError:
            pass
    subprocess.Popen(["systemctl", action])


def system_button(overlay, action, text=None):
    """A button that asks first, then fades to the sky and runs systemctl's action."""
    emoji, question_emoji, question = SYSTEM_ACTIONS[action]
    button = big_button(text, "subtle", emoji)
    button.connect(
        "clicked",
        lambda *_args: overlay.confirm(
            _(question), question_emoji, lambda: overlay.fade_to_sky(lambda: power(action))
        ),
    )
    return button


# The boot splash's cloud, so the sky carries on from it unchanged.
CLOUD = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-62 -32 130 50">'
    '<g fill="#fff" opacity=".9"><ellipse rx="40" ry="16"/>'
    '<ellipse cx="-16" cy="-10" rx="20" ry="16"/><ellipse cx="14" cy="-12" rx="24" ry="18"/>'
    "</g></svg>"
)


class Sky(Gtk.Widget):
    """Clouds drifting left across the window's sky, behind everything.

    The boot splash's clouds, ``slowness`` times slower. Positions and sizes
    are in pixels of a 1080-line screen and scale with the window. They
    follow the frame clock, so the compositor stops them while a game covers
    the window, and they fade in as the window opens: the boot splash ends
    on a bare sky.

    Old PCs draw without a GPU, where every redraw is expensive, so all the
    clouds step together 20 times a second, slow enough that each step is
    about a pixel, instead of on every frame.
    """

    # (x, y, size, speed): the splash's layout.
    CLOUDS = [(i * 345, 108 + (i * 291) % 810, i % 3, 330 + (i % 3) * 270) for i in range(7)]
    SIZES = (0.55, 0.9, 1.25)
    FADE_IN = 1.5
    STEPS_PER_SECOND = 20

    def __init__(self, slowness, strength=1.0):
        super().__init__(can_target=False, hexpand=True, vexpand=True)
        self.slowness = slowness
        self.strength = strength
        self.textures = {}
        self.scale = None
        self.start = None
        self.now = 0.0
        self.drawn = None
        self.timer = None
        self.connect("map", self._start)
        self.connect("unmap", self._stop)

    def _textures(self, scale):
        if scale != self.scale:
            self.scale = scale
            self.textures = {}
            for size, factor in enumerate(self.SIZES):
                width = max(1, round(390 * factor * scale))
                self.textures[size] = Gdk.Texture.new_for_pixbuf(art.pixbuf(CLOUD.encode(), width))
        return self.textures

    def _layout(self):
        """Where each cloud is now, in whole pixels, and how faded in."""
        width, height = self.get_width(), self.get_height()
        if not width or not height:
            return None
        scale = height / 1080
        textures = self._textures(scale)
        clouds = []
        for x, y, size, speed in self.CLOUDS:
            w = textures[size].get_width()
            left = (x * scale - self.now * speed * scale / self.slowness) % (width + w) - w
            clouds.append((round(left), round(y * scale), size))
        fade = round(min(1.0, self.now / self.FADE_IN), 2)
        return fade, tuple(clouds)

    def _start(self, *_):
        if self.timer is None:
            self.timer = GLib.timeout_add(1000 // self.STEPS_PER_SECOND, self._step)

    def _stop(self, *_):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def _step(self):
        now = GLib.get_monotonic_time() / 1e6
        if self.start is None:
            self.start = now
        self.now = now - self.start
        if self._layout() != self.drawn:
            self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def do_snapshot(self, snapshot):
        self.drawn = self._layout()
        if self.drawn is None:
            return
        fade, clouds = self.drawn
        snapshot.push_opacity(self.strength * fade)
        for left, top, size in clouds:
            texture = self.textures[size]
            bounds = Graphene.Rect().init(left, top, texture.get_width(), texture.get_height())
            snapshot.append_texture(texture, bounds)
        snapshot.pop()


def sky(slowness, strength=1.0):
    """A Sky, unless the grown-ups asked for a calm screen."""
    return None if state.calm_screen() else Sky(slowness, strength)


# When each step of a screen's arrival starts, and how far apart the
# widgets of one step start; the sky shows bare for a moment first.
ARRIVALS = {"drop": 0.15, "pop": 0.35, "rise": 0.8}
STAGGER = 0.06
_delays = None
_delay_classes = set()


def children(widget):
    found = []
    child = widget.get_first_child()
    while child is not None:
        found.append(child)
        child = child.get_next_sibling()
    return found


def arrive(window, *steps):
    """Brings a screen in on the bare sky the screen before left.

    Each step is a kind of entrance, one of ARRIVALS, and its widgets, which
    start one after another: the title drops, the tiles pop, the buttons
    rise. Keys work at once. A calm screen only fades in.

    The first frame takes long to draw, without a GPU up to half a second,
    and an animation started with it would be mostly over by the time it
    shows. That frame shows the bare sky; the steps start once it is out.
    """
    calm = state.calm_screen()
    timeline = []
    for kind, widgets in steps:
        for index, widget in enumerate(widgets):
            if calm:
                timeline.append((widget, "appear", 0))
            else:
                timeline.append((widget, kind, round(1000 * (ARRIVALS[kind] + STAGGER * min(index, 6)))))
            widget.add_css_class("waiting")
    global _delays
    needed = {delay for _widget, _kind, delay in timeline} - _delay_classes
    if needed:
        if _delays is None:
            _delays = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), _delays, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        _delay_classes.update(needed)
        _delays.load_from_string(
            "".join(f".delay-{ms} {{ animation-delay: {ms}ms; }}\n" for ms in sorted(_delay_classes))
        )

    def start(clock):
        clock.disconnect(painted)
        for widget, kind, delay in timeline:
            widget.add_css_class(f"arrive-{kind}")
            widget.add_css_class(f"delay-{delay}")
            widget.remove_css_class("waiting")

    def realized(*_args):
        nonlocal painted
        painted = window.get_frame_clock().connect("after-paint", start)

    painted = None
    window.connect("realize", realized)


class Overlay(Gtk.Overlay):
    """A full-window layer for dialogs; cage shows one window, so popups
    would otherwise take over the whole screen."""

    def __init__(self, content, sky=None):
        super().__init__()
        if sky is not None:
            # The sky sits under the page; the page decides the size.
            layers = Gtk.Overlay(child=sky)
            layers.add_overlay(content)
            layers.set_measure_overlay(content, True)
            content = layers
        self.set_child(content)
        self._layer = None
        self._previous_focus = None
        self.modal = False
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)

    def _key(self, _controller, keyval, _code, _modifiers):
        if keyval == Gdk.KEY_Escape and self.open:
            self.close()
            return True
        return False

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

    FADE_SECONDS = 0.3

    def fade_to_sky(self, then):
        """Fades to the bare sky, then calls then.

        The power off splash opens on that sky, so the screen never changes
        all at once. The fade follows the clock, not the frames, so a slow
        machine only shows fewer steps of it.
        """
        cover = Gtk.Box(hexpand=True, vexpand=True, can_target=False, css_classes=["sky-cover"])
        cover.set_opacity(0)
        self.add_overlay(cover)
        self.get_child().set_sensitive(False)
        start = GLib.get_monotonic_time()

        def step(*_args):
            done = (GLib.get_monotonic_time() - start) / 1e6 / self.FADE_SECONDS
            cover.set_opacity(min(1.0, done))
            if done < 1:
                return GLib.SOURCE_CONTINUE
            then()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(16, step)

    def confirm(self, question, emoji, on_yes):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.append(
            Gtk.Label(
                label=f"{emoji}\n{question}",
                justify=Gtk.Justification.CENTER,
                css_classes=["dialog-title"],
            )
        )
        row = Gtk.Box(spacing=24, halign=Gtk.Align.CENTER, homogeneous=True)
        no = big_button(_("No"), "no", "✖")
        yes = big_button(_("Yes"), "yes", "✔")
        no.connect("clicked", lambda *_args: self.close())

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
        "little": ("🧸", _("Little kid"), _("Just the games")),
        "older": ("🎒", _("Older kid"), _("A desktop for study and play")),
    }

    def __init__(self, kid=None, older=True, used_avatars=()):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        kid = kid or {}
        free = [a for a in state.AVATARS if a not in used_avatars] or state.AVATARS
        self.avatar = kid.get("avatar") or free[0]
        self.color = kid.get("color") or state.COLORS[len(used_avatars) % len(state.COLORS)]
        self.kind = kid.get("kind") or "little"

        self.name = Gtk.Entry(text=kid.get("name", ""), placeholder_text=_("Name"))
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
            box.append(Gtk.Label(label=f"{emoji} {title}", css_classes=["kind-title"]))
            box.append(Gtk.Label(label=hint))
            button.set_child(box)
            button.add_css_class("kind-choice")
            self.kind_buttons[kind] = button
            kinds.append(button)
        self.append(kinds)

        self._choices("avatar", self.avatar_buttons)
        self._choices("color", self.color_buttons)
        self._choices("kind", self.kind_buttons)

    def _choices(self, attribute, buttons):
        first, *rest = buttons.values()
        for button in rest:
            button.set_group(first)
        for value, button in buttons.items():
            button.connect("toggled", self._chosen, attribute, value, not rest)

    def _chosen(self, button, attribute, value, lone):
        if button.get_active():
            setattr(self, attribute, value)
        elif lone:
            # A group keeps one of its buttons chosen, but GTK cannot group
            # a lone button, as when only one kind of kid is allowed.
            button.set_active(True)

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
    return Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, css_classes=["pin-message"])
