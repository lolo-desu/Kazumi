"""libmpv Render API on Gtk.GLArea; commands never block the GL thread."""

import ctypes as C
import ctypes.util
from concurrent.futures import ThreadPoolExecutor
import os
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

Proc = C.CFUNCTYPE(C.c_void_p, C.c_void_p, C.c_char_p)
Update = C.CFUNCTYPE(None, C.c_void_p)


class Param(C.Structure):
    _fields_ = [("type", C.c_int), ("data", C.c_void_p)]


class Init(C.Structure):
    _fields_ = [("get_proc_address", Proc), ("ctx", C.c_void_p)]


class Fbo(C.Structure):
    _fields_ = [("fbo", C.c_int), ("w", C.c_int), ("h", C.c_int), ("format", C.c_int)]


class Node(C.Structure):
    pass


class NodeList(C.Structure):
    pass


class NodeValue(C.Union):
    _fields_ = [
        ("string", C.c_char_p),
        ("flag", C.c_int),
        ("integer", C.c_int64),
        ("double", C.c_double),
        ("list", C.POINTER(NodeList)),
        ("bytes", C.c_void_p),
    ]


Node._fields_ = [("value", NodeValue), ("format", C.c_int)]
NodeList._fields_ = [
    ("num", C.c_int),
    ("values", C.POINTER(Node)),
    ("keys", C.POINTER(C.c_char_p)),
]


def library(name, env):
    return C.CDLL(
        os.environ.get(env) or ctypes.util.find_library(name) or f"lib{name}.so"
    )


class Video(Gtk.GLArea):
    def __init__(self, report, volume=80, audio_output=None):
        super().__init__(hexpand=True, vexpand=True)
        self.set_size_request(240, 160)
        self.set_allowed_apis(Gdk.GLAPI.GL | Gdk.GLAPI.GLES)
        self.set_auto_render(False)
        self.report = report
        self.initial_volume = volume
        self.audio_output = audio_output
        self.handle = None
        self.render_context = C.c_void_p()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mpv")
        self.closed = False
        self.ready = False
        self.pending = None
        self.connect("realize", self.realize_video)
        self.connect("render", self.render_video)
        self.connect("unrealize", self.unrealize_video)

    def bind(self, name, result, *args):
        f = getattr(self.mpv, name)
        f.restype, f.argtypes = result, args
        return f

    def realize_video(self, *_):
        self.make_current()
        if self.get_error():
            self.report(str(self.get_error()))
            return
        try:
            self.mpv = library("mpv", "NATIVE_MPV_LIBRARY")
            self.egl = library("EGL", "NATIVE_EGL_LIBRARY")
            self.egl.eglGetProcAddress.argtypes = [C.c_char_p]
            self.egl.eglGetProcAddress.restype = C.c_void_p
            self.bind("mpv_create", C.c_void_p)
            self.bind(
                "mpv_set_option_string", C.c_int, C.c_void_p, C.c_char_p, C.c_char_p
            )
            self.bind("mpv_initialize", C.c_int, C.c_void_p)
            self.bind("mpv_command", C.c_int, C.c_void_p, C.POINTER(C.c_char_p))
            self.bind("mpv_get_property_string", C.c_void_p, C.c_void_p, C.c_char_p)
            self.bind("mpv_free", None, C.c_void_p)
            self.bind(
                "mpv_set_property", C.c_int, C.c_void_p, C.c_char_p, C.c_int, C.c_void_p
            )
            self.bind("mpv_terminate_destroy", None, C.c_void_p)
            self.bind(
                "mpv_render_context_create",
                C.c_int,
                C.POINTER(C.c_void_p),
                C.c_void_p,
                C.POINTER(Param),
            )
            self.bind(
                "mpv_render_context_render", C.c_int, C.c_void_p, C.POINTER(Param)
            )
            self.bind(
                "mpv_render_context_set_update_callback",
                None,
                C.c_void_p,
                Update,
                C.c_void_p,
            )
            self.bind("mpv_render_context_free", None, C.c_void_p)
            self.handle = self.mpv.mpv_create()
            for k, v in [
                ("vo", "libmpv"),
                ("hwdec", "auto-safe"),
                ("terminal", "no"),
                ("config", "no"),
                ("idle", "yes"),
                ("keep-open", "yes"),
                ("volume", str(self.initial_volume)),
            ] + ([("ao", self.audio_output)] if self.audio_output else []):
                if (
                    self.mpv.mpv_set_option_string(self.handle, k.encode(), v.encode())
                    < 0
                ):
                    raise RuntimeError("mpv option: " + k)
            if self.mpv.mpv_initialize(self.handle) < 0:
                raise RuntimeError("libmpv 初始化失败")
            self.proc = Proc(lambda _, name: self.egl.eglGetProcAddress(name))
            self.init = Init(self.proc, None)
            api = C.create_string_buffer(b"opengl")
            params = (Param * 3)(
                Param(1, C.cast(api, C.c_void_p)),
                Param(2, C.cast(C.pointer(self.init), C.c_void_p)),
                Param(),
            )
            if (
                self.mpv.mpv_render_context_create(
                    C.byref(self.render_context), self.handle, params
                )
                < 0
            ):
                raise RuntimeError("libmpv OpenGL 上下文创建失败")
            self.get_int = C.CFUNCTYPE(None, C.c_uint, C.POINTER(C.c_int))(
                self.egl.eglGetProcAddress(b"glGetIntegerv")
            )
            self.update = Update(lambda _: GLib.idle_add(self.invalidate))
            self.mpv.mpv_render_context_set_update_callback(
                self.render_context, self.update, None
            )
            self.ready = True
            if self.pending:
                self.load(*self.pending)
        except Exception as error:
            self.report(str(error))

    def invalidate(self):
        if not self.closed:
            self.queue_render()
        return False

    def render_video(self, *_):
        if not self.render_context.value or self.closed:
            return True
        framebuffer = C.c_int()
        self.get_int(0x8CA6, C.byref(framebuffer))
        scale = self.get_scale_factor()
        fbo = Fbo(
            framebuffer.value, self.get_width() * scale, self.get_height() * scale, 0
        )
        flip = C.c_int(1)
        params = (Param * 3)(
            Param(3, C.cast(C.pointer(fbo), C.c_void_p)),
            Param(4, C.cast(C.pointer(flip), C.c_void_p)),
            Param(),
        )
        self.mpv.mpv_render_context_render(self.render_context, params)
        return True

    def command(self, *args):
        if self.ready and not self.closed:

            def run():
                values = [str(x).encode() for x in args] + [None]
                result = self.mpv.mpv_command(
                    self.handle, (C.c_char_p * len(values))(*values)
                )
                if result < 0:
                    GLib.idle_add(self.report, f"播放器命令失败：{args[0]} ({result})")

            self.worker.submit(run)

    def load(self, url, headers=None, audio=None, start=0, paused=False):
        if not self.ready:
            self.pending = (url, headers, audio, start, paused)
            return
        self.set_list(
            "http-header-fields", [f"{k}: {v}" for k, v in (headers or {}).items()]
        )
        self.set_list("audio-files", [audio] if audio else [])
        # mpv applies the pause property to the currently loaded file.  Queue
        # loadfile before pause so a paused quality switch remains paused after
        # the new stream replaces the old one.
        self.command("set", "start", str(start))
        self.command("loadfile", url, "replace")
        self.command("set", "pause", "yes" if paused else "no")

    def set_list(self, name, values):
        if not self.ready or self.closed:
            return

        def set_property():
            encoded = [value.encode() for value in values]
            entries = (Node * len(encoded))(
                *(Node(NodeValue(string=value), 1) for value in encoded)
            )
            array = NodeList(len(encoded), entries, None)
            node = Node(NodeValue(list=C.pointer(array)), 7)
            # Pass native arrays: parsing a colon-separated path list splits URLs.
            result = self.mpv.mpv_set_property(
                self.handle, name.encode(), 6, C.byref(node)
            )
            if result < 0:
                GLib.idle_add(self.report, f"播放器设置失败：{name} ({result})")

        self.worker.submit(set_property)

    def status(self, callback):
        if not self.ready or self.closed:
            return

        def read():
            result = {}
            for key in (
                "time-pos",
                "duration",
                "pause",
                "eof-reached",
                "idle-active",
                "volume",
                "speed",
                "video-params/w",
                "video-params/h",
                "audio-codec-name",
                "audio-params/channel-count",
            ):
                ptr = self.mpv.mpv_get_property_string(self.handle, key.encode())
                if ptr:
                    result[key] = C.string_at(ptr).decode()
                    self.mpv.mpv_free(ptr)
            GLib.idle_add(callback, result)

        self.worker.submit(read)

    def unrealize_video(self, *_):
        self.closed = True
        self.make_current()
        if self.render_context.value:
            self.mpv.mpv_render_context_free(self.render_context)
            self.render_context = C.c_void_p()
        if self.handle:
            self.worker.submit(self.mpv.mpv_terminate_destroy, self.handle)
        self.worker.shutdown(wait=False)
