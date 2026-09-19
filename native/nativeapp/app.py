import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys
from datetime import datetime
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, Pango
from .storage import Store
from .network import Http
from .services import APP, Service


def margins(widget, value=18):
    for side in ("top", "bottom", "start", "end"):
        getattr(widget, "set_margin_" + side)(value)
    return widget


def button(icon, tooltip, callback):
    widget = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
    widget.connect("clicked", lambda *_: callback())
    return widget


def action_row(**kwargs):
    return Adw.ActionRow(use_markup=False, **kwargs)


def label(text, style=None):
    widget = Gtk.Label(label=str(text), xalign=0, wrap=True, selectable=True)
    if style:
        widget.add_css_class(style)
    return widget


class Window(Adw.ApplicationWindow):
    def __init__(self, app, store, offline=False):
        super().__init__(
            application=app, title=APP, default_width=1160, default_height=800
        )
        self.store, self.offline = store, offline
        from .downloads import Downloads

        self.downloads = Downloads(store)
        self.http = Http(store)
        self.service = Service(self.http, store)
        self.jobs = ThreadPoolExecutor(max_workers=3, thread_name_prefix="network")
        self.images = ThreadPoolExecutor(max_workers=2, thread_name_prefix="images")
        self.generation, self.closed, self.playback = 0, False, None
        self.messages = []
        self.current_route = "popular"
        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        self.split = Adw.NavigationSplitView(
            min_sidebar_width=190, max_sidebar_width=240
        )
        self.toast.set_child(self.split)
        breakpoint = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 700sp")
        )
        breakpoint.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint)
        sidebar = Adw.ToolbarView()
        sidebar.add_top_bar(Adw.HeaderBar(title_widget=Adw.WindowTitle(title=APP)))
        self.navlist = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.navlist.add_css_class("navigation-sidebar")
        routes = [
            ("popular", "热门", "view-grid-symbolic"),
            ("timeline", "时间表", "x-office-calendar-symbolic"),
            ("collect", "追番" if APP == "Kazumi" else "收藏", "starred-symbolic"),
            ("my", "我的", "avatar-default-symbolic"),
        ]
        self.routes = {}
        for route, title, icon in routes:
            row = action_row(title=title)
            row.add_prefix(Gtk.Image(icon_name=icon))
            row.route = route
            self.navlist.append(row)
            self.routes[route] = row
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.navlist
        )
        sidebar.set_content(scroll)
        self.navlist.connect(
            "row-selected", lambda _, row: self.navigate(row.route) if row else None
        )
        self.split.set_sidebar(Adw.NavigationPage(child=sidebar, title=APP))
        self.navigation = Adw.NavigationView()
        self.toolbar = Adw.ToolbarView()
        self.header = Adw.HeaderBar()
        self.page_title = Adw.WindowTitle(title="热门")
        self.header.set_title_widget(self.page_title)
        self.header.pack_end(
            button("system-search-symbolic", "搜索（Ctrl+F）", self.show_search)
        )
        self.header.pack_end(button("open-menu-symbolic", "设置", self.settings))
        self.toolbar.add_top_bar(self.header)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.toolbar.set_content(
            Gtk.ScrolledWindow(
                hscrollbar_policy=Gtk.PolicyType.NEVER, child=margins(self.body)
            )
        )
        self.navigation.add(
            Adw.NavigationPage(child=self.toolbar, title=APP, tag="root")
        )
        self.split.set_content(Adw.NavigationPage(child=self.navigation, title=APP))
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key)
        self.add_controller(keys)
        self.connect("close-request", self.close_window)
        self.apply_theme()
        self.navlist.select_row(self.routes["popular"])

    def key(self, controller, key, code, state):
        if state & Gdk.ModifierType.CONTROL_MASK and key == Gdk.KEY_f:
            self.show_search()
            return True
        if key == Gdk.KEY_Escape:
            if self.is_fullscreen():
                self.unfullscreen()
                return True
            return self.navigation.pop()
        return False

    def close_window(self, *_):
        self.closed = True
        self.downloads.close()
        self.generation += 1
        if self.playback:
            self.playback.save()
        self.jobs.shutdown(wait=False, cancel_futures=True)
        self.images.shutdown(wait=False, cancel_futures=True)
        return False

    def message(self, text):
        # Keep a bounded, credential-free in-app log so failures can be
        # inspected without opening a terminal.  Toasts remain the immediate
        # feedback for normal actions.
        text = str(text)
        self.messages.append(f"{datetime.now():%H:%M:%S}  {text[:500]}")
        del self.messages[:-200]
        if not self.closed:
            self.toast.add_toast(Adw.Toast(title=text[:250]))
        return False

    def async_call(self, operation, callback, error=None, scoped=True, image=False):
        generation = self.generation

        def guarded():
            if self.closed or (scoped and generation != self.generation):
                return None
            return operation()

        future = (self.images if image else self.jobs).submit(guarded)

        def completed(future):
            def deliver():
                if self.closed or (scoped and generation != self.generation):
                    return False
                try:
                    result = future.result()
                except Exception as exception:
                    (error or self.message)(str(exception))
                    return False
                callback(result)
                return False

            GLib.idle_add(deliver)

        future.add_done_callback(completed)

    def clear(self, box=None):
        box = box or self.body
        while (child := box.get_first_child()) is not None:
            box.remove(child)

    def status(self, title, description="", retry=None):
        self.clear()
        status = Adw.StatusPage(
            title=title,
            description=description,
            icon_name="dialog-information-symbolic",
        )
        if retry:
            action = Gtk.Button(label="重试", halign=Gtk.Align.CENTER)
            action.add_css_class("suggested-action")
            action.connect("clicked", lambda *_: retry())
            status.set_child(action)
        self.body.append(status)

    def load(self, operation, callback, retry=None):
        self.status("正在加载…")
        self.async_call(
            operation, callback, lambda error: self.status("无法加载", error, retry)
        )

    def navigate(self, route):
        if self.navlist.get_selected_row() != self.routes[route]:
            self.navlist.select_row(self.routes[route])
            return
        self.generation += 1
        self.navigation.pop_to_tag("root")
        self.current_route = route
        self.page_title.set_title(self.routes[route].get_title())
        self.split.set_show_content(True)
        self.clear()
        if route == "popular":
            if self.offline:
                self.status("热门", "测试模式：未连接网络")
                return
            self.list_page(self.service.browse)
        elif route == "timeline":
            self.load(
                self.service.calendar, self.calendar, lambda: self.navigate(route)
            )
        elif route == "collect":
            self.library("collect")
        elif route == "my":
            self.personal()

    def list_page(self, operation, page=1):
        def show(items):
            self.clear()
            self.cards(items)
            controls = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
            prev = Gtk.Button(label="上一页", sensitive=page > 1)
            prev.connect("clicked", lambda *_: self.list_page(operation, page - 1))
            next = Gtk.Button(label="下一页", sensitive=bool(items))
            next.connect("clicked", lambda *_: self.list_page(operation, page + 1))
            controls.append(prev)
            controls.append(Gtk.Label(label=str(page)))
            controls.append(next)
            self.body.append(controls)

        self.load(
            lambda: operation(page), show, lambda: self.list_page(operation, page)
        )

    def cards(self, items, box=None):
        box = box or self.body
        if not items:
            box.append(
                Adw.StatusPage(title="这里还没有内容", icon_name="folder-symbolic")
            )
            return
        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            min_children_per_line=1,
            max_children_per_line=5,
            column_spacing=16,
            row_spacing=16,
        )
        flow.set_activate_on_single_click(True)
        flow.connect("child-activated", lambda _, child: self.details(child.item))
        for item in items:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class("card")
            image = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
            image.set_size_request(150, 190 if APP == "Kazumi" else 115)
            card.append(image)
            title = Gtk.Label(
                label=item["title"],
                xalign=0,
                wrap=True,
                lines=2,
                ellipsize=Pango.EllipsizeMode.END,
            )
            title.set_max_width_chars(22)
            margins(title, 8)
            card.append(title)
            subtitle = Gtk.Label(
                label=item.get("subtitle", ""),
                xalign=0,
                ellipsize=Pango.EllipsizeMode.END,
            )
            subtitle.add_css_class("dim-label")
            margins(subtitle, 8)
            card.append(subtitle)
            child = Gtk.FlowBoxChild(child=card, tooltip_text=item["title"])
            child.item = item
            flow.append(child)
            if item.get("cover") and not self.offline:
                self.async_call(
                    lambda url=item["cover"]: self.http.image(url),
                    lambda path, image=image: image.set_filename(path),
                    lambda _: None,
                    image=True,
                )
        box.append(flow)

    def calendar(self, groups):
        self.clear()
        for name, items in groups:
            self.body.append(label(name, "title-2"))
            self.cards(items)

    def library(self, kind):
        self.clear()
        items = self.store.items(kind)
        self.cards(items)

    def show_search(self):
        self.generation += 1
        self.navigation.pop_to_tag("root")
        self.split.set_show_content(True)
        self.page_title.set_title("搜索")
        self.clear()
        entry = Gtk.SearchEntry(
            placeholder_text="搜索番剧" if APP == "Kazumi" else "搜索视频"
        )
        self.body.append(entry)
        results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.body.append(results)

        def search(*_):
            query = entry.get_text().strip()
            if not query:
                return
            self.generation += 1
            self.clear(results)
            results.append(label("正在搜索…"))

            def show(items):
                self.clear(results)
                self.cards(items, results)

            self.async_call(
                lambda: self.service.search(query),
                show,
                lambda e: (self.clear(results), results.append(label(e))),
            )

        entry.connect("activate", search)
        entry.grab_focus()

    def push(self, title, content):
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar(title_widget=Adw.WindowTitle(title=title)))
        toolbar.set_content(content)
        page = Adw.NavigationPage(child=toolbar, title=title)
        self.navigation.push(page)
        return page

    def details(self, item):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20), 24)
        clamp = Adw.Clamp(maximum_size=900, child=body)
        self.push(
            item["title"],
            Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER),
        )
        body.append(label(item["title"], "title-1"))
        body.append(label(item.get("subtitle", ""), "dim-label"))
        actions = Gtk.Box(spacing=8)
        collect = Gtk.MenuButton(label="收藏")
        pop = Gtk.Popover()
        choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for state in ("想看", "在看", "看过", "搁置", "抛弃", "移除收藏"):
            choice = Gtk.Button(label=state)

            def selected(_, state=state):
                self.service.set_collection(item, state)
                pop.popdown()
                self.message("已更新收藏")

            choice.connect("clicked", selected)
            choices.append(choice)
        pop.set_child(choices)
        collect.set_popover(pop)
        actions.append(collect)
        play = Gtk.Button(label="查找播放源" if APP == "Kazumi" else "播放")
        play.add_css_class("suggested-action")
        play.connect(
            "clicked",
            lambda *_: (
                self.sources(item, body) if APP == "Kazumi" else self.pili_play(item)
            ),
        )
        actions.append(play)
        actions.append(
            button(
                "web-browser-symbolic",
                "打开原站",
                lambda: Gio.AppInfo.launch_default_for_uri(item["url"], None),
            )
        )
        body.append(actions)
        summary = label(item.get("summary") or "正在获取详情…")
        body.append(summary)

        def loaded(detail):
            item.update(detail)
            summary.set_text(detail.get("summary") or "暂无简介")

        if not self.offline:
            self.async_call(lambda: self.service.detail(item), loaded)

    def sources(self, item, body):
        group = Adw.PreferencesGroup(title="播放源", description="搜索已启用的规则")
        body.append(group)

        def show(results):
            group.set_description("请选择匹配的条目")
            for result in results:
                rule = result["plugin"]
                if result.get("error"):
                    row = action_row(title=rule["name"], subtitle=result["error"])
                    if "CaptchaRequiredException" in result["error"]:
                        verify = Gtk.Button(label="验证", valign=Gtk.Align.CENTER)

                        def begin(_, rule=rule):
                            def prepared(request):
                                from .webview import Verification

                                Verification(
                                    self,
                                    rule,
                                    request["url"],
                                    lambda: self.sources(item, body),
                                ).present(self)

                            self.async_call(
                                lambda: self.service.core(
                                    "search.prepare",
                                    rule,
                                    input=item.get("original_title") or item["title"],
                                ),
                                prepared,
                            )

                        verify.connect("clicked", begin)
                        row.add_suffix(verify)
                    group.add(row)
                    continue
                for match in result["items"]:
                    row = action_row(
                        title=match["name"], subtitle=rule["name"], activatable=True
                    )
                    row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                    row.connect(
                        "activated",
                        lambda _, r=rule, m=match: self.episodes(item, r, m["src"]),
                    )
                    group.add(row)
            if not results:
                group.set_description("请先在“我的 → 规则管理”安装并启用规则")

        self.async_call(lambda: self.service.sources(item), show)

    def episodes(self, item, rule, source):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16))
        self.push(item["title"] + " · 选集", Gtk.ScrolledWindow(child=body))

        def show(roads):
            for road in roads:
                group = Adw.PreferencesGroup(title=road["name"])
                for name, url in zip(road["identifier"], road["data"]):
                    row = action_row(title=name, activatable=True)
                    row.add_suffix(Gtk.Image(icon_name="media-playback-start-symbolic"))
                    row.connect(
                        "activated",
                        lambda _, n=name, u=url: self.resolve(item, n, u, rule),
                    )
                    group.add(row)
                body.append(group)

        self.async_call(
            lambda: self.service.chapters(rule, source),
            show,
            lambda e: body.append(Adw.StatusPage(title="获取剧集失败", description=e)),
        )

    def resolve(self, item, name, url, rule):
        from urllib.parse import urljoin

        url = urljoin(rule.get("baseURL", ""), url)
        headers = {"Referer": rule.get("referer") or rule.get("baseURL", "")}
        if rule.get("userAgent"):
            headers["User-Agent"] = rule["userAgent"]

        def play(media):
            self.open_player(item, name, media, headers=headers, page_url=url)

        if re.search(r"\.(m3u8|mp4|mkv|webm)(\?|$)", url):
            play(url)
        else:
            try:
                from .webview import Resolver

                Resolver(
                    self.store, url, play, user_agent=rule.get("userAgent", "")
                ).present(self)
            except Exception as error:
                self.message(str(error))

    def pili_play(self, item):
        self.async_call(
            lambda: self.service.play(item),
            lambda info: self.open_player(item, item["title"], **info),
        )

    def open_player(self, item, name, url, headers=None, audio=None, page_url=None):
        from .playback import Playback

        view = Playback(self, item, name, url, headers, audio, page_url)
        self.playback = view
        page = self.push(name, view)
        page.connect("hidden", lambda *_: view.pause_and_save())

    def account(self):
        from .account import show_account

        show_account(self)

    def personal(self):
        self.clear()
        group = Adw.PreferencesGroup(title="资料库")
        for title, subtitle, icon, callback in [
            ("Bangumi 账号", "登录与收藏同步", "avatar-default-symbolic", self.account),
            (
                "导入原版资料库",
                "读取 Hive 快照，保留原文件",
                "document-open-symbolic",
                self.import_legacy,
            ),
            (
                "历史记录",
                "继续观看",
                "document-open-recent-symbolic",
                lambda: self.personal_library("history", "历史记录"),
            ),
            (
                "规则管理",
                "安装、编辑和启用播放源",
                "application-x-addon-symbolic",
                self.rules,
            ),
            (
                "打开本地视频",
                "使用内嵌播放器",
                "folder-videos-symbolic",
                self.open_file,
            ),
            ("下载管理", "离线观看", "folder-download-symbolic", self.download_page),
            ("备份与恢复", "原生版资料库备份", "document-save-symbolic", self.backup),
            ("设置", "外观与播放", "preferences-system-symbolic", self.settings),
            ("操作日志", "查看最近的错误和网络状态", "document-properties-symbolic", self.logs),
            ("关于", "版本、许可证和项目链接", "help-about-symbolic", self.about),
        ]:
            if APP != "Kazumi" and title == "规则管理":
                continue
            row = action_row(title=title, subtitle=subtitle, activatable=True)
            row.add_prefix(Gtk.Image(icon_name=icon))
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            row.connect("activated", lambda _, f=callback: f())
            group.add(row)
        self.body.append(Adw.Clamp(maximum_size=760, child=group))

    def personal_library(self, kind, title):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12))
        self.push(title, Gtk.ScrolledWindow(child=body))
        for item in self.store.items(kind):
            row = action_row(
                title=item["title"], subtitle=item.get("episode", ""), activatable=True
            )
            row.connect("activated", lambda _, i=item: self.details(i))
            remove = button(
                "user-trash-symbolic",
                "删除记录",
                lambda i=item, r=row: (
                    self.store.remove(kind, i["id"]),
                    body.remove(r),
                ),
            )
            row.add_suffix(remove)
            body.append(row)

    def download_page(self):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12))
        self.push(
            "下载管理",
            Gtk.ScrolledWindow(child=Adw.Clamp(maximum_size=850, child=body)),
        )

        def refresh():
            self.clear(body)
            refresh_button = Gtk.Button(label="刷新状态", halign=Gtk.Align.START)
            refresh_button.connect("clicked", lambda *_: refresh())
            body.append(refresh_button)
            group = Adw.PreferencesGroup(title="下载任务")
            states = {
                "queued": "等待下载",
                "running": "下载中",
                "completed": "已完成",
                "failed": "失败",
                "cancelled": "已取消",
                "interrupted": "上次运行中断",
            }
            for item in self.store.items("downloads"):
                row = action_row(
                    title=item["title"],
                    subtitle=item["episode"]
                    + " · "
                    + states.get(item["state"], item["state"]),
                )
                if item["state"] == "completed":
                    row.set_activatable(True)
                    row.connect(
                        "activated",
                        lambda _, i=item: self.open_player(
                            i["source_item"], i["episode"], i["path"]
                        ),
                    )
                elif item["state"] in ("queued", "running"):
                    row.add_suffix(
                        button(
                            "process-stop-symbolic",
                            "取消下载",
                            lambda i=item: (self.downloads.cancel(i["id"]), refresh()),
                        )
                    )
                if item.get("error"):
                    row.set_tooltip_text(item["error"])
                group.add(row)
            body.append(group)

        refresh()

    def import_legacy(self):
        dialog = Gtk.FileDialog(title="选择原版 Kazumi 的 hive 文件夹（请先关闭原版）")

        def chosen(dialog, result):
            try:
                directory = dialog.select_folder_finish(result).get_path()
            except GLib.Error:
                return
            self.async_call(
                lambda: self.service.import_hive(directory),
                lambda result: self.message(
                    f"已导入 {result['mapped']} 条收藏/历史，保留 {result['preserved']} 条兼容记录"
                ),
                scoped=False,
            )

        dialog.select_folder(self, None, chosen)

    def open_file(self):
        dialog = Gtk.FileDialog(title="打开视频")

        def selected(dialog, result):
            try:
                file = dialog.open_finish(result)
                item = {
                    "id": file.get_uri(),
                    "title": file.get_basename(),
                    "url": file.get_uri(),
                }
                self.open_player(item, item["title"], file.get_path())
            except GLib.Error:
                pass

        dialog.open(self, None, selected)

    def about(self):
        dialog = Adw.AboutDialog(
            application_name=APP,
            application_icon="applications-multimedia-symbolic",
            version="GTK4 native preview",
            developer_name="lolo-desu",
            license_type=Gtk.License.MIT_X11,
            comments="使用 GTK4 与 libadwaita 的 GNOME 原生界面；保留上游数据和网络服务。",
            website=(
                "https://github.com/lolo-desu/Kazumi"
                if APP == "Kazumi"
                else "https://github.com/lolo-desu/PiliPlus"
            ),
            issue_url="https://github.com/lolo-desu/"
            + ("Kazumi" if APP == "Kazumi" else "PiliPlus")
            + "/issues",
        )
        dialog.present(self)

    def logs(self):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12))
        self.push(
            "操作日志",
            Gtk.ScrolledWindow(child=Adw.Clamp(maximum_size=900, child=body)),
        )
        header = Gtk.Box(spacing=8)
        copy = Gtk.Button(label="复制全部")
        clear = Gtk.Button(label="清空")
        header.append(copy)
        header.append(clear)
        body.append(header)
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.set_vexpand(True)
        view.add_css_class("card")
        body.append(view)

        def refresh():
            view.get_buffer().set_text("\n".join(self.messages) or "暂无日志")

        def copy_all(*_):
            self.get_clipboard().set_text("\n".join(self.messages))
            self.message("日志已复制")

        copy.connect("clicked", copy_all)
        clear.connect("clicked", lambda *_: (self.messages.clear(), refresh()))
        refresh()

    def shortcuts(self):
        dialog = Adw.PreferencesDialog(title="键盘快捷键")
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="全局")
        for title, shortcut in [
            ("搜索", "Ctrl + F"),
            ("返回上一页", "Esc"),
            ("全屏播放", "F"),
            ("播放 / 暂停", "Space"),
            ("前进 / 后退 5 秒", "← / →"),
            ("调节音量", "↑ / ↓"),
        ]:
            group.add(action_row(title=title, subtitle=shortcut))
        page.add(group)
        dialog.add(page)
        dialog.present(self)

    def apply_theme(self):
        schemes = {
            "system": Adw.ColorScheme.DEFAULT,
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
        }
        Adw.StyleManager.get_default().set_color_scheme(
            schemes.get(self.store.get("theme"), Adw.ColorScheme.DEFAULT)
        )

    def settings(self):
        dialog = Adw.PreferencesDialog(title="设置")
        page = Adw.PreferencesPage(
            title="常规", icon_name="preferences-system-symbolic"
        )
        group = Adw.PreferencesGroup(title="外观")
        theme = Adw.ComboRow(
            title="配色", model=Gtk.StringList.new(["跟随系统", "浅色", "深色"])
        )
        keys = ["system", "light", "dark"]
        theme.set_selected(keys.index(self.store.get("theme", "system")))
        theme.connect(
            "notify::selected",
            lambda *_: (
                self.store.set("theme", keys[theme.get_selected()]),
                self.apply_theme(),
            ),
        )
        group.add(theme)
        page.add(group)
        group = Adw.PreferencesGroup(title="播放")
        remember = Adw.SwitchRow(
            title="记住播放进度", active=self.store.get("remember", True)
        )
        remember.connect(
            "notify::active",
            lambda *_: self.store.set("remember", remember.get_active()),
        )
        group.add(remember)
        speed = Adw.SpinRow.new_with_range(0.25, 4, 0.25)
        speed.set_title("默认播放速度")
        speed.set_value(self.store.get("speed", 1.0))
        speed.connect(
            "notify::value", lambda *_: self.store.set("speed", speed.get_value())
        )
        group.add(speed)
        page.add(group)
        group = Adw.PreferencesGroup(title="帮助")
        shortcut_row = action_row(title="键盘快捷键", subtitle="查看播放器和导航快捷键", activatable=True)
        shortcut_row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        shortcut_row.connect("activated", lambda *_: self.shortcuts())
        group.add(shortcut_row)
        page.add(group)
        group = Adw.PreferencesGroup(title="网络")
        proxy = Adw.EntryRow(title="HTTP 代理（可选）")
        proxy.set_text(self.store.get("proxy", ""))
        proxy.connect("changed", lambda row: (self.store.set("proxy", row.get_text()), self.http.set_proxy(row.get_text())))
        group.add(proxy)
        page.add(group)
        dialog.add(page)
        dialog.present(self)

    def rules(self):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16))
        self.push(
            "规则管理",
            Gtk.ScrolledWindow(child=Adw.Clamp(maximum_size=850, child=body)),
        )
        actions = Gtk.Box(spacing=8)
        for name, callback in [
            ("规则商店", self.rule_shop),
            ("导入 JSON", lambda: self.edit_rule(None)),
        ]:
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda _, f=callback: f())
            actions.append(b)
        body.append(actions)
        group = Adw.PreferencesGroup(title="已安装")
        disabled = self.store.get("disabled_rules", [])
        for rule in self.service.plugins():
            row = action_row(title=rule["name"], subtitle=rule.get("baseURL", ""))
            toggle = Gtk.Switch(
                active=rule["name"] not in disabled, valign=Gtk.Align.CENTER
            )

            def changed(switch, _, name=rule["name"]):
                disabled = set(self.store.get("disabled_rules", []))
                disabled.discard(name) if switch.get_active() else disabled.add(name)
                self.store.set("disabled_rules", sorted(disabled))

            toggle.connect("notify::active", changed)
            row.add_suffix(toggle)
            row.add_suffix(
                button(
                    "document-edit-symbolic",
                    "编辑规则",
                    lambda r=rule: self.edit_rule(r),
                )
            )
            row.add_suffix(
                button(
                    "user-trash-symbolic",
                    "删除规则",
                    lambda r=rule, w=row: (
                        self.store.set(
                            "plugins",
                            [
                                p
                                for p in self.service.plugins()
                                if p["name"] != r["name"]
                            ],
                        ),
                        group.remove(w),
                    ),
                )
            )
            group.add(row)
        body.append(group)

    def edit_rule(self, rule):
        dialog = Adw.Dialog(
            title="编辑规则" if rule else "导入规则",
            content_width=760,
            content_height=620,
        )
        toolbar = Adw.ToolbarView()
        bar = Adw.HeaderBar()
        toolbar.add_top_bar(bar)
        editor = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        editor.get_buffer().set_text(
            json.dumps(rule or {}, ensure_ascii=False, indent=2)
        )
        toolbar.set_content(Gtk.ScrolledWindow(child=margins(editor)))
        save = Gtk.Button(label="保存")
        save.add_css_class("suggested-action")

        def submit(*_):
            buf = editor.get_buffer()
            try:
                value = json.loads(
                    buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
                )
            except ValueError as error:
                self.message(str(error))
                return
            self.async_call(
                lambda: self.service.save_plugin(value),
                lambda _: (dialog.close(), self.message("规则已保存")),
                scoped=False,
            )

        save.connect("clicked", submit)
        bar.pack_end(save)
        dialog.set_child(toolbar)
        dialog.present(self)

    def rule_shop(self):
        body = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12))
        self.push(
            "规则商店",
            Gtk.ScrolledWindow(child=Adw.Clamp(maximum_size=850, child=body)),
        )

        def show(items):
            group = Adw.PreferencesGroup(title="KazumiRules")
            for item in items:
                row = action_row(
                    title=item["name"],
                    subtitle=f"{item.get('version', '')} · {item.get('author', '')}",
                )
                install = Gtk.Button(label="安装 / 更新", valign=Gtk.Align.CENTER)

                def clicked(b, name=item["name"]):
                    b.set_sensitive(False)
                    self.async_call(
                        lambda: self.service.install_rule(name),
                        lambda _: (
                            b.set_label("已安装"),
                            self.message("已安装 " + name),
                        ),
                        lambda e: (b.set_sensitive(True), self.message(e)),
                        scoped=False,
                    )

                install.connect("clicked", clicked)
                row.add_suffix(install)
                group.add(row)
            body.append(group)

        self.async_call(self.service.catalog, show, lambda e: body.append(label(e)))

    def backup(self):
        dialog = Adw.AlertDialog(
            heading="备份与恢复", body="导出或合并原生版资料库；不包含登录凭据。"
        )
        dialog.add_response("cancel", "取消")
        dialog.add_response("export", "导出")
        dialog.add_response("import", "导入")

        def chosen(dialog, response):
            if response == "cancel":
                return
            file = Gtk.FileDialog(title="资料库备份")

            def complete(file, result):
                try:
                    if response == "export":
                        path = file.save_finish(result).get_path()
                        Path(path).write_text(
                            json.dumps(
                                self.store.export_data(), ensure_ascii=False, indent=2
                            )
                        )
                    else:
                        path = file.open_finish(result).get_path()
                        self.store.import_data(json.loads(Path(path).read_text()))
                    self.message("完成")
                except GLib.Error:
                    pass
                except Exception as e:
                    self.message(str(e))

            if response == "export":
                file.set_initial_name(APP + "-native-backup.json")
                file.save(self, None, complete)
            else:
                file.open(self, None, complete)

        dialog.connect("response", chosen)
        dialog.present(self)


class Application(Adw.Application):
    def __init__(self, store=None, offline=False):
        super().__init__(
            application_id="io.github.lolo_desu." + APP + ".Native",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.store = store or Store(APP)
        self.offline = offline

    def do_activate(self):
        self.window = Window(self, self.store, self.offline)
        self.window.present()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    return Application(Store(APP, args.profile), args.offline).run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
