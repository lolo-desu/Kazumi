"""Verify WebKit media detection and cookie transfer using only a local fixture."""

import http.server
from pathlib import Path
import sys
import tempfile
import threading
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nativeapp.app import Application
from nativeapp.storage import Store
from nativeapp.webview import Resolver, Verification
from gi.repository import GLib, WebKit


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/protected":
            good = "clearance=yes" in self.headers.get("Cookie", "")
            self.send_response(200 if good else 403)
            self.end_headers()
            self.wfile.write(b"ok" if good else b"no")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "clearance=yes; Path=/; HttpOnly")
        self.end_headers()
        self.wfile.write(
            b'<html><body><video controls src="/fixture.mp4"></video></body></html>'
        )

    def log_message(self, *_):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/"
app = Application(Store("fixture", tempfile.mkdtemp(prefix="webkit-test-")), True)
errors = []


def start():
    if not hasattr(app, "window") or app.window.get_width() < 300:
        return True

    def media(uri):
        try:
            assert uri == url + "fixture.mp4"
        except Exception:
            errors.append(traceback.format_exc())
            app.quit()
            return
        GLib.idle_add(verify)

    Resolver(app.window.store, url, media).present(app.window)
    return False


def verify():
    def done():
        def result(value):
            try:
                assert value == "ok"
                print("WebKit media detection and verified-cookie transfer passed")
            except Exception:
                errors.append(traceback.format_exc())
            app.window.close()
            app.quit()

        app.window.async_call(
            lambda: app.window.http.request(url + "protected"),
            result,
            lambda e: (errors.append(e), app.quit()),
            scoped=False,
        )

    dialog = Verification(app.window, {"name": "fixture"}, url, done)
    dialog.web.connect(
        "load-changed",
        lambda web, event: (
            dialog.finish() if event == WebKit.LoadEvent.FINISHED else None
        ),
    )
    dialog.present(app.window)
    return False


GLib.timeout_add(700, start)
GLib.timeout_add_seconds(
    30, lambda: (errors.append("WebKit timeout"), app.quit(), False)[-1]
)
app.run(["webkit-smoke"])
server.shutdown()
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
