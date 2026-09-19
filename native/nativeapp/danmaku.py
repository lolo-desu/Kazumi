"""GTK/Pango danmaku overlay with deterministic lanes and seek-safe timing."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import json
import time
import xml.etree.ElementTree as ET
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, PangoCairo


@dataclass(frozen=True)
class Comment:
    time: float
    text: str
    mode: int = 1
    color: int = 0xFFFFFF


def parse_comments(raw):
    """Import DanDanPlay JSON or standard Bilibili XML without executing markup."""
    result = []
    if raw.lstrip().startswith("<"):
        if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
            raise ValueError("不支持带有实体定义的弹幕 XML")
        for node in ET.fromstring(raw).iter("d"):
            fields = node.attrib.get("p", "").split(",")
            if len(fields) >= 4:
                try:
                    result.append(
                        Comment(
                            float(fields[0]),
                            node.text or "",
                            int(fields[1]),
                            int(fields[3]) & 0xFFFFFF,
                        )
                    )
                except ValueError:
                    continue
    else:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("comments", [])
        for value in data:
            fields = value.get("p", "").split(",")
            if len(fields) >= 3:
                try:
                    result.append(
                        Comment(
                            float(fields[0]),
                            str(value["m"]),
                            int(fields[1]),
                            int(fields[2]) & 0xFFFFFF,
                        )
                    )
                except (ValueError, KeyError):
                    continue
    return sorted(
        (c for c in result if c.time >= 0 and c.text and c.mode in (1, 4, 5)),
        key=lambda c: c.time,
    )


def schedule(comments, width, lanes, measure, duration=8, blocked=()):
    running = [None] * lanes
    top = [-1.0] * lanes
    bottom = [-1.0] * lanes
    result = []
    for comment in comments:
        if any(word and word in comment.text for word in blocked):
            continue
        size = measure(comment.text)
        if comment.mode in (4, 5):
            slots = top if comment.mode == 5 else bottom
            lane = next((i for i, t in enumerate(slots) if t <= comment.time), None)
            if lane is None:
                continue
            slots[lane] = comment.time + 4
        else:
            lane = None
            for i, previous in enumerate(running):
                if previous is None:
                    lane = i
                    break
                start, previous_width = previous
                previous_speed = (width + previous_width) / duration
                speed = (width + size) / duration
                # Entry gap and catch-up boundary must both remain clear.
                ready = max(
                    start + (previous_width + 16) / previous_speed,
                    start + duration - (width - 16) / speed,
                )
                if comment.time >= ready:
                    lane = i
                    break
            if lane is None:
                continue
            running[lane] = (comment.time, size)
        result.append((comment, lane, size))
    return result


class Overlay(Gtk.DrawingArea):
    def __init__(self, store):
        super().__init__(hexpand=True, vexpand=True, can_target=False)
        self.store = store
        self.comments = []
        self.plan = []
        self.times = []
        self.geometry = None
        self.position = 0
        self.paused = True
        self.updated = time.monotonic()
        self.speed = 1
        self.preferences = {}
        self.configure()
        self.set_draw_func(self.draw)
        self.add_tick_callback(lambda *_: (self.queue_draw(), True)[-1])

    def configure(self):
        for key, default in [
            ("danmaku_font", 24),
            ("danmaku_opacity", 0.85),
            ("danmaku_offset", 0),
            ("danmaku_area", 0.5),
            ("danmaku_blocked", []),
            ("danmaku_enabled", True),
        ]:
            self.preferences[key] = self.store.get(key, default)
        self.visible_danmaku = self.preferences["danmaku_enabled"]
        self.geometry = None
        self.queue_draw()

    def add(self, comments):
        self.comments = sorted(self.comments + comments, key=lambda c: c.time)
        self.geometry = None
        self.queue_draw()

    def sync(self, position, paused, speed=1):
        self.position = position
        self.paused = paused
        self.updated = time.monotonic()
        self.speed = speed

    def draw(self, widget, cr, width, height):
        if not self.visible_danmaku:
            return
        font = self.preferences.get("danmaku_font", 24)
        opacity = self.preferences.get("danmaku_opacity", 0.85)
        offset = self.preferences.get("danmaku_offset", 0)
        blocked = tuple(self.preferences.get("danmaku_blocked", []))
        lanes = max(
            1, int(height * self.preferences.get("danmaku_area", 0.5) / (font + 8))
        )
        geometry = (width, height, font, lanes, blocked)
        layout = PangoCairo.create_layout(cr)
        description = Pango.FontDescription.from_string(f"Sans {font}")
        description.set_absolute_size(font * Pango.SCALE)
        layout.set_font_description(description)
        if geometry != self.geometry:

            def measure(text):
                layout.set_text(text, -1)
                return layout.get_pixel_size()[0]

            self.plan = schedule(self.comments, width, lanes, measure, blocked=blocked)
            self.times = [c.time for c, _, _ in self.plan]
            self.geometry = geometry
        now = (
            self.position
            + (0 if self.paused else (time.monotonic() - self.updated) * self.speed)
            - offset
        )
        for comment, lane, text_width in self.plan[
            bisect_left(self.times, now - 8) : bisect_right(self.times, now)
        ]:
            age = now - comment.time
            if comment.mode != 1 and age > 4:
                continue
            x = (
                width - (width + text_width) * age / 8
                if comment.mode == 1
                else (width - text_width) / 2
            )
            y = (
                lane * (font + 8) + 6
                if comment.mode != 4
                else height - (lane + 1) * (font + 8) - 6
            )
            layout.set_text(comment.text, -1)
            cr.move_to(x, y)
            PangoCairo.layout_path(cr, layout)
            cr.set_line_width(2)
            cr.set_source_rgba(0, 0, 0, opacity)
            cr.stroke_preserve()
            color = comment.color
            cr.set_source_rgba(
                (color >> 16) / 255,
                ((color >> 8) & 255) / 255,
                (color & 255) / 255,
                opacity,
            )
            cr.fill()
