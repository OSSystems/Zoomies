"""Zip's artwork, kept free of any GTK version so GTK 3 and 4 apps share it."""

import xml.etree.ElementTree as ET

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def pixbuf(data, width=-1, height=-1):
    """The SVG data drawn at that size. Given one side only, it keeps its
    proportions; given both, it fills them exactly."""
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
    keep = width < 0 or height < 0
    return GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, width, height, keep, None)


def svg_frames(path):
    """The SVG once per frame of its <animate> and translating
    <animateTransform> loops.

    librsvg draws only the first frame of an SVG animation, so the frames
    are rendered one by one and shown in turn.
    """
    return tree_frames(ET.parse(path))


def tree_frames(tree):
    """svg_frames for an SVG already parsed."""
    animated = []
    for element in list(tree.iter()):
        for animation in list(element):
            tag = animation.tag
            if tag == f"{{{SVG}}}animate":
                attribute = animation.get("attributeName")
                frame = str
            elif (
                tag == f"{{{SVG}}}animateTransform"
                and animation.get("type") == "translate"
            ):
                attribute = "transform"
                frame = "translate({})".format
            else:
                continue
            values = animation.get("values").split(";")
            # A loop repeats its first frame at the end.
            if len(values) > 1 and values[-1] == values[0]:
                values.pop()
            animated.append((element, attribute, [frame(v) for v in values]))
            element.remove(animation)
    count = min((len(values) for *_, values in animated), default=1)
    frames = []
    for frame in range(count):
        for element, attribute, values in animated:
            element.set(attribute, values[frame])
        frames.append(ET.tostring(tree.getroot()))
    return frames
