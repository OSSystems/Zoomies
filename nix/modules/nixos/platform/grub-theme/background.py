"""Draws the boot menu's background: the older kids' sky, with Zip
hovering beside the menu and pointing at it instead of flying across.
Usage: background.py WALLPAPER_SVG OUT_SVG ZIP_SVG
"""

import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# Where Zip's middle sits on the 1920x1080 wallpaper, and his size: left of
# the menu, level with its first entries. Far enough in that the crop GRUB
# makes on a 4:3 screen keeps him whole.
CENTRE = (420, 735)
SCALE = 1.45
# The mascot's waving wing, held out straight towards the menu.
POINTING = "M200 170 Q246 160 296 176 Q312 183 300 192 Q252 198 214 214Z"
WAVING = "#222d3c"


def zip_figure(path):
    root = ET.parse(path).getroot()
    defs = root.find(f"{{{SVG}}}defs")
    for element in list(root.iter()):
        for child in list(element):
            if child.tag in (f"{{{SVG}}}animate", f"{{{SVG}}}animateTransform"):
                element.remove(child)
    shapes = (f"{{{SVG}}}path", f"{{{SVG}}}ellipse", f"{{{SVG}}}circle")
    body = max(root.iter(f"{{{SVG}}}g"), key=lambda g: sum(c.tag in shapes for c in g))
    # Of the two wings, the waving one is the one that comes last.
    wings = [c for c in body if c.get("fill") == WAVING]
    wings[-1].set("d", POINTING)
    return defs, body


def main():
    wallpaper, out, mascot = sys.argv[1:]
    tree = ET.parse(wallpaper)
    root = tree.getroot()
    # Flying Zip and his wind belong to the desktop; here he is stopped.
    for group in list(root):
        if group.get("id") in ("zip", "wind"):
            root.remove(group)
    defs, body = zip_figure(mascot)
    root.find(f"{{{SVG}}}defs").extend(list(defs))
    x, y = CENTRE
    # Art coordinates put his middle at about (155, 180).
    place = ET.SubElement(root, f"{{{SVG}}}g", transform=f"translate({x} {y}) scale({SCALE}) translate(-155 -180)")
    place.extend(list(body))
    tree.write(out)


if __name__ == "__main__":
    main()
