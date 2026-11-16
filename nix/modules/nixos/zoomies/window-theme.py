"""Draws the Zoomies xfwm4 theme: a light sky title strip with the app's
name and one big close button. Kids' apps are always maximized, so the
other buttons are never shown and are left blank.

Usage: window-theme.py DIRECTORY
"""

import math
import os
import sys

import cairo

TITLE = 48
BORDER = 4
CLOSE_WIDTH = 52
BUTTONS = ("hide", "maximize", "maximize-toggled", "menu", "shade", "shade-toggled", "stick", "stick-toggled")
CLOSE = {
    "active": "#ff8a80",
    "prelight": "#ff6b5f",
    "pressed": "#e85a50",
    "inactive": "#c3d3dd",
}
STRIP = {"active": ("#e9f8ff", "#bfe9ff"), "inactive": ("#f4f8fa", "#dde9f0")}


def rgb(color):
    return tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))


def save(directory, name, width, height, draw):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    draw(cairo.Context(surface))
    surface.write_to_png(os.path.join(directory, f"{name}.png"))


def strip(state):
    # Pressed and hovered buttons only show on the window in front.
    top, bottom = STRIP["inactive" if state == "inactive" else "active"]

    def draw(cr):
        gradient = cairo.LinearGradient(0, 0, 0, TITLE)
        gradient.add_color_stop_rgb(0, *rgb(top))
        gradient.add_color_stop_rgb(1, *rgb(bottom))
        cr.set_source(gradient)
        cr.paint()
        # The white line the shelf has on its top edge, mirrored.
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(0, TITLE - 3, 1000, 3)
        cr.fill()

    return draw


def solid(color):
    def draw(cr):
        cr.set_source_rgb(*rgb(color))
        cr.paint()

    return draw


def close(state):
    def draw(cr):
        strip(state)(cr)
        x, y, w, h, r = 6, 6, CLOSE_WIDTH - 12, TITLE - 15, 12
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, math.pi * 3 / 2)
        cr.close_path()
        cr.set_source_rgb(*rgb(CLOSE[state]))
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cx, cy, arm = x + w / 2, y + h / 2, 7
        cr.move_to(cx - arm, cy - arm)
        cr.line_to(cx + arm, cy + arm)
        cr.move_to(cx + arm, cy - arm)
        cr.line_to(cx - arm, cy + arm)
        cr.stroke()

    return draw


def main():
    directory = sys.argv[1]
    os.makedirs(directory, exist_ok=True)
    for state in ("active", "inactive"):
        for part in ("title-1", "title-2", "title-3", "title-4", "title-5", "top-left", "top-right"):
            save(directory, f"{part}-{state}", BORDER if part.startswith("top") else 8, TITLE, strip(state))
        edge = STRIP[state][1]
        save(directory, f"left-{state}", BORDER, 8, solid(edge))
        save(directory, f"right-{state}", BORDER, 8, solid(edge))
        save(directory, f"bottom-{state}", 8, BORDER, solid(edge))
        save(directory, f"bottom-left-{state}", BORDER, BORDER, solid(edge))
        save(directory, f"bottom-right-{state}", BORDER, BORDER, solid(edge))
    for state in CLOSE:
        save(directory, f"close-{state}", CLOSE_WIDTH, TITLE, close(state))
        for button in BUTTONS:
            save(directory, f"{button}-{state}", 1, TITLE, strip(state))
    with open(os.path.join(directory, "themerc"), "w") as themerc:
        themerc.write(
            "active_text_color=#1d3557\n"
            "inactive_text_color=#3d5a80\n"
            "button_offset=6\n"
            "button_spacing=0\n"
            "full_width_title=true\n"
            "maximized_offset=0\n"
            "show_app_icon=false\n"
            "title_horizontal_offset=16\n"
            "title_shadow_active=false\n"
            "title_shadow_inactive=false\n"
            "title_vertical_offset_active=-1\n"
            "title_vertical_offset_inactive=-1\n"
        )


if __name__ == "__main__":
    main()
