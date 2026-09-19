import re
import gi

gi.require_version("WebKit", "6.0")
from gi.repository import WebKit, Adw, Gtk

_sessions = {}


def session_for(store):
    key = str(store.path.resolve())
    if key not in _sessions:
        _sessions[key] = WebKit.NetworkSession.new(
            str(store.path / "webkit"), str(store.path / "webkit-cache")
        )
    return _sessions[key]


class Verification(Adw.Dialog):
    """Share verified site cookies and its user agent with the upstream rule core."""

    def __init__(self, window, rule, url, done):
        super().__init__(
            title="源站验证 · " + rule["name"], content_width=820, content_height=600
        )
        self.window, self.rule, self.url, self.done = window, rule, url, done
        self.session = session_for(window.store)
        self.web = WebKit.WebView(network_session=self.session)
        if rule.get("userAgent"):
            self.web.get_settings().set_user_agent(rule["userAgent"])
        toolbar = Adw.ToolbarView(content=self.web)
        bar = Adw.HeaderBar()
        toolbar.add_top_bar(bar)
        finish = Gtk.Button(label="完成验证，重新搜索")
        finish.add_css_class("suggested-action")
        finish.connect("clicked", self.finish)
        bar.pack_end(finish)
        self.set_child(toolbar)
        self.web.load_uri(url)
        self.connect("closed", lambda *_: self.web.stop_loading())

    def finish(self, *_):
        manager = self.session.get_cookie_manager()

        def received(manager, result):
            try:
                import http.cookiejar

                cookies = manager.get_cookies_finish(result)
                with self.window.http.lock:
                    for cookie in cookies:
                        expires = cookie.get_expires()
                        domain = cookie.get_domain()
                        self.window.http.cookies.set_cookie(
                            http.cookiejar.Cookie(
                                0,
                                cookie.get_name(),
                                cookie.get_value(),
                                None,
                                False,
                                domain,
                                True,
                                domain.startswith("."),
                                cookie.get_path(),
                                True,
                                cookie.get_secure(),
                                expires.to_unix() if expires else None,
                                expires is None,
                                None,
                                None,
                                {"HttpOnly": cookie.get_http_only()},
                            )
                        )
                    self.window.http.cookies.save(ignore_discard=True)
                    (self.window.store.path / "cookies.txt").chmod(0o600)
                self.window.store.set(
                    "verified_ua:" + self.rule["name"],
                    self.web.get_settings().get_user_agent(),
                )
                self.close()
                self.done()
            except Exception as error:
                self.window.message(str(error))

        manager.get_cookies(self.url, None, received)


class Resolver(Adw.Dialog):
    """Native WebKit surface for source-page media detection and interactive challenges."""

    def __init__(self, store, url, done, *, user_agent=""):
        super().__init__(title="解析播放地址", content_width=820, content_height=580)
        self.done, self.found = done, False
        session = session_for(store)
        manager = WebKit.UserContentManager()
        manager.register_script_message_handler("media", None)
        manager.connect("script-message-received::media", self.message)
        manager.add_script(
            WebKit.UserScript.new(
                """
          setInterval(() => {
            for (const video of document.querySelectorAll('video')) {
              const src = video.currentSrc || video.src;
              if (/^https?:/.test(src)) window.webkit.messageHandlers.media.postMessage(src);
            }
          }, 800);
        """,
                WebKit.UserContentInjectedFrames.ALL_FRAMES,
                WebKit.UserScriptInjectionTime.END,
                None,
                None,
            )
        )
        self.web = WebKit.WebView(network_session=session, user_content_manager=manager)
        if user_agent:
            self.web.get_settings().set_user_agent(user_agent)
        self.web.connect("resource-load-started", self.resource)
        bar = Adw.HeaderBar()
        toolbar = Adw.ToolbarView(content=self.web)
        toolbar.add_top_bar(bar)
        self.set_child(toolbar)
        self.connect("closed", lambda *_: self.web.stop_loading())
        self.web.load_uri(url)

    def message(self, manager, value):
        self.accept(value.to_string())

    def resource(self, web, resource, request):
        resource.connect("finished", self.resource_finished)

    def resource_finished(self, resource):
        response = resource.get_response()
        if response and (response.get_mime_type() or "").lower() in (
            "application/vnd.apple.mpegurl",
            "application/x-mpegurl",
            "video/mp4",
            "video/webm",
        ):
            self.accept(response.get_uri())

    def accept(self, uri):
        if not self.found and re.match(r"^https?://", uri):
            self.found = True
            self.done(uri)
            self.close()
