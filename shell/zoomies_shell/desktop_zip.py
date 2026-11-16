"""Brings the older kids' wallpaper to life: clouds drift, the wind blows
past Zip and his cape flaps.

xfdesktop shows a still image, so a window covering each monitor draws the
wallpaper in layers instead: the sky, the clouds marked class="cloud"
drifting left, the wind lines marked id="wind" blowing back from Zip's
cape, then Zip, marked id="zip", playing his frames.
Everything is scaled and placed the way xfdesktop zooms the image, so the
window lines up with the still wallpaper pixel for pixel. Clicks go through
to the desktop, and the window steps aside when the kid picks another
wallpaper.

Only the parts that move are redrawn: old PCs draw without a GPU.
"""

import re
import sys
import xml.etree.ElementTree as ET

import cairo
import gi

from . import art, state

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Xfconf", "0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Xfconf  # noqa: E402

SVG = art.SVG
FRAME_MS = 100
# Each wind line blows this far left, fading, then starts again at the cape;
# a gust takes WIND_STEPS steps of STEP_MS.
WIND_SPAN = 220
WIND_STEPS = 20
# Clouds step together 20 times a second, each about a pixel at a time;
# the biggest, nearest ones drift fastest.
STEP_MS = 50
CLOUD_SPEED = 8
# Room for smoothing, which reaches a pixel past a shape.
MARGIN = 2


def cover(width, height, image_width, image_height):
    """Scale and offset of xfdesktop's "zoomed" style: the image covers the
    monitor, centred, with the same rounding."""
    scale = max(width / image_width, height / image_height)
    x = int((width - int(image_width * scale)) * 0.5)
    y = int((height - int(image_height * scale)) * 0.5)
    return scale, x, y


def zoomed(data, width, height, image_width, image_height):
    """The SVG as xfdesktop draws it on a monitor, transparent where it is."""
    scale, x, y = cover(width, height, image_width, image_height)
    image = art.pixbuf(data, int(image_width * scale), int(image_height * scale))
    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
    canvas.fill(0)
    image.composite(canvas, 0, 0, width, height, x, y, 1, 1, GdkPixbuf.InterpType.BILINEAR, 255)
    return canvas


def opaque_area(frames):
    """The rectangle any frame draws on."""
    width, height = frames[0].get_width(), frames[0].get_height()
    stride = frames[0].get_rowstride()
    left, top, right, bottom = width, None, 0, None
    for frame in frames:
        pixels = frame.get_pixels()
        for y in range(height):
            # Transparent pixels are all zero once composited.
            row = pixels[y * stride : y * stride + width * 4]
            stripped = row.lstrip(b"\0")
            if not stripped:
                continue
            top = y if top is None else min(top, y)
            bottom = y if bottom is None else max(bottom, y)
            left = min(left, (len(row) - len(stripped)) // 4)
            right = max(right, width - (len(row) - len(row.rstrip(b"\0"))) // 4)
    if top is None:
        return None
    left, top = max(left - MARGIN, 0), max(top - MARGIN, 0)
    right, bottom = min(right + MARGIN, width), min(bottom + 1 + MARGIN, height)
    return left, top, right - left, bottom - top


class Wallpaper:
    """The wallpaper SVG split into its layers."""

    def __init__(self, path):
        self.root = ET.parse(path).getroot()
        self.width = float(self.root.get("width"))
        self.height = float(self.root.get("height"))
        self.clouds = [g for g in self.root.iter(f"{{{SVG}}}g") if g.get("class") == "cloud"]
        self.zip = next(
            (g for g in self.root.iter(f"{{{SVG}}}g") if g.get("id") == "zip"), None
        )
        self.wind = next(
            (g for g in self.root.iter(f"{{{SVG}}}g") if g.get("id") == "wind"), None
        )

    @staticmethod
    def moving(element):
        return element.get("class") == "cloud" or element.get("id") in ("zip", "wind")

    def alone(self, name):
        """The SVG with only the defs and the element with that id."""
        root = ET.fromstring(ET.tostring(self.root))
        for child in list(root):
            if child.tag != f"{{{SVG}}}defs" and child.get("id") != name:
                root.remove(child)
        return root

    def sky(self):
        root = ET.fromstring(ET.tostring(self.root))
        for parent in list(root.iter()):
            for child in list(parent):
                if self.moving(child):
                    parent.remove(child)
        return ET.tostring(root)

    def zip_frames(self):
        return art.tree_frames(ET.ElementTree(self.alone("zip")))

    def wind_frames(self):
        """The wind lines blowing left from where the still wallpaper has
        them, each fading in and out, staggered so a gust never stops."""
        root = self.alone("wind")
        lines = [e for e in root.iter() if e.tag in (f"{{{SVG}}}line", f"{{{SVG}}}path")]
        frames = []
        for step in range(WIND_STEPS):
            for index, line in enumerate(lines):
                t = (step / WIND_STEPS + index / len(lines)) % 1
                line.set("transform", f"translate({-t * WIND_SPAN:.1f} 0)")
                line.set("opacity", f"{min(1, t * 6) * (1 - t):.2f}")
            frames.append(ET.tostring(root))
        return frames

    def cloud(self, group):
        """One cloud alone, its bounds in the wallpaper, and how big it is."""
        x, y = map(float, re.search(r"translate\(([-\d.]+) ([-\d.]+)\)", group.get("transform")).groups())
        size = float(re.search(r"scale\(([-\d.]+)\)", group.get("transform")).group(1))
        shapes = list(group.iter(f"{{{SVG}}}ellipse"))
        left = min(float(e.get("cx", 0)) - float(e.get("rx")) for e in shapes)
        right = max(float(e.get("cx", 0)) + float(e.get("rx")) for e in shapes)
        top = min(float(e.get("cy", 0)) - float(e.get("ry")) for e in shapes)
        bottom = max(float(e.get("cy", 0)) + float(e.get("ry")) for e in shapes)
        bounds = (x + left * size, y + top * size, (right - left) * size, (bottom - top) * size)
        svg = (
            f'<svg xmlns="{SVG}" viewBox="{bounds[0]} {bounds[1]} {bounds[2]} {bounds[3]}">'
            + ET.tostring(group, encoding="unicode")
            + "</svg>"
        )
        return svg.encode(), bounds, size


class Cloud:
    def __init__(self, surface, x, y, speed):
        self.surface = surface
        self.width, self.height = surface.get_width(), surface.get_height()
        self.x, self.y = x, y
        self.drawn = round(x)
        self.speed = speed


class Sky(Gtk.Window):
    def __init__(self, monitor, wallpaper):
        super().__init__(title="Zip")
        geometry = monitor.get_geometry()
        self.width, self.height = geometry.width, geometry.height
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_below(True)
        self.stick()
        self.set_default_size(self.width, self.height)
        self.move(geometry.x, geometry.y)
        self.wallpaper = wallpaper
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._draw)
        self.add(self.area)
        self.connect("map-event", self._pass_clicks)
        self.connect("realize", self._load)
        self.timers = []
        self.connect("destroy", lambda *_: [GLib.source_remove(t) for t in self.timers])

    def _surface(self, pixbuf):
        # Converted once: painting a pixbuf converts it on every draw.
        return Gdk.cairo_surface_create_from_pixbuf(pixbuf, 1, self.get_window())

    def _load(self, *_):
        w, h = self.width, self.height
        paper = self.wallpaper
        scale, ox, oy = cover(w, h, paper.width, paper.height)
        self.sky = self._surface(zoomed(paper.sky(), w, h, paper.width, paper.height))
        self.clouds = []
        for group in paper.clouds:
            svg, (bx, by, bw, bh), size = paper.cloud(group)
            image = art.pixbuf(svg, max(1, round(bw * scale)), max(1, round(bh * scale)))
            speed = CLOUD_SPEED * size * scale * STEP_MS / 1000
            self.clouds.append(Cloud(self._surface(image), ox + bx * scale, oy + by * scale, speed))
        self.zip = []
        self.zip_area = None
        if paper.zip is not None:
            frames = [zoomed(data, w, h, paper.width, paper.height) for data in paper.zip_frames()]
            self.zip_area = opaque_area(frames)
            if self.zip_area is not None:
                x, y, zw, zh = self.zip_area
                self.zip = [self._surface(f.new_subpixbuf(x, y, zw, zh)) for f in frames]
        self.wind = []
        self.wind_area = None
        if paper.wind is not None:
            frames = [zoomed(data, w, h, paper.width, paper.height) for data in paper.wind_frames()]
            self.wind_area = opaque_area(frames)
            if self.wind_area is not None:
                x, y, ww, wh = self.wind_area
                self.wind = [self._surface(f.new_subpixbuf(x, y, ww, wh)) for f in frames]
        self.frame = 0
        self.gust = 0
        self.timers.append(GLib.timeout_add(STEP_MS, self._step))
        if len(self.zip) > 1:
            self.timers.append(GLib.timeout_add(FRAME_MS, self._flap))

    def _pass_clicks(self, *_):
        # An empty input shape sends clicks to the desktop underneath.
        # xfwm4 copies it to the window's frame only when it changes on a
        # window it already manages, so it is set once mapped.
        self.input_shape_combine_region(cairo.Region())
        return False

    def _step(self):
        for cloud in self.clouds:
            cloud.x -= cloud.speed
            if cloud.x + cloud.width < 0:
                cloud.x += self.width + cloud.width
            x = round(cloud.x)
            if x != cloud.drawn:
                left = min(x, cloud.drawn)
                span = abs(x - cloud.drawn) + cloud.width
                if span > cloud.width + 1:
                    # Wrapped around: two separate places to redraw.
                    self.area.queue_draw_area(cloud.drawn, round(cloud.y), cloud.width, cloud.height)
                    self.area.queue_draw_area(x, round(cloud.y), cloud.width, cloud.height)
                else:
                    self.area.queue_draw_area(left, round(cloud.y), span, cloud.height)
                cloud.drawn = x
        if self.wind:
            self.gust = (self.gust + 1) % len(self.wind)
            self.area.queue_draw_area(*self.wind_area)
        return GLib.SOURCE_CONTINUE

    def _flap(self):
        self.frame = (self.frame + 1) % len(self.zip)
        self.area.queue_draw_area(*self.zip_area)
        return GLib.SOURCE_CONTINUE

    def _draw(self, _area, cr):
        cr.set_source_surface(self.sky, 0, 0)
        cr.paint()
        for cloud in self.clouds:
            cr.set_source_surface(cloud.surface, cloud.drawn, round(cloud.y))
            cr.paint()
        if self.wind:
            x, y, _, _ = self.wind_area
            cr.set_source_surface(self.wind[self.gust], x, y)
            cr.paint()
        if self.zip:
            x, y, _, _ = self.zip_area
            cr.set_source_surface(self.zip[self.frame], x, y)
            cr.paint()
        return True


class Desktop:
    def __init__(self, path):
        self.path = path
        self.wallpaper = Wallpaper(path)
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
        return self.channel.get_string(f"{prefix}/last-image", "") == self.path

    def refresh(self):
        for window in self.windows:
            window.destroy()
        self.windows = []
        display = Gdk.Display.get_default()
        for index in range(display.get_n_monitors()):
            monitor = display.get_monitor(index)
            if self.ours(monitor):
                window = Sky(monitor, self.wallpaper)
                window.show_all()
                self.windows.append(window)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: zoomies-desktop-zip WALLPAPER")
    if state.calm_screen():
        return
    Desktop(sys.argv[1])
    Gtk.main()
