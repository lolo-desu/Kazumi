import sys
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


def start():
    original = app.window.message
    app.window.message = lambda text: (
        print("PLAYER:", text, flush=True),
        original(text),
    )[-1]
    app.window.open_player(
        {"id": "fixture", "title": "播放器集成测试", "url": sys.argv[1]},
        "播放器集成测试",
        sys.argv[1],
    )
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
    14000, lambda: (errors.append("player timeout"), app.quit(), False)[-1]
)
app.run(["native-player-test"])
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
