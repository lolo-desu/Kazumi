import sys
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib
from nativeapp.app import Application
from nativeapp.storage import Store
from nativeapp.services import APP

app = Application(Store(APP, tempfile.mkdtemp()), True)
errors = []
result = {}
server = None
audio_url = None
if len(sys.argv) > 2:

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    audio_path = Path(sys.argv[2]).resolve()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(QuietHandler, directory=str(audio_path.parent)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    audio_url = f"http://127.0.0.1:{server.server_port}/{audio_path.name}"
app.store.set("volume", 0)


def start():
    if not hasattr(app, "window") or app.window.get_width() <= 300:
        return True
    original = app.window.message
    app.window.message = lambda text: (
        print("PLAYER:", text, flush=True),
        original(text),
    )[-1]
    app.window.open_player(
        {"id": "fixture", "title": "播放器集成测试", "url": sys.argv[1]},
        "播放器集成测试",
        sys.argv[1],
        audio=audio_url,
    )
    from nativeapp.danmaku import Comment

    app.window.playback.danmaku.add([Comment(0, "GTK 弹幕"), Comment(1, "顶部弹幕", 5)])
    GLib.timeout_add(4500, check)
    return False


def check():
    video = app.window.playback.video
    print(
        "VIDEO",
        video.ready,
        video.closed,
        video.get_realized(),
        video.get_error(),
        flush=True,
    )

    def got(status):
        try:
            assert float(status.get("time-pos", 0)) > 1, status
            if audio_url:
                assert int(status.get("audio-params/channel-count", 0)) > 0, status
            assert len(app.window.playback.danmaku.plan) == 2
            assert int(status.get("video-params/w", 0)) == 640, status
            video.command("set", "pause", "yes")
            video.command("seek", 2, "absolute")
            GLib.timeout_add(700, verify_seek)
        except Exception:
            errors.append(traceback.format_exc())
            app.quit()
        return False

    video.status(got)
    return False


def verify_seek():
    def got(status):
        try:
            assert status.get("pause") == "yes", status
            assert abs(float(status["time-pos"]) - 2) < 0.5, status
            print("GTK libmpv: video frames, progress, pause and seek passed")
        except Exception:
            errors.append(traceback.format_exc())
        app.window.close()
        app.quit()
        return False

    app.window.playback.video.status(got)
    return False


GLib.timeout_add(500, start)
GLib.timeout_add(
    30000, lambda: (errors.append("player timeout"), app.quit(), False)[-1]
)
app.run(["native-player-test"])
if server:
    server.shutdown()
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
