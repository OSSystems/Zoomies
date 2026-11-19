"""Draws the boot splash's images from Zip's artwork.

Plymouth only moves, swaps and fades images, so everything that bends (the
cape, a wing) is drawn ahead of time as a loop of frames. Sizes are for a 1080-line
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
# Canvases in stage units around Zip's centre: (left, top, width, height).
HERO_BOX = (-96, -96, 192, 192)
# The flying pose Zip takes to leave: the side-on Super Zip, scaled so his
# body matches the front pose, nose up a little.
FLY_SCALE = 0.4
FLY_CENTRE = (350, 269)
FLY_TILT = -8
# Square, so that he can point up while he climbs off his cloud.
FLY_BOX = (-125, -125, 250, 250)
# The climb off the cloud, nose up, levelling out into the dash.
CLIMB = (-80, -60, -40, -22)
# Where his feet rest, in stage units below his centre, and the cloud he
# stands on there.
FEET = ZIP_ORIGIN[1] + ZIP_SCALE * 290
PERCH = 2.1
# Squashed as he crouches to jump or lands, stretched as he springs up.
CROUCH = (1.08, 0.86)
STRETCH = (0.93, 1.1)
# Asleep for the night: closed eyes, and the waving wing down like the
# other one.
CLOSED_EYES = (
    '<path d="M117 133 Q130 144 143 133 M164 133 Q177 144 190 133" fill="none" '
    'stroke="#172433" stroke-width="5" stroke-linecap="round"/>'
)
PUPILS = {"#172433", "white"}
WING = "#222d3c"
RESTING_WING = "M212 172 Q251 185 252 235 Q245 253 210 216Z"
# Stars for the night, in stage pixels on the 1920x1080 stage.
STARS = [
    (160, 120, 1.0), (420, 260, 0.7), (700, 90, 0.8), (980, 210, 1.1), (1260, 70, 0.7),
    (1500, 230, 0.9), (1780, 130, 1.0), (300, 470, 0.6), (1640, 440, 0.7), (560, 380, 0.8),
    (1120, 400, 0.6), (1860, 330, 0.6),
]
NIGHT = [("0", "#0f2348"), (".6", "#24477e"), ("1", "#3e6d94")]
SKY = [("0", "#7fd3ff"), (".55", "#b8ecff"), ("1", "#c8f5c0")]


def hovering(path):
    """Zip's front pose once per frame of the mascot's own loop: his cape
    hangs and sways and he waves, as he does on the mascot. Without the
    card, shadow or hover, which the theme does itself. Each frame takes the
    animations' values in turn, as librsvg would draw them still. The last
    frame is Zip asleep."""
    root = ET.parse(path).getroot()
    defs = ET.tostring(root.find(f"{{{SVG}}}defs"), encoding="unicode")
    # The figure is the group holding the most shapes; the groups around
    # it only place it on the card and bob it.
    shapes = (f"{{{SVG}}}path", f"{{{SVG}}}ellipse", f"{{{SVG}}}circle")
    body = max(root.iter(f"{{{SVG}}}g"), key=lambda g: sum(c.tag in shapes for c in g))
    animated = take_animations(body)
    count = min(len(values) for _, values in animated)
    frames = []
    for frame in range(count):
        for element, values in animated:
            element.set("d", values[frame])
        frames.append(hero(defs, "".join(ET.tostring(e, encoding="unicode") for e in body)))
    for element, values in animated:
        element.set("d", values[0])
        if element.get("fill") == WING:
            element.set("d", RESTING_WING)
    asleep = [
        e for e in body
        if not (e.tag == f"{{{SVG}}}ellipse" and e.get("fill") in PUPILS and float(e.get("rx")) < 12)
    ]
    frames.append(hero(defs, "".join(ET.tostring(e, encoding="unicode") for e in asleep) + CLOSED_EYES))
    for element, values in animated:
        element.set("d", values[0])
    still = "".join(ET.tostring(e, encoding="unicode") for e in body)
    frames.append(hero(defs, still, CROUCH))
    frames.append(hero(defs, still, STRETCH))
    return frames


def take_animations(figure):
    """Removes the figure's animations and returns each animated element with
    its values, the loop's repeated first frame dropped."""
    animated = []
    for element in figure.iter():
        for animation in element.findall(f"{{{SVG}}}animate"):
            values = animation.get("values").split(";")
            if len(values) > 1 and values[-1] == values[0]:
                values.pop()
            animated.append((element, values))
            element.remove(animation)
    return animated


def flying(path, tilt=FLY_TILT):
    """Super Zip once per frame of his cape's flap, without the card, shadow
    or speed lines. The flap is an SVG animation, which librsvg would draw
    still, so each frame takes the animation's values in turn."""
    root = ET.parse(path).getroot()
    figure = root.findall(f"{{{SVG}}}g")[-1]
    animated = take_animations(figure)
    count = min(len(values) for _, values in animated)
    x, y = FLY_CENTRE
    frames = []
    for frame in range(count):
        for element, values in animated:
            element.set("d", values[frame])
        body = ET.tostring(figure, encoding="unicode")
        frames.append(
            canvas(FLY_BOX, f'<g transform="scale({FLY_SCALE}) translate({-x} {-y})">{body}</g>', tilt=tilt)
        )
    return frames


def canvas(box, content, defs="", tilt=0):
    left, top, width, height = box
    return (
        f'<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width * PX}" height="{height * PX}" '
        f'viewBox="{left} {top} {width} {height}">{defs}'
        f'<g transform="rotate({tilt})">{content}</g></svg>'
    )


def hero(defs, body, squash=(1, 1)):
    x, y = ZIP_ORIGIN
    sx, sy = squash
    # Squashed from his feet, which stay on the cloud.
    return canvas(
        HERO_BOX,
        f'<g transform="translate(0 {FEET}) scale({sx} {sy}) translate(0 {-FEET})">'
        f'<g transform="translate({x} {y}) scale({ZIP_SCALE})">{body}</g></g>',
        defs,
    )


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


def sky(colours=SKY):
    # One column is enough: the theme stretches it across the screen, and
    # the stops match the greeter's background so the handover is seamless.
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in colours)
    return (
        f'<svg xmlns="{SVG}" width="4" height="1080" viewBox="0 0 4 1080">'
        f'<defs><linearGradient id="sky" x2="0" y2="1">{stops}</linearGradient></defs>'
        '<rect width="4" height="1080" fill="url(#sky)"/></svg>'
    )


def star():
    return (
        f'<svg xmlns="{SVG}" width="{12 * PX}" height="{12 * PX}" viewBox="-6 -6 12 12">'
        '<path d="M0 -6 Q1 -1 6 0 Q1 1 0 6 Q-1 1 -6 0 Q-1 -1 0 -6Z" fill="#fff6d5"/></svg>'
    )


def first_frame(clouds, perch):
    """The splash's first frame without Zip, on the 1920x1080 stage: the
    sky, the clouds where the theme starts them and the cloud he lands on.
    The boot menu shows it while Zoomies loads, so the splash seems to start
    on the same picture. The positions match the theme's layout()."""
    def place(svg, x, y):
        return svg.replace("<svg ", f'<svg x="{x:.0f}" y="{y:.0f}" ', 1)

    items = [place(clouds[i % 3], i * 345, 108 + (i * 291) % 810) for i in range(7)]
    feet = 534 + FEET * PX + 12 * PERCH * PX
    items.append(place(perch, 930 - 62 * PERCH * PX, feet - 32 * PERCH * PX))
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in SKY)
    return (
        f'<svg xmlns="{SVG}" width="1920" height="1080" viewBox="0 0 1920 1080">'
        f'<defs><linearGradient id="sky" x2="0" y2="1">{stops}</linearGradient></defs>'
        '<rect width="1920" height="1080" fill="url(#sky)"/>' + "".join(items) + "</svg>"
    )


def render(svg, out):
    subprocess.run(["rsvg-convert", "-o", out], input=svg.encode(), check=True)


def main():
    zip_svg, flying_svg, script, out = sys.argv[1:]
    *hover, asleep, crouch, stretch = hovering(zip_svg)
    for frame, svg in enumerate(hover):
        render(svg, f"{out}/hover-{frame}.png")
    render(asleep, f"{out}/asleep.png")
    render(crouch, f"{out}/crouch.png")
    render(stretch, f"{out}/stretch.png")
    flyer = flying(flying_svg)
    for frame, svg in enumerate(flyer):
        render(svg, f"{out}/fly-{frame}.png")
    for step, tilt in enumerate(CLIMB):
        for frame, svg in enumerate(flying(flying_svg, tilt)):
            render(svg, f"{out}/climb-{step}-{frame}.png")
    render(cloud(PERCH), f"{out}/perch.png")
    clouds = [cloud(scale) for scale in (0.55, 0.9, 1.25)]
    for size, svg in enumerate(clouds):
        render(svg, f"{out}/cloud-{size}.png")
    render(first_frame(clouds, cloud(PERCH)), f"{out}/first-frame.png")
    for size, length in enumerate((40, 70, 100)):
        render(streak(length), f"{out}/streak-{size}.png")
    render(sky(), f"{out}/sky.png")
    render(sky(NIGHT), f"{out}/night.png")
    render(sky([("0", "#000"), ("1", "#000")]), f"{out}/black.png")
    render(star(), f"{out}/star.png")
    # The theme lines the canvases up on Zip's centre.
    values = {
        "HOVER_FRAMES": len(hover),
        "CLIMB_STEPS": len(CLIMB),
        "FEET": round(FEET * PX),
        # Where the cloud's own middle is in its image, and how far below
        # his feet it sits, so that they sink into it a little.
        "PERCH_X": round(62 * PERCH * PX),
        "PERCH_Y": round(32 * PERCH * PX),
        "PERCH_DROP": round(12 * PERCH * PX),
        "FLY_FRAMES": len(flyer),
        "FLY_X": -FLY_BOX[0] * PX,
        "FLY_Y": -FLY_BOX[1] * PX,
        "HERO_X": -HERO_BOX[0] * PX,
        "HERO_Y": -HERO_BOX[1] * PX,
        "STARS": len(STARS),
        "STAR_LIST": "".join(
            f"stars[{i}].x = {x}; stars[{i}].y = {y}; stars[{i}].size = {size};\n"
            for i, (x, y, size) in enumerate(STARS)
        ),
    }
    with open(script) as source:
        text = source.read()
    for name, value in values.items():
        text = text.replace(f"@{name}@", str(value))
    with open(f"{out}/zoomies.script", "w") as target:
        target.write(text)

if __name__ == "__main__":
    main()
