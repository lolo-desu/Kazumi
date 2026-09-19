import re
import gi

gi.require_version("WebKit", "6.0")
from gi.repository import WebKit, Adw


class Resolver(Adw.Dialog):
    """Native WebKit surface for source-page media detection and interactive challenges."""

    def __init__(self, store, url, done, *, user_agent=""):
        super().__init__(title="解析播放地址", content_width=820, content_height=580)
        self.done, self.found = done, False
        session = WebKit.NetworkSession.new(
            str(store.path / "webkit"), str(store.path / "webkit-cache")
        )
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
