"""
DeskTodo - to-do list, notes and an "at a glance" dashboard for your Windows desktop.

The window is drawn with Microsoft Edge WebView2 (via pywebview), so scrolling, transitions and the
light/dark crossfade are GPU-accelerated and smooth. All data handling lives in core.py:
tasks, notes and settings are saved to %APPDATA%\\DeskTodo\\data.json.

    python desktodo.pyw              run the app
    python desktodo.pyw --selftest   check weather, city search and calendar parsing
    DeskTodo.exe --smoketest         open the window, confirm the UI loads, then close (used in CI)
"""

import json
import logging
import os
import sys
import tempfile
import threading
import traceback
import webbrowser

import core

SMOKE = "--smoketest" in sys.argv
LOG_FILE = os.path.join(tempfile.gettempdir(), "desktodo.log")
if SMOKE or os.environ.get("DESKTODO_LOG"):
    logging.basicConfig(filename=LOG_FILE, filemode="w", level=logging.DEBUG,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("desktodo")
WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
DEFAULT_W, DEFAULT_H = 420, 780


class Api:
    """Everything the interface (ui/app.js) can ask Python to do."""

    def __init__(self):
        self._data = core.load_data()
        core.roll_over(self._data)
        core.upgrade_notes(self._data)
        core.save_data(self._data)
        self._window = None
        self._css_width = None
        self._lock = threading.Lock()

    # ---- data ------------------------------------------------------------------------
    def get_state(self):
        return {"data": self._data, "smoke": SMOKE, "platform": sys.platform}

    def save(self, data):
        with self._lock:
            self._data = data
            core.save_data(self._data)
        return True

    # ---- online ----------------------------------------------------------------------
    def weather(self, lat, lon):
        try:
            return {"ok": True, "weather": core.fetch_weather(lat, lon)}
        except Exception as exc:  # offline, service down, ...
            return {"ok": False, "error": str(exc)}

    def geocode(self, query):
        try:
            return {"ok": True, "places": core.geocode(query)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def events(self, url):
        try:
            return {"ok": True, "events": core.fetch_events(url)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    # ---- window ----------------------------------------------------------------------
    def report_size(self, css_width):
        self._css_width = css_width

    def resize(self, css_w, css_h):
        """Resize from the corner grip. JS sends CSS pixels; convert to the window's units."""
        w = self._window
        if not w:
            return
        ratio = (w.width / self._css_width) if self._css_width else 1.0
        w.resize(max(360, int(css_w * ratio)), max(440, int(css_h * ratio)))

    def set_on_top(self, on):
        if self._window:
            self._window.on_top = bool(on)

    def minimize(self):
        if self._window:
            self._window.minimize()

    def close(self):
        if self._window:
            self.remember_geometry()
            self._window.destroy()

    def remember_geometry(self):
        w = self._window
        try:
            self._data.setdefault("settings", {})["window"] = {"x": w.x, "y": w.y, "w": w.width, "h": w.height}
            core.save_data(self._data)
        except Exception:
            pass

    # ---- backups ---------------------------------------------------------------------
    def export_backup(self):
        import webview
        name = f"DeskTodo backup {core.date.today().isoformat()}.json"
        path = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name,
                                              directory=os.path.join(os.path.expanduser("~"), "Documents"))
        if not path:
            return {"ok": False, "cancelled": True}
        path = path if isinstance(path, str) else path[0]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=1, ensure_ascii=False)
            return {"ok": True, "path": path}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def import_backup(self):
        import webview
        paths = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=("DeskTodo backup (*.json)",),
                                               directory=os.path.join(os.path.expanduser("~"), "Documents"))
        if not paths:
            return {"ok": False, "cancelled": True}
        try:
            with open(paths[0], "r", encoding="utf-8") as f:
                new = json.load(f)
            if not isinstance(new, dict) or "days" not in new or "notes" not in new:
                raise ValueError("That file isn't a DeskTodo backup.")
            new.setdefault("settings", {})
            core.upgrade_notes(new)
            return {"ok": True, "data": new}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    # ---- diagnostics -----------------------------------------------------------------
    def log(self, message):
        log.warning("UI: %s", message)

    # ---- CI smoke test ---------------------------------------------------------------
    def smoke(self, info):
        out = os.path.join(tempfile.gettempdir(), "desktodo_smoke.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(info, f)
        threading.Timer(1.0, lambda: self._window and self._window.destroy()).start()


def round_corners(window):
    """Windows 11: ask the compositor for rounded, antialiased corners with a soft shadow."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(window.native.Handle.ToInt64())
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


def on_screen(geo):
    """Make sure a remembered position is still on a connected screen."""
    import webview
    try:
        for s in webview.screens:
            if s.x - 100 <= geo["x"] <= s.x + s.width - 120 and s.y - 20 <= geo["y"] <= s.y + s.height - 120:
                return True
    except Exception:
        return True
    return False


def explain_missing_webview2(exc):
    """Shown when Windows has no WebView2 runtime (rare on Windows 10/11)."""
    log.error("Could not start the WebView2 window: %s", exc)
    if SMOKE or sys.platform != "win32":
        return
    try:
        import ctypes
        msg = ("DeskTodo needs the Microsoft Edge WebView2 Runtime, which is missing on this PC.\n\n"
               "Click OK to open Microsoft's download page, install the \"Evergreen\" runtime, "
               "then start DeskTodo again.")
        if ctypes.windll.user32.MessageBoxW(None, msg, core.APP_NAME, 0x41) == 1:  # OK / Cancel
            webbrowser.open(WEBVIEW2_URL)
    except Exception:
        pass


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if core.selftest() else 1)
    try:
        run()
    except Exception as exc:
        log.error("Crashed: %s", traceback.format_exc())
        if SMOKE:
            with open(os.path.join(tempfile.gettempdir(), "desktodo_smoke.json"), "w", encoding="utf-8") as f:
                json.dump({"ok": False, "error": traceback.format_exc()}, f)
        explain_missing_webview2(exc)
        sys.exit(1)


def run():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    import webview

    api = Api()
    settings = api._data.setdefault("settings", {})
    geo = settings.get("window") or {}
    dark = settings.get("theme", "dark") == "dark"
    kwargs = {}
    if geo.get("w") and geo.get("h"):
        kwargs.update(width=geo["w"], height=geo["h"])
        if "x" in geo and on_screen(geo):
            kwargs.update(x=geo["x"], y=geo["y"])
    else:
        kwargs.update(width=DEFAULT_W, height=DEFAULT_H)

    window = webview.create_window(
        core.APP_NAME,
        url=os.path.join(core.resource_dir(), "ui", "index.html"),
        js_api=api,
        frameless=True,
        easy_drag=False,
        min_size=(360, 440),
        on_top=bool(settings.get("on_top")),
        background_color="#0f0f0f" if dark else "#e8e8e6",
        text_select=True,
        **kwargs,
    )
    api._window = window
    window.events.shown += lambda: round_corners(window)
    window.events.closing += api.remember_geometry
    window.events.loaded += lambda: log.info("Page loaded with renderer: %s", getattr(webview, "renderer", "?"))
    if SMOKE:  # never hang a CI run: give up after 60 s and report why
        def give_up():
            out = os.path.join(tempfile.gettempdir(), "desktodo_smoke.json")
            if not os.path.exists(out):
                with open(out, "w", encoding="utf-8") as f:
                    json.dump({"ok": False, "error": "timeout", "renderer": getattr(webview, "renderer", "?")}, f)
            window.destroy()
        t = threading.Timer(60, give_up)
        t.daemon = True  # don't keep the app alive after its window closes
        t.start()
    # WebView2 only: the old Internet Explorer engine can't run this interface.
    gui = "edgechromium" if sys.platform == "win32" else None
    log.info("Starting window (gui=%s)", gui)
    webview.start(gui=gui, private_mode=False, storage_path=core.data_dir(), debug=SMOKE)


if __name__ == "__main__":
    main()
