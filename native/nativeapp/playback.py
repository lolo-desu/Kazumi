import time
from gi.repository import Gtk, Gdk, GLib, Adw
from .danmaku import Overlay, parse_comments
from .player import Video


class Playback(Gtk.Box):
    def __init__(
        self, window, item, name, url, headers=None, audio=None, page_url=None
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.window, self.item, self.name = window, item.copy(), name
        self.url, self.page_url = url, page_url or url
        self.headers, self.audio = headers, audio
        self.position, self.duration, self.last_save = 0.0, 0.0, 0
        self.video = Video(window.message, window.store.get("volume", 80))
        self.danmaku = Overlay(window.store)
        surface = Gtk.Overlay(child=self.video)
        surface.add_overlay(self.danmaku)
        self.append(surface)
        self.danmaku_segments = set()
        self.danmaku_identifier = None
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for edge in ("start", "end", "top", "bottom"):
            getattr(controls, "set_margin_" + edge)(12)
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        self.seek.connect("change-value", self.seek_changed)
        controls.append(self.seek)
        bar = Gtk.Box(spacing=8)
        self.pause = Gtk.Button(
            icon_name="media-playback-pause-symbolic",
            tooltip_text="播放 / 暂停（空格）",
        )
        self.pause.connect("clicked", lambda *_: self.video.command("cycle", "pause"))
        bar.append(self.pause)
        self.clock = Gtk.Label(label="00:00 / 00:00", hexpand=True, xalign=0)
        bar.append(self.clock)
        speed = Gtk.DropDown.new_from_strings(
            ["0.5×", "0.75×", "1×", "1.25×", "1.5×", "2×", "3×"]
        )
        speeds = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]
        speed.set_selected(
            speeds.index(window.store.get("speed", 1))
            if window.store.get("speed", 1) in speeds
            else 2
        )
        speed.connect(
            "notify::selected",
            lambda *_: self.video.command("set", "speed", speeds[speed.get_selected()]),
        )
        bar.append(speed)
        volume = Gtk.VolumeButton()
        volume.set_value(window.store.get("volume", 80) / 100)
        volume.connect(
            "value-changed",
            lambda _, v: (
                self.video.command("set", "volume", round(v * 100)),
                window.store.set("volume", round(v * 100)),
            ),
        )
        bar.append(volume)
        menu = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="播放选项")
        pop = Gtk.Popover()
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for title, callback in [
            ("导入弹幕", self.import_danmaku),
            ("在线弹幕", self.online_danmaku),
            ("弹幕设置", self.danmaku_settings),
            ("加载字幕", self.subtitle),
            ("切换字幕", lambda: self.video.command("cycle", "sid")),
            ("切换音轨", lambda: self.video.command("cycle", "aid")),
            ("下载本集", self.download),
            ("保存截图", self.screenshot),
            (
                "切换宽高比",
                lambda: self.video.command(
                    "cycle-values", "video-aspect-override", "-1", "16:9", "4:3"
                ),
            ),
        ]:
            b = Gtk.Button(label=title)
            b.connect("clicked", lambda _, f=callback: (f(), pop.popdown()))
            options.append(b)
        pop.set_child(options)
        menu.set_popover(pop)
        bar.append(menu)
        fullscreen = Gtk.Button(
            icon_name="view-fullscreen-symbolic", tooltip_text="全屏（F）"
        )
        fullscreen.connect("clicked", lambda *_: self.fullscreen())
        bar.append(fullscreen)
        controls.append(bar)
        self.append(controls)
        self.set_focusable(True)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self.key)
        self.add_controller(key)
        self.timer = GLib.timeout_add(750, self.tick)
        self.connect("unrealize", self.unrealize_player)
        self.video.connect(
            "realize",
            lambda *_: self.video.command("set", "speed", window.store.get("speed", 1)),
        )
        history = next(
            (
                x
                for x in window.store.items("history")
                if str(x["id"]) == str(item["id"])
            ),
            {},
        )
        start = (
            history.get("position", 0)
            if history.get("page_url") == self.page_url
            and window.store.get("remember", True)
            else 0
        )
        self.video.load(url, headers, audio, start)

    def fullscreen(self):
        self.window.unfullscreen() if self.window.is_fullscreen() else self.window.fullscreen()

    def key(self, controller, key, code, state):
        commands = {
            Gdk.KEY_space: ("cycle", "pause"),
            Gdk.KEY_Left: ("seek", -5),
            Gdk.KEY_Right: ("seek", 5),
            Gdk.KEY_Up: ("add", "volume", 5),
            Gdk.KEY_Down: ("add", "volume", -5),
        }
        if key in commands:
            self.video.command(*commands[key])
            return True
        if key in (Gdk.KEY_f, Gdk.KEY_F):
            self.fullscreen()
            return True
        return False

    def seek_changed(self, scale, scroll, value):
        self.video.command("seek", max(0, min(value, self.duration)), "absolute")
        return False

    @staticmethod
    def timestamp(value):
        value = int(value)
        return (
            f"{value // 3600:d}:{value // 60 % 60:02d}:{value % 60:02d}"
            if value >= 3600
            else f"{value // 60:02d}:{value % 60:02d}"
        )

    def tick(self):
        if self.video.closed:
            return False
        self.video.status(self.update)
        return True

    def update(self, status):
        if self.video.closed:
            return False
        self.position = float(status.get("time-pos", self.position))
        self.duration = float(status.get("duration", self.duration))
        self.danmaku.sync(
            self.position, status.get("pause") == "yes", float(status.get("speed", 1))
        )
        if self.danmaku_identifier is not None and getattr(
            self.window.service, "danmaku_segmented", False
        ):
            self.load_danmaku_segment()
        self.seek.set_range(0, max(self.duration, 1))
        self.seek.set_value(self.position)
        self.clock.set_text(
            self.timestamp(self.position) + " / " + self.timestamp(self.duration)
        )
        self.pause.set_icon_name(
            "media-playback-start-symbolic"
            if status.get("pause") == "yes"
            else "media-playback-pause-symbolic"
        )
        if time.monotonic() - self.last_save > 10:
            self.save()
        return False

    def save(self):
        if self.position > 0 and self.window.store.get("remember", True):
            self.window.store.put(
                "history",
                {
                    **self.item,
                    "episode": self.name,
                    "page_url": self.page_url,
                    "position": self.position,
                    "duration": self.duration,
                },
            )
        self.last_save = time.monotonic()

    def pause_and_save(self):
        self.video.command("set", "pause", "yes")
        self.save()

    def unrealize_player(self, *_):
        self.save()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def subtitle(self):
        dialog = Gtk.FileDialog(title="加载字幕")

        def selected(dialog, result):
            try:
                self.video.command(
                    "sub-add", dialog.open_finish(result).get_path(), "select"
                )
            except GLib.Error:
                pass

        dialog.open(self.window, None, selected)

    def download(self):
        try:
            self.window.downloads.start(
                self.item, self.name, self.url, self.headers, self.audio
            )
            self.window.message("已加入下载队列")
        except Exception as error:
            self.window.message(str(error))

    def screenshot(self):
        dialog = Gtk.FileDialog(title="保存视频截图", initial_name="screenshot.png")

        def selected(dialog, result):
            try:
                self.video.command(
                    "screenshot-to-file", dialog.save_finish(result).get_path(), "video"
                )
            except GLib.Error:
                pass

        dialog.save(self.window, None, selected)

    def import_danmaku(self):
        dialog = Gtk.FileDialog(title="导入 JSON / XML 弹幕")

        def chosen(dialog, result):
            try:
                path = dialog.open_finish(result).get_path()
            except GLib.Error:
                return
            from pathlib import Path

            def read():
                if Path(path).stat().st_size > 32 * 1024 * 1024:
                    raise ValueError("弹幕文件过大")
                return parse_comments(Path(path).read_text())

            self.window.async_call(
                read,
                lambda comments: (
                    self.danmaku.add(comments),
                    self.window.message(f"已加载 {len(comments)} 条弹幕"),
                ),
                scoped=False,
            )

        dialog.open(self.window, None, chosen)

    def online_danmaku(self):
        self.window.message("正在查询弹幕…")

        def show(episodes):
            dialog = Adw.Dialog(
                title="选择弹幕剧集", content_width=500, content_height=550
            )
            group = Adw.PreferencesGroup()
            for episode in episodes:
                row = Adw.ActionRow(
                    title=episode["title"], activatable=True, use_markup=False
                )

                def chosen(_, identifier=episode["id"]):
                    dialog.close()
                    self.danmaku_identifier = identifier
                    self.danmaku_segments.clear()
                    self.danmaku.comments = []
                    self.danmaku.configure()
                    self.load_danmaku_segment()

                row.connect("activated", chosen)
                group.add(row)
            toolbar = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=group))
            toolbar.add_top_bar(Adw.HeaderBar())
            dialog.set_child(toolbar)
            dialog.present(self.window)

        self.window.async_call(
            lambda: self.window.service.danmaku_episodes(self.item), show, scoped=False
        )

    def danmaku_settings(self):
        dialog = Adw.PreferencesDialog(title="弹幕设置")
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        enabled = Adw.SwitchRow(title="显示弹幕", active=self.danmaku.visible_danmaku)

        def update(key, value):
            self.window.store.set(key, value)
            self.danmaku.configure()

        enabled.connect(
            "notify::active", lambda *_: update("danmaku_enabled", enabled.get_active())
        )
        group.add(enabled)
        for title, key, minimum, maximum, step in [
            ("字号", "danmaku_font", 12, 48, 1),
            ("不透明度", "danmaku_opacity", 0.1, 1, 0.05),
            ("显示区域", "danmaku_area", 0.1, 1, 0.1),
            ("延迟（秒）", "danmaku_offset", -120, 120, 0.5),
        ]:
            row = Adw.SpinRow.new_with_range(minimum, maximum, step)
            row.set_title(title)
            row.set_value(self.danmaku.preferences[key])
            row.connect(
                "notify::value", lambda row, _, key=key: update(key, row.get_value())
            )
            group.add(row)
        blocked = Adw.EntryRow(title="屏蔽词（以逗号分隔）")
        blocked.set_text(",".join(self.danmaku.preferences["danmaku_blocked"]))
        blocked.connect(
            "changed",
            lambda row: update(
                "danmaku_blocked",
                [x.strip() for x in row.get_text().split(",") if x.strip()],
            ),
        )
        group.add(blocked)
        page.add(group)
        dialog.add(page)
        dialog.present(self.window)

    def load_danmaku_segment(self):
        identifier = self.danmaku_identifier
        segmented = getattr(self.window.service, "danmaku_segmented", False)
        segment = int(self.position // 360) + 1 if segmented else 1
        key = (identifier, segment)
        if key in self.danmaku_segments:
            return
        self.danmaku_segments.add(key)

        def fetch():
            return (
                self.window.service.danmaku_comments(identifier, segment)
                if segmented
                else self.window.service.danmaku_comments(identifier)
            )

        def show(comments):
            if not self.video.closed and identifier == self.danmaku_identifier:
                self.danmaku.add(comments)
                self.window.message(f"已加载 {len(comments)} 条弹幕")

        self.window.async_call(fetch, show, scoped=False)
