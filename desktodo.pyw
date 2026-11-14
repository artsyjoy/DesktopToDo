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
import os
import sys
import tempfile
import threading
import webbrowser

import core

SMOKE = "--smoketest" in sys.argv
DEFAULT_W, DEFAULT_H = 420, 780


class Api:
    """Everything the interface (ui/app.js) can ask Python to do."""

    def __init__(self):
        self.data = core.load_data()
        core.roll_over(self.data)
        core.upgrade_notes(self.data)
        core.save_data(self.data)
        self.window = None
        self.css_width = None
        self._lock = threading.Lock()

    # ---- data ------------------------------------------------------------------------
    def get_state(self):
        return {"data": self.data, "smoke": SMOKE, "platform": sys.platform}

    def save(self, data):
        with self._lock:
            self.data = data
            core.save_data(self.data)
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
        self.css_width = css_width

    def resize(self, css_w, css_h):
        """Resize from the corner grip. JS sends CSS pixels; convert to the window's units."""
        w = self.window
        if not w:
            return
        ratio = (w.width / self.css_width) if self.css_width else 1.0
        w.resize(max(360, int(css_w * ratio)), max(440, int(css_h * ratio)))

    def set_on_top(self, on):
        if self.window:
            self.window.on_top = bool(on)

    def minimize(self):
        if self.window:
            self.window.minimize()

    def close(self):
        if self.window:
            self.remember_geometry()
            self.window.destroy()

    def remember_geometry(self):
        w = self.window
        try:
            self.data.setdefault("settings", {})["window"] = {"x": w.x, "y": w.y, "w": w.width, "h": w.height}
            core.save_data(self.data)
        except Exception:
            pass

    # ---- backups ---------------------------------------------------------------------
    def export_backup(self):
        import webview
        name = f"DeskTodo backup {core.date.today().isoformat()}.json"
        path = self.window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name,
                                              directory=os.path.join(os.path.expanduser("~"), "Documents"))
        if not path:
            return {"ok": False, "cancelled": True}
        path = path if isinstance(path, str) else path[0]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1, ensure_ascii=False)
            return {"ok": True, "path": path}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def import_backup(self):
        import webview
        paths = self.window.create_file_dialog(webview.OPEN_DIALOG, file_types=("DeskTodo backup (*.json)",),
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

    # ---- CI smoke test ---------------------------------------------------------------
    def smoke(self, info):
        out = os.path.join(tempfile.gettempdir(), "desktodo_smoke.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(info, f)
        threading.Timer(1.0, lambda: self.window and self.window.destroy()).start()


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


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if core.selftest() else 1)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    import webview

    api = Api()
    settings = api.data.setdefault("settings", {})
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
    api.window = window
    window.events.shown += lambda: round_corners(window)
    window.events.closing += api.remember_geometry
    webview.start(private_mode=False, storage_path=core.data_dir())


if __name__ == "__main__":
    main()
