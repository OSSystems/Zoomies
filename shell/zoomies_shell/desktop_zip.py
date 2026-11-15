"""Flaps Zip's cape on the older kids' wallpaper.

xfdesktop shows a still image, so a small window sits on the desktop over
the part of the wallpaper that moves and plays the wallpaper's own frames
there. They are scaled and cropped the way xfdesktop zooms the image, so
the window lines up with the wallpaper pixel for pixel. Clicks go through
to the desktop, and the window steps aside when the kid picks another
wallpaper.
"""

import sys

import cairo
import gi

from . import art, state

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Xfconf", "0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Xfconf  # noqa: E402

FRAME_MS = 100
# Room for xfdesktop's smoothing, which reaches a pixel past a shape.
MARGIN = 2


def zoomed(data, width, height):
    """The wallpaper as xfdesktop's "zoomed" style draws it on a monitor:
    the image covers the monitor, centred, with the same rounding."""
    loader = GdkPixbuf.PixbufLoader()

    def prepared(loader, image_width, image_height):
        scale = max(width / image_width, height / image_height)
        loader.set_size(int(image_width * scale), int(image_height * scale))

    loader.connect("size-prepared", prepared)
    loader.write(data)
    loader.close()
    image = loader.get_pixbuf()
    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height)
    canvas.fill(0)
    x = int((width - image.get_width()) * 0.5)
    y = int((height - image.get_height()) * 0.5)
    image.composite(
        canvas, 0, 0, width, height, x, y, 1, 1, GdkPixbuf.InterpType.BILINEAR, 255
    )
    return canvas


def first_difference(a, b):
    low, high = 0, len(a)
    while low < high:
        middle = (low + high) // 2
        if a[: middle + 1] == b[: middle + 1]:
            low = middle + 1
        else:
            high = middle
    return low


def moving_area(frames):
    """The rectangle where any frame differs from the first."""
    width, height = frames[0].get_width(), frames[0].get_height()
    stride, channels = frames[0].get_rowstride(), frames[0].get_n_channels()
    pixels = [frame.get_pixels() for frame in frames]
    top = bottom = None
    left, right = width, 0
    for y in range(height):
        start = y * stride
        row = pixels[0][start : start + width * channels]
        for other in pixels[1:]:
            changed = other[start : start + width * channels]
            if changed == row:
                continue
            top = y if top is None else top
            bottom = y
            left = min(left, first_difference(row, changed) // channels)
            right = max(right, width - first_difference(row[::-1], changed[::-1]) // channels)
    if top is None:
        return None
    left, top = max(left - MARGIN, 0), max(top - MARGIN, 0)
    right, bottom = min(right + MARGIN, width), min(bottom + 1 + MARGIN, height)
    return left, top, right - left, bottom - top


class Cape(Gtk.Window):
    def __init__(self, monitor, frames, area):
        super().__init__(title="Zip")
        geometry = monitor.get_geometry()
        x, y, width, height = area
        self.frames = [frame.new_subpixbuf(x, y, width, height).copy() for frame in frames]
        self.frame = 0
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_below(True)
        self.stick()
        self.set_default_size(width, height)
        self.move(geometry.x + x, geometry.y + y)
        self.image = Gtk.Image.new_from_pixbuf(self.frames[0])
        self.add(self.image)
        self.connect("map-event", self._pass_clicks)
        GLib.timeout_add(FRAME_MS, self._next)

    def _pass_clicks(self, *_):
        # An empty input shape sends clicks to the desktop underneath.
        # xfwm4 copies it to the window's frame only when it changes on a
        # window it already manages, so it is set once mapped.
        self.input_shape_combine_region(cairo.Region())
        return False

    def _next(self):
        self.frame = (self.frame + 1) % len(self.frames)
        self.image.set_from_pixbuf(self.frames[self.frame])
        return GLib.SOURCE_CONTINUE


class Desktop:
    def __init__(self, wallpaper):
        self.wallpaper = wallpaper
        self.svg = art.svg_frames(wallpaper)
        self.windows = []
        Xfconf.init()
        self.channel = Xfconf.Channel.get("xfce4-desktop")
        self.channel.connect("property-changed", lambda *_: self.refresh())
        display = Gdk.Display.get_default()
        display.connect("monitor-added", lambda *_: self.refresh())
        display.connect("monitor-removed", lambda *_: self.refresh())
        Gdk.Screen.get_default().connect("size-changed", lambda *_: self.refresh())
        self.refresh()

    def ours(self, monitor):
        # xfdesktop names a monitor's settings after its connector, which
        # is what GDK reports as the model on X11.
        prefix = f"/backdrop/screen0/monitor{monitor.get_model()}/workspace0"
        return self.channel.get_string(f"{prefix}/last-image", "") == self.wallpaper

    def refresh(self):
        for window in self.windows:
            window.destroy()
        self.windows = []
        if len(self.svg) < 2:
            return
        display = Gdk.Display.get_default()
        for index in range(display.get_n_monitors()):
            monitor = display.get_monitor(index)
            if not self.ours(monitor):
                continue
            geometry = monitor.get_geometry()
            frames = [zoomed(data, geometry.width, geometry.height) for data in self.svg]
            area = moving_area(frames)
            if area is None:
                continue
            window = Cape(monitor, frames, area)
            window.show_all()
            self.windows.append(window)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: zoomies-desktop-zip WALLPAPER")
    if state.calm_screen():
        return
    Desktop(sys.argv[1])
    Gtk.main()
