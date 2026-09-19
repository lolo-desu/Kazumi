"""Exercise actual GTK widgets with isolated storage and deterministic fixtures."""

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")
from gi.repository import Gtk, GLib
from nativeapp.app import Application
from nativeapp.storage import Store
from nativeapp.services import APP

store = Store(APP, tempfile.mkdtemp(prefix="native-smoke-"))
store.set("plugins", [])
app = Application(store, True)
errors = []


def capture():
    if not hasattr(app, "window") or app.window.get_width() <= 300:
        return True
    window = app.window
    Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
    try:
        width = int(os.environ.get("NATIVE_TEST_WIDTH", "1160"))
        window.set_default_size(width, 800)
        if os.environ.get("NATIVE_TEST_DARK"):
            store.set("theme", "dark")
            window.apply_theme()
        assert window.get_width() > 300
        window.navigate("my")
        window.settings()
        dialog = window.get_visible_dialog()
        assert dialog is not None
        dialog.close()
        window.navigate("collect") if "collect" in window.routes else window.library(
            "collect"
        )
        item = {
            "id": "test",
            "title": "原生界面测试",
            "subtitle": "GTK4 · libadwaita",
            "summary": "隔离测试数据",
            "url": "https://example.org",
        }
        store.put("collect", item)
        window.navigate("collect") if "collect" in window.routes else window.library(
            "collect"
        )
        window.details(item)
        assert window.navigation.get_visible_page().get_title() == item["title"]
        window.navigation.pop()
        window.navigate("my")
        if APP == "Kazumi":
            window.rules()
            window.navigation.pop()
        GLib.timeout_add(500, render)
    except Exception:
        errors.append(traceback.format_exc())
        app.quit()
    return False


def render():
    try:
        window = app.window
        paintable = Gtk.WidgetPaintable.new(window)
        snapshot = Gtk.Snapshot.new()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        texture = window.get_renderer().render_texture(node, None)
        target = Path(os.environ.get("NATIVE_TEST_OUTPUT", "native/test-output"))
        target.mkdir(parents=True, exist_ok=True)
        texture.save_to_png(
            str(
                target
                / (
                    APP
                    + "-gtk-"
                    + str(window.get_width())
                    + ("-dark" if os.environ.get("NATIVE_TEST_DARK") else "-light")
                    + ".png"
                )
            )
        )
        print(
            json.dumps(
                {
                    "application": APP,
                    "width": window.get_width(),
                    "height": window.get_height(),
                    "native_smoke": "passed",
                }
            )
        )
    except Exception:
        errors.append(traceback.format_exc())
    app.quit()
    return False


GLib.timeout_add(700, capture)
GLib.timeout_add_seconds(
    30, lambda: (errors.append("GTK startup timeout"), app.quit(), False)[-1]
)
app.run(["gtk-smoke"])
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
