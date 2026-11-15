"""Draws the boot splash's images from Zip's artwork.

Plymouth only moves, swaps and fades images, so everything that bends (the
cape) is drawn ahead of time as a loop of frames. Sizes are for a 1080-line
screen; the theme scales them once at start, not on every frame.

Usage: render.py ZIP_SVG FLYING_SVG SCRIPT OUT_DIR
"""

import math
import subprocess
import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# The designs use a 640x360 stage; three pixels per unit fills 1080 lines.
PX = 3
# Zip's own drawing, scaled to the stage. The figure keeps its art
# coordinates so it stays identical to the mascot.
ZIP_SCALE = 150 / 220
ZIP_ORIGIN = (-75 - 50 * ZIP_SCALE, -85.5 - 50 * ZIP_SCALE)
TILT = -6
# Canvases in stage units around Zip's centre: (left, top, width, height).
HERO_BOX = (-88, -96, 176, 192)
CAPE_BOX = (-200, -45, 210, 150)
CAPE_FRAMES = 15
# The flying pose Zip takes to leave: the side-on Super Zip, scaled so his
# body matches the front pose, nose up a little.
FLY_SCALE = 0.4
FLY_CENTRE = (350, 269)
FLY_TILT = -8
FLY_BOX = (-125, -64, 250, 128)
# The mascot's own cape and its fold.
CAPE_COLOURS = {"#e2453c", "#b8322d"}
SKY = [("0", "#7fd3ff"), (".55", "#b8ecff"), ("1", "#c8f5c0")]


def figure(path):
    """Zip's defs and figure in the art's own coordinates, still: without
    the card, shadow, hover or the cape that hangs down behind him, since
    the splash streams its own cape in the wind."""
    root = ET.parse(path).getroot()
    defs = root.find(f"{{{SVG}}}defs")
    for element in list(root.iter()):
        for child in list(element):
            if child.tag in (f"{{{SVG}}}animate", f"{{{SVG}}}animateTransform"):
                element.remove(child)
    # The figure is the group holding the most shapes; the groups around
    # it only place it on the card.
    shapes = (f"{{{SVG}}}path", f"{{{SVG}}}ellipse", f"{{{SVG}}}circle")
    body = max(root.iter(f"{{{SVG}}}g"), key=lambda g: sum(c.tag in shapes for c in g))
    for child in list(body):
        if child.get("fill") in CAPE_COLOURS:
            body.remove(child)
    return ET.tostring(defs, encoding="unicode"), "".join(
        ET.tostring(e, encoding="unicode") for e in body
    )


def flying(path):
    """Super Zip once per frame of his cape's flap, without the card, shadow
    or speed lines. The flap is an SVG animation, which librsvg would draw
    still, so each frame takes the animation's values in turn."""
    root = ET.parse(path).getroot()
    figure = root.findall(f"{{{SVG}}}g")[-1]
    animated = []
    for element in figure.iter():
        for animation in element.findall(f"{{{SVG}}}animate"):
            values = animation.get("values").split(";")
            # A loop repeats its first frame at the end.
            if len(values) > 1 and values[-1] == values[0]:
                values.pop()
            animated.append((element, values))
            element.remove(animation)
    count = min(len(values) for _, values in animated)
    x, y = FLY_CENTRE
    frames = []
    for frame in range(count):
        for element, values in animated:
            element.set("d", values[frame])
        body = ET.tostring(figure, encoding="unicode")
        frames.append(
            canvas(FLY_BOX, f'<g transform="scale({FLY_SCALE}) translate({-x} {-y})">{body}</g>', tilt=FLY_TILT)
        )
    return frames


def canvas(box, content, defs="", tilt=TILT):
    left, top, width, height = box
    return (
        f'<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width * PX}" height="{height * PX}" '
        f'viewBox="{left} {top} {width} {height}">{defs}'
        f'<g transform="rotate({tilt})">{content}</g></svg>'
    )


def cape(frame):
    """The cape at one point of its flap. Every wave turns a whole number of
    times per loop, so the last frame runs straight into the first."""
    phase = 2 * math.pi * frame / CAPE_FRAMES
    steps = 14
    top, bottom = [], []
    for i in range(steps + 1):
        u = i / steps
        wave = u * u * 13 * math.sin(phase - u * 5.5) + u * 4 * math.sin(2 * phase - u * 9)
        top.append((-6 - u * 150, -10 + u * 6 + wave))
        bottom.append(
            (-34 - u * 152, 34 + u * 36 + wave * 1.15 + u * u * 6 * math.sin(phase + 1))
        )
    tip, end = top[-1], bottom[-1]
    outline = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in top)
    outline += f" Q{(tip[0] + end[0]) / 2 - 12:.1f} {(tip[1] + end[1]) / 2:.1f} {end[0]:.1f} {end[1]:.1f}"
    outline += "".join(f" L{x:.1f} {y:.1f}" for x, y in reversed(bottom[:-1])) + "Z"
    fold = [(top[i][0], top[i][1] + 12 + i * 1.6) for i in range(3, steps + 1)]
    fold += [(top[i][0] + 6, top[i][1] + 22 + i * 2.2) for i in range(steps, 2, -1)]
    shade = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in fold) + "Z"
    # Super Zip's red, so the cape keeps its colour when he changes pose.
    defs = (
        '<defs><linearGradient id="cape" x1="1" x2="0">'
        '<stop stop-color="#cf3a32"/><stop offset="1" stop-color="#e2453c"/>'
        "</linearGradient></defs>"
    )
    return canvas(
        CAPE_BOX,
        f'<path d="{outline}" fill="url(#cape)"/>'
        f'<path d="{shade}" fill="#b8322c" opacity=".6"/>',
        defs,
    )


def hero(defs, body):
    x, y = ZIP_ORIGIN
    return canvas(HERO_BOX, f'<g transform="translate({x} {y}) scale({ZIP_SCALE})">{body}</g>', defs)


def cloud(scale):
    w, h = 130 * scale, 50 * scale
    return (
        f'<svg xmlns="{SVG}" width="{w * PX:.0f}" height="{h * PX:.0f}" viewBox="-62 -32 130 50">'
        '<g fill="#fff" opacity=".9"><ellipse rx="40" ry="16"/>'
        '<ellipse cx="-16" cy="-10" rx="20" ry="16"/><ellipse cx="14" cy="-12" rx="24" ry="18"/>'
        "</g></svg>"
    )


def streak(length):
    return (
        f'<svg xmlns="{SVG}" width="{(length + 6) * PX}" height="{6 * PX}" viewBox="-3 -3 {length + 6} 6">'
        f'<line x2="{length}" stroke="#fff" stroke-width="6" stroke-linecap="round" opacity=".8"/></svg>'
    )


def sky():
    # One column is enough: the theme stretches it across the screen, and
    # the stops match the greeter's background so the handover is seamless.
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in SKY)
    return (
        f'<svg xmlns="{SVG}" width="4" height="1080" viewBox="0 0 4 1080">'
        f'<defs><linearGradient id="sky" x2="0" y2="1">{stops}</linearGradient></defs>'
        '<rect width="4" height="1080" fill="url(#sky)"/></svg>'
    )


def render(svg, out):
    subprocess.run(["rsvg-convert", "-o", out], input=svg.encode(), check=True)


def main():
    zip_svg, flying_svg, script, out = sys.argv[1:]
    defs, body = figure(zip_svg)
    render(hero(defs, body), f"{out}/zip.png")
    flyer = flying(flying_svg)
    for frame, svg in enumerate(flyer):
        render(svg, f"{out}/fly-{frame}.png")
    for frame in range(CAPE_FRAMES):
        render(cape(frame), f"{out}/cape-{frame}.png")
    for size, scale in enumerate((0.55, 0.9, 1.25)):
        render(cloud(scale), f"{out}/cloud-{size}.png")
    for size, length in enumerate((40, 70, 100)):
        render(streak(length), f"{out}/streak-{size}.png")
    render(sky(), f"{out}/sky.png")
    # The theme lines the canvases up on Zip's centre.
    values = {
        "CAPE_FRAMES": CAPE_FRAMES,
        "FLY_FRAMES": len(flyer),
        "FLY_X": -FLY_BOX[0] * PX,
        "FLY_Y": -FLY_BOX[1] * PX,
        "HERO_X": -HERO_BOX[0] * PX,
        "HERO_Y": -HERO_BOX[1] * PX,
        "CAPE_X": -CAPE_BOX[0] * PX,
        "CAPE_Y": -CAPE_BOX[1] * PX,
    }
    with open(script) as source:
        text = source.read()
    for name, value in values.items():
        text = text.replace(f"@{name}@", str(value))
    with open(f"{out}/zoomies.script", "w") as target:
        target.write(text)

if __name__ == "__main__":
    main()
