# Films a VM over VNC and reads its journal over a virtio port, both on the
# host's clock, so each flash on the screen lines up with what the system
# was doing. Screenshot polling misses flashes shorter than a screenshot,
# which on a busy host takes longer than the flashes we look for.
import csv
import json
import os
import re
import socket
import struct
import subprocess
import threading
import time

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

FPS = 30
VIDEO_W, VIDEO_H, STRIP = 960, 600, 40
# The sky is bright; the firmware, a text console and a blank screen are
# dark. The power off's night falls slowly and stays above this.
DARK = 60

# Units and messages worth a line on the chart; the rest of the journal is
# kept in events.csv.
HIGHLIGHT = re.compile(
    r"plymouth|zoomies-splash|zoomies-console|greetd|display-manager|"
    r"initrd-switch-root|session-\d+\.scope|systemd-poweroff|systemd-reboot"
)
# Events whose next seconds are worth a close look.
ANCHOR = re.compile(r"^kernel starts$|zoomies-splash-takeoff.service start$|plymouth-(poweroff|reboot).service start$|^» ")
KERNEL = re.compile(r"fbcon|simpledrm|efifb|vesafb|virtio_gpu|bochs|\[drm\]|Console: switching")


def unit_event(entry):
    unit = entry.get("UNIT") or entry.get("USER_UNIT") or ""
    message = entry.get("MESSAGE")
    if not isinstance(message, str):
        return None
    if entry.get("_TRANSPORT") == "kernel":
        return message if KERNEL.search(message) else None
    if unit and HIGHLIGHT.search(unit) and entry.get("JOB_TYPE"):
        return f"{unit} {entry['JOB_TYPE']} {entry.get('JOB_RESULT', '')}".strip()
    if entry.get("SYSLOG_IDENTIFIER") == "systemd-logind" and "session" in message.lower():
        return message
    if re.match(r"Reached target (Graphical|System Shutdown)|The system will", message):
        return message
    # The screens' own lines, without cage's and Mesa's start-up chatter.
    if entry.get("SYSLOG_IDENTIFIER", "").startswith("zoomies-") and not re.match(
        r"\d\d:\d\d:\d\d\.\d+ \[|libEGL|\s|/nix/store", message
    ):
        return f"{entry['SYSLOG_IDENTIFIER']}: {message}"[:90]
    return None


def recv_exact(sock, size):
    data = bytearray(size)
    view = memoryview(data)
    got = 0
    while got < size:
        n = sock.recv_into(view[got:])
        if n == 0:
            raise EOFError
        got += n
    return bytes(data)


def connect(path, until):
    while time.monotonic() < until:
        try:
            sock = socket.socket(socket.AF_UNIX)
            sock.connect(path)
            return sock
        except OSError:
            time.sleep(0.02)
    raise TimeoutError(path)


class Recorder:
    def __init__(self, node, name, ffmpeg):
        self.node = node
        self.name = name
        self.ffmpeg_bin = ffmpeg
        self.out = os.path.join(node.out_dir, name)
        os.makedirs(self.out, exist_ok=True)
        self.lock = threading.Lock()
        self.fb = bytearray()
        self.size = (0, 0)
        self.samples = []
        self.lines = []
        self.marks = []
        self.label = ""
        self.stopping = threading.Event()
        self.threads = []

    def now(self):
        return time.monotonic() - self.start

    def mark(self, text):
        self.marks.append((self.now(), text))
        self.node.log(f"[{self.name}] {self.now():7.2f}s {text}")

    def begin(self, **start_args):
        """Powers the VM on and films it until it is gone."""
        self.start = time.monotonic()
        self.video = subprocess.Popen(
            [self.ffmpeg_bin, "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{VIDEO_W}x{VIDEO_H + STRIP}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", os.path.join(self.out, "video.mp4")],
            stdin=subprocess.PIPE,
        )
        self.mark("power on")
        self.serial = []
        log_serial = self.node.log_serial

        def timed(line):
            self.serial.append((self.now(), line))
            log_serial(line)

        setattr(self.node, "log_serial", timed)
        self.node.start(**start_args)
        for target in (self.film, self.read_journal, self.sample):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.threads.append(thread)

    # The VNC client: raw pixels only, which over a local socket is cheaper
    # than decoding anything compressed in Python.
    def film(self):
        sock = connect(os.path.join(self.node.state_dir, "vnc"), time.monotonic() + 30)
        try:
            recv_exact(sock, 12)
            sock.sendall(b"RFB 003.008\n")
            types = recv_exact(sock, recv_exact(sock, 1)[0])
            assert 1 in types, types
            sock.sendall(b"\x01")
            assert recv_exact(sock, 4) == b"\0\0\0\0"
            sock.sendall(b"\x01")
            width, height = struct.unpack(">HH", recv_exact(sock, 4))
            recv_exact(sock, 16)
            recv_exact(sock, struct.unpack(">I", recv_exact(sock, 4))[0])
            # 32 bits, little endian, red at bit 16: BGRX in memory.
            sock.sendall(struct.pack(">B3xBBBBHHHBBB3x", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
            # Raw, and DesktopSize for the firmware, GRUB and Linux changing modes.
            sock.sendall(struct.pack(">BxHii", 2, 2, 0, -223))
            self.resize(width, height)
            incremental = 0
            while True:
                sock.sendall(struct.pack(">BBHHHH", 3, incremental, 0, 0, *self.size))
                incremental = 1
                kind = recv_exact(sock, 1)[0]
                if kind == 2:
                    continue
                if kind == 3:
                    recv_exact(sock, 3)
                    recv_exact(sock, struct.unpack(">I", recv_exact(sock, 4))[0])
                    continue
                assert kind == 0, kind
                count = struct.unpack(">xH", recv_exact(sock, 3))[0]
                rects = []
                for _ in range(count):
                    x, y, w, h, encoding = struct.unpack(">HHHHi", recv_exact(sock, 12))
                    if encoding == -223:
                        rects.append((x, y, w, h, None))
                    else:
                        assert encoding == 0, encoding
                        rects.append((x, y, w, h, recv_exact(sock, w * h * 4)))
                with self.lock:
                    for x, y, w, h, pixels in rects:
                        if pixels is None:
                            self.resize(w, h)
                            incremental = 0
                            continue
                        stride = self.size[0] * 4
                        for row in range(h):
                            at = (y + row) * stride + x * 4
                            self.fb[at:at + w * 4] = pixels[row * w * 4:(row + 1) * w * 4]
        except (EOFError, OSError):
            pass

    def resize(self, width, height):
        self.size = (width, height)
        self.fb = bytearray(width * height * 4)

    # Journal entries carry the guest's monotonic clock; entries that arrive
    # as they happen give its offset from the host's, per boot.
    def read_journal(self):
        sock = connect(os.path.join(self.node.state_dir, "events"), time.monotonic() + 30)
        buffer = b""
        while True:
            try:
                chunk = sock.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            arrival = self.now()
            buffer += chunk
            *complete, buffer = buffer.split(b"\n")
            for line in complete:
                try:
                    self.lines.append((arrival, json.loads(line)))
                except ValueError:
                    pass

    def sample(self):
        font = ImageFont.load_default(size=22)
        previous = None
        frame = 0
        while not self.stopping.is_set():
            due = self.start + frame / FPS
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            with self.lock:
                size = self.size
                pixels = bytes(self.fb)
            if size[0] and size[1]:
                image = Image.frombuffer("RGB", size, pixels, "raw", "BGRX", 0, 1)
            else:
                image = Image.new("RGB", (16, 10))
            thumb = image.resize((160, 100), Image.Resampling.BILINEAR).convert("L")
            luma = ImageStat.Stat(thumb).mean[0]
            dark = sum(thumb.histogram()[:40]) / (160 * 100)
            change = ImageStat.Stat(ImageChops.difference(thumb, previous)).mean[0] if previous else 0.0
            previous = thumb

            canvas = Image.new("RGB", (VIDEO_W, VIDEO_H + STRIP), (40, 40, 40))
            scale = min(VIDEO_W / image.width, VIDEO_H / image.height)
            fitted = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                  Image.Resampling.BILINEAR)
            canvas.paste(fitted, ((VIDEO_W - fitted.width) // 2, (VIDEO_H - fitted.height) // 2))
            t = frame / FPS
            ImageDraw.Draw(canvas).text(
                (8, VIDEO_H + 8), f"{self.name} {t:7.2f}s {size[0]}x{size[1]}  {self.label}"[:90],
                fill=(255, 255, 255), font=font)
            data = canvas.tobytes()
            # Behind schedule, the frame repeats, so video time stays real time.
            late = max(1, int((time.monotonic() - self.start) * FPS) - frame)
            for _ in range(late):
                self.samples.append((frame / FPS, size[0], size[1], luma, dark, change))
                try:
                    assert self.video.stdin
                    self.video.stdin.write(data)
                except BrokenPipeError:
                    return
                frame += 1
                change = 0.0
            self.update_label()

    def update_label(self):
        for arrival, entry in reversed(self.lines[-50:]):
            event = unit_event(entry)
            if event:
                self.label = event
                return

    def wait_for_journal(self, pattern, timeout):
        end = time.monotonic() + timeout
        seen = 0
        while time.monotonic() < end:
            lines = self.lines[seen:]
            seen += len(lines)
            for _arrival, entry in lines:
                if isinstance(entry.get("MESSAGE"), str) and re.search(pattern, entry["MESSAGE"]):
                    return
            time.sleep(0.1)
        raise TimeoutError(f"nothing in the journal matched {pattern}")

    def wait_for_power_off(self, timeout=120):
        end = time.monotonic() + timeout
        assert self.node.process
        while self.node.process.poll() is None:
            assert time.monotonic() < end, "the VM did not power off"
            time.sleep(0.1)
        self.mark("powered off")
        self.node.wait_for_shutdown()

    def finish(self, windows):
        """Stops filming and writes the evidence; windows are (name, start, end)."""
        time.sleep(1)
        self.stopping.set()
        for thread in self.threads:
            thread.join(timeout=10)
        assert self.video.stdin
        self.video.stdin.close()
        self.video.wait()

        boots = {}
        for arrival, entry in self.lines:
            boot = entry.get("_BOOT_ID")
            mono = entry.get("__MONOTONIC_TIMESTAMP")
            # Only the time journald received an entry says when it reached
            # the host; the kernel's own stamps come before journald runs.
            if boot and mono and entry.get("_TRANSPORT") != "kernel":
                offset = arrival - int(mono) / 1e6
                boots[boot] = min(boots.get(boot, offset), offset)
        order = list(boots)

        events = []
        with open(os.path.join(self.out, "journal.csv"), "w") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "boot", "arrival", "identifier", "unit", "message"])
            for arrival, entry in self.lines:
                boot = entry.get("_BOOT_ID")
                if boot not in boots:
                    continue
                stamp = entry.get("_SOURCE_MONOTONIC_TIMESTAMP") or entry["__MONOTONIC_TIMESTAMP"]
                # A loaded host can stall the guest, whose clock then jumps
                # ahead of the offset seen before; nothing happens after it
                # reached the host.
                at = min(int(stamp) / 1e6 + boots[boot], arrival)
                message = entry.get("MESSAGE")
                writer.writerow([f"{at:.3f}", order.index(boot), f"{arrival:.3f}",
                                 entry.get("SYSLOG_IDENTIFIER", ""), entry.get("UNIT", ""),
                                 message if isinstance(message, str) else ""])
                event = unit_event(entry)
                if event:
                    events.append((at, event))
        for boot in order:
            events.append((boots[boot], "kernel starts"))
        events += [(at, f"» {text}") for at, text in self.marks]
        events.sort()
        self.events = events
        with open(os.path.join(self.out, "events.txt"), "w") as f:
            for at, text in events:
                f.write(f"{at:8.3f} {text}\n")

        with open(os.path.join(self.out, "frames.csv"), "w") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "width", "height", "brightness", "dark", "change"])
            for row in self.samples:
                writer.writerow([f"{row[0]:.3f}", row[1], row[2], f"{row[3]:.1f}", f"{row[4]:.3f}", f"{row[5]:.1f}"])

        spans = self.dark_spans()
        jumps = [t for t, *_rest, change in self.samples if change > 40]
        with open(os.path.join(self.out, "report.txt"), "w") as f:
            f.write("Dark spans (brightness < %d):\n" % DARK)
            for start, end in spans:
                context = [text for at, text in events if start - 2 <= at <= end + 0.5]
                f.write(f"  {start:8.2f}s for {end - start:5.2f}s; around: {' | '.join(context)[:400]}\n")
            f.write("\nSudden changes (mean change > 40 in one frame):\n")
            for t in jumps:
                f.write(f"  {t:8.2f}s\n")
        self.chart(events, spans)
        self.filmstrips(windows, spans, events)
        return spans

    def lit_after(self, start):
        """When the screen first shows something bright: GRUB's sky after the firmware."""
        return next(t for t, _w, _h, luma, *_rest in self.samples if t >= start and luma >= DARK)

    def takeoffs(self):
        """From each time Zip takes off until the greeter is ready."""
        windows = []
        for at, text in self.events:
            if text.startswith("zoomies-splash-takeoff.service start"):
                ready = next((t for t, mark in self.marks if mark == "greeter ready" and t > at), None)
                assert ready, f"{self.name}: Zip took off at {at:.2f}s, after the greeter was ready"
                windows.append((at, ready))
        assert windows, f"{self.name}: Zip never took off"
        return windows

    def kernel_says(self, pattern, start):
        """When the serial console next printed pattern, such as the kernel's
        last words before a reset; the firmware blanks the screen right after."""
        for t, line in self.serial:
            if t >= start and pattern in line:
                return t
        raise AssertionError(f"{self.name}: the console never printed {pattern!r}")

    def assert_never_dark(self, spans, start, end, what):
        for dark_start, dark_end in spans:
            assert dark_end <= start or dark_start >= end, (
                f"{self.name}: the screen went dark for {dark_end - dark_start:.2f}s "
                f"at {dark_start:.2f}s while {what}"
            )

    def dark_spans(self):
        spans = []
        start = None
        for t, _w, _h, luma, _dark, _change in self.samples:
            if luma < DARK and start is None:
                start = t
            elif luma >= DARK and start is not None:
                spans.append((start, t))
                start = None
        if start is not None:
            spans.append((start, self.samples[-1][0] + 1 / FPS))
        return spans

    def chart(self, events, spans):
        length = self.samples[-1][0] if self.samples else 1
        px = 25
        width, height, top = int(length * px) + 40, 520, 200
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=13)
        for start, end in spans:
            draw.rectangle([20 + start * px, top, 20 + end * px, height - 20], fill=(255, 200, 200))
        for second in range(int(length) + 1):
            x = 20 + second * px
            draw.line([x, height - 20, x, height - 14 if second % 5 else height - 8], fill="gray")
            if second % 5 == 0:
                draw.text((x + 2, height - 18), f"{second}s", fill="gray", font=font)
        points = [(20 + t * px, height - 20 - luma * (height - 20 - top) / 255)
                  for t, _w, _h, luma, _d, _c in self.samples]
        if len(points) > 1:
            draw.line(points, fill=(30, 80, 200), width=2)
        # Labels closer than a line apart share one, so they stay legible.
        groups = []
        for at, text in events:
            x = 20 + at * px
            draw.line([x, top - 4, x, height - 20], fill=(200, 120, 0) if text.startswith("»") else (180, 180, 180))
            if groups and x - groups[-1][0] < 15:
                groups[-1][1].append(text)
            else:
                groups.append((x, [text]))
        for x, texts in groups:
            text = texts[0][:30] + (f" (+{len(texts) - 1})" if len(texts) > 1 else "")
            label = Image.new("RGBA", (top - 8, 15), (255, 255, 255, 0))
            ImageDraw.Draw(label).text((0, 0), text, fill="black", font=font)
            label = label.rotate(90, expand=True)
            image.paste(label, (int(x) - 14, 2), label)
        image.save(os.path.join(self.out, "chart.png"))

    def filmstrips(self, windows, spans, events):
        def strip(name, start, end, columns=8, tiles=48):
            start = max(0.0, start)
            fps = min(FPS, tiles / max(end - start, 0.1))
            rows = -(-int((end - start) * fps) // columns) or 1
            subprocess.run(
                [self.ffmpeg_bin, "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                 "-i", os.path.join(self.out, "video.mp4"),
                 "-vf", f"fps={fps:.3f},scale=240:-2,tile={columns}x{rows}:padding=2",
                 "-frames:v", "1", os.path.join(self.out, f"{name}.png")],
                check=True,
            )

        for name, start, end in windows:
            strip(name, start, end)
        # Each handover up close, at the full frame rate.
        for at, text in events:
            if ANCHOR.search(text):
                strip(f"at-{at:06.2f}s-{re.sub(r'[^a-z]+', '-', text.lower()).strip('-')}", at - 1.5, at + 2.5,
                      columns=12, tiles=120)
        for i, (start, end) in enumerate(spans):
            strip(f"dark-{i:02}-{start:06.2f}s", start - 0.5, end + 0.5)
