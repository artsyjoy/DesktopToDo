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
# Every start writes a short log next to the data file (the CI smoke test logs to %TEMP%).
LOG_FILE = os.path.join(tempfile.gettempdir() if SMOKE else core.data_dir(), "desktodo.log")
try:
    logging.basicConfig(filename=LOG_FILE, filemode="w",
                        level=logging.DEBUG if SMOKE or os.environ.get("DESKTODO_LOG") else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
except OSError:
    pass
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
        self._hwnd = None          # native window handle, set once the window is shown
        self._resizing = False
        s = self._data.setdefault("settings", {})
        # where the widget lives; older versions only had "keep on top" (on_top)
        self._layer = s.get("layer") or ("top" if s.get("on_top") else "desktop")
        s["layer"] = self._layer

    # ---- data ------------------------------------------------------------------------
    def get_state(self):
        return {"data": self._data, "smoke": SMOKE, "platform": sys.platform, "version": core.APP_VERSION}

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

    def begin_resize(self):
        """Start a height-only resize from the bottom handle.

        Python follows the mouse with plain Win32 calls until the left button is released. The page sends
        just this one message, so nothing piles up between the page and the window (that froze 1.5.x)."""
        if sys.platform != "win32" or not self._hwnd or self._resizing:
            return
        self._resizing = True
        threading.Thread(target=self._resize_loop, daemon=True).start()

    def _resize_loop(self):
        import ctypes
        import time
        from ctypes import wintypes as wt
        u32 = ctypes.windll.user32

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]
        # exact signatures, so 64-bit window handles are passed intact
        u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        u32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
        u32.GetDpiForWindow.argtypes = [wt.HWND]
        u32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
        u32.MonitorFromWindow.restype = wt.HANDLE
        u32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
        u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
        u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u32.GetAsyncKeyState.restype = ctypes.c_short
        try:
            hwnd = self._hwnd
            rect, pt = wt.RECT(), wt.POINT()
            u32.GetWindowRect(hwnd, ctypes.byref(rect))
            u32.GetCursorPos(ctypes.byref(pt))
            width, start_h, start_y = rect.right - rect.left, rect.bottom - rect.top, pt.y
            scale = (u32.GetDpiForWindow(hwnd) or 96) / 96
            min_h = int(440 * scale)
            mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
            u32.GetMonitorInfoW(u32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
            # stop at the bottom of the screen, but never shrink just because the drag started
            max_h = max(min_h, start_h, mi.rcWork.bottom - rect.top)
            flags = 0x0002 | 0x0004 | 0x0010 | 0x4000                 # no move, no z-order, no activate, async
            last = start_h
            while u32.GetAsyncKeyState(0x01) & 0x8000:                # until the mouse button is released
                u32.GetCursorPos(ctypes.byref(pt))
                h = int(max(min_h, min(max_h, start_h + pt.y - start_y)))
                if h != last:
                    u32.SetWindowPos(hwnd, None, 0, 0, width, h, flags)
                    last = h
                time.sleep(1 / 120)
        except Exception:
            log.warning("Resize failed: %s", traceback.format_exc())
        finally:
            self._resizing = False

    def set_on_top(self, on):
        self.set_layer("top" if on else "desktop")

    def set_layer(self, layer):
        """Where the widget lives: "top" (above all apps), "desktop" (behind apps, like a desktop widget)
        or "normal" (an ordinary window)."""
        self._layer = layer if layer in ("top", "desktop", "normal") else "desktop"
        if self._window:
            self._window.on_top = self._layer == "top"
        log.info("Window layer: %s", self._layer)

    def _layer_loop(self):
        """Desktop mode: keep the widget behind other apps, and bring it back when the desktop is shown
        (for example with Win+D). Runs in the background, a few times a second, using plain Win32 calls."""
        import ctypes
        import time
        from ctypes import wintypes as wt
        u32 = ctypes.windll.user32
        u32.GetForegroundWindow.restype = wt.HWND
        u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        u32.IsWindow.argtypes = u32.IsIconic.argtypes = u32.IsWindowVisible.argtypes = [wt.HWND]
        u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
        HWND_TOP, HWND_BOTTOM = 0, 1
        KEEP = 0x0001 | 0x0002 | 0x0010            # no size, no move, no activate
        name = ctypes.create_unicode_buffer(64)
        state = None
        while self._hwnd and u32.IsWindow(self._hwnd):
            try:
                if self._layer == "desktop" and not self._resizing:
                    fg = u32.GetForegroundWindow()
                    if fg and fg != self._hwnd:
                        u32.GetClassNameW(fg, name, 64)
                        if name.value in ("WorkerW", "Progman"):          # the desktop is showing
                            if u32.IsIconic(self._hwnd) or not u32.IsWindowVisible(self._hwnd):
                                u32.ShowWindow(self._hwnd, 4)               # SW_SHOWNOACTIVATE
                                state = None
                            if state != "desktop":
                                u32.SetWindowPos(self._hwnd, HWND_TOP, 0, 0, 0, 0, KEEP)
                                state = "desktop"
                        elif state != "behind":                         # an app is in front: tuck behind
                            u32.SetWindowPos(self._hwnd, HWND_BOTTOM, 0, 0, 0, 0, KEEP)
                            state = "behind"
                    else:
                        state = None                                    # you're using the widget
                else:
                    state = None
            except Exception:
                log.warning("Layer loop: %s", traceback.format_exc())
            time.sleep(0.25)

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
        """CI: the page loaded. On Windows also drag-resize for real, then check the window still responds."""
        def run():
            if sys.platform == "win32" and self._hwnd:
                info.update(self._smoke_resize())
                info["ok"] = bool(info.get("ok") and info.get("resize_ok") and info.get("responsive"))
            out = os.path.join(tempfile.gettempdir(), "desktodo_smoke.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(info, f)
            time.sleep(1.0)
            if self._window:
                self._window.destroy()
        import time
        threading.Thread(target=run, daemon=True).start()

    def _smoke_resize(self):
        import ctypes
        import time
        from ctypes import wintypes as wt
        u32 = ctypes.windll.user32
        u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
        rect = wt.RECT()
        u32.GetWindowRect(self._hwnd, ctypes.byref(rect))
        # start from the top-left at a moderate height, so even a small test screen has room to grow
        scale = (u32.GetDpiForWindow(self._hwnd) or 96) / 96
        u32.SetWindowPos(self._hwnd, None, 20, 20, rect.right - rect.left, int(480 * scale), 0x0004 | 0x0010)
        time.sleep(0.4)
        u32.GetWindowRect(self._hwnd, ctypes.byref(rect))
        before = rect.bottom - rect.top
        x, y = (rect.left + rect.right) // 2, rect.bottom + 5     # just below the window: clicks nothing in it
        u32.SetCursorPos(x, y)
        u32.mouse_event(0x0002, 0, 0, 0, 0)                       # left button down
        self.begin_resize()
        for step in range(1, 21):                                 # drag 120 px down over ~0.4 s
            u32.SetCursorPos(x, y + step * 6)
            time.sleep(0.02)
        time.sleep(0.2)
        u32.mouse_event(0x0004, 0, 0, 0, 0)                       # left button up
        time.sleep(0.4)
        u32.GetWindowRect(self._hwnd, ctypes.byref(rect))
        after = rect.bottom - rect.top
        result = {}
        t = threading.Thread(target=lambda: result.update(js=self._window.evaluate_js("1 + 1")), daemon=True)
        t.start(); t.join(5)                                      # the page must still answer quickly
        return {"height_before": before, "height_after": after, "resize_ok": after - before >= 60,
                "resize_finished": not self._resizing, "responsive": result.get("js") == 2}


def on_shown(window, api):
    """Once the window exists: remember its handle (for resizing) and round its corners."""
    if sys.platform != "win32":
        return
    try:
        api._hwnd = int(window.native.Handle.ToInt64())
    except Exception:
        log.warning("Could not read the window handle: %s", traceback.format_exc())
    round_corners(window, api._hwnd)
    if api._hwnd:
        threading.Thread(target=api._layer_loop, daemon=True).start()


def round_corners(window, hwnd=None):
    """Windows 11: ask the compositor for rounded, antialiased corners with a soft shadow."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = hwnd or int(window.native.Handle.ToInt64())
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


def webview2_installed():
    """True if the Edge WebView2 Runtime is registered (machine-wide or for this user)."""
    if sys.platform != "win32":
        return True
    import winreg
    client = "Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, path in ((winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + client),
                       (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + client),
                       (winreg.HKEY_CURRENT_USER, "Software\\" + client)):
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def message_box(text, buttons=0x40):
    """Plain Windows message box (0x40 = OK with an info icon). Returns the button pressed."""
    if SMOKE or sys.platform != "win32":
        return 0
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, text, core.APP_NAME, buttons)
    except Exception:
        return 0


def explain_start_failure(exc):
    """Say what actually went wrong, instead of guessing."""
    if not webview2_installed():
        msg = ("DeskTodo needs the Microsoft Edge WebView2 Runtime, which is missing on this PC.\n\n"
               "Click OK to open Microsoft's download page, install the \"Evergreen\" runtime, "
               "then start DeskTodo again.")
        if message_box(msg, 0x41) == 1:  # OK / Cancel
            webbrowser.open(WEBVIEW2_URL)
        return
    if "0x80131515" in str(exc):  # .NET won't load files marked as downloaded
        message_box("Windows is blocking DeskTodo's files because they came from a downloaded zip.\n\n"
                    "Fix: right-click the DeskTodo zip > Properties > tick Unblock > OK, then unzip it "
                    "again and replace the DeskTodo folder.", 0x30)
        return
    message_box("DeskTodo couldn't open its window.\n\n"
                f"{type(exc).__name__}: {str(exc)[:300]}\n\n"
                "If another DeskTodo is still running, close it (Task Manager > DeskTodo > End task) "
                f"and start DeskTodo again.\n\nDetails were saved to:\n{LOG_FILE}", 0x30)


_instance_mutex = None


def already_running():
    """Allow one DeskTodo at a time. If one is open, bring its window to the front."""
    global _instance_mutex
    if sys.platform != "win32" or SMOKE:
        return False
    try:
        import ctypes
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        _instance_mutex = k32.CreateMutexW(None, False, "Local\\DeskTodo.SingleInstance")
        if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
            return False
        hwnd = u32.FindWindowW(None, core.APP_NAME)
        if hwnd:
            u32.ShowWindow(hwnd, 9)  # SW_RESTORE
            u32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if core.selftest() else 1)
    if already_running():
        log.info("Another DeskTodo is running; brought it to the front.")
        return
    try:
        run()
    except Exception as exc:
        log.error("Crashed: %s", traceback.format_exc())
        if SMOKE:
            with open(os.path.join(tempfile.gettempdir(), "desktodo_smoke.json"), "w", encoding="utf-8") as f:
                json.dump({"ok": False, "error": traceback.format_exc()}, f)
        explain_start_failure(exc)
        sys.exit(1)


def unblock_bundled_files():
    """Clear Windows' "downloaded from the internet" mark from the app's own DLLs.

    Files unzipped from a downloaded zip carry that mark unless the zip was unblocked first,
    and .NET then refuses to load them (FileLoadException, HRESULT 0x80131515)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    cleared = 0
    for root, _dirs, files in os.walk(core.resource_dir()):
        for name in files:
            if name.lower().endswith((".dll", ".exe", ".pyd")):
                try:
                    os.remove(os.path.join(root, name) + ":Zone.Identifier")
                    cleared += 1
                except OSError:
                    pass  # no mark on this file
    if cleared:
        log.info("Cleared the downloaded-file mark from %d bundled files", cleared)


def run():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    unblock_bundled_files()

    import webview

    api = Api()
    settings = api._data.setdefault("settings", {})
    geo = settings.get("window") or {}
    dark = settings.get("theme", "dark") == "dark"
    kwargs = {}
    log.info("Starting DeskTodo; saved window: %s", geo)
    if not (isinstance(geo.get("w"), (int, float)) and 300 <= geo["w"] <= 4000
            and isinstance(geo.get("h"), (int, float)) and 300 <= geo["h"] <= 4000):
        geo = {}  # ignore a broken saved size (e.g. saved while minimised)
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
        on_top=api._layer == "top",
        background_color="#0f0f0f" if dark else "#e8e8e6",
        text_select=True,
        **kwargs,
    )
    api._window = window
    window.events.shown += lambda: on_shown(window, api)
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
    log.info("Starting DeskTodo %s (gui=%s)", core.APP_VERSION, gui)
    # Remove the browser cache older versions kept in the data folder: it could keep showing an old
    # interface after an update. (Tasks and notes live in data.json, which is never touched here.)
    import shutil
    shutil.rmtree(os.path.join(core.data_dir(), "EBWebView"), ignore_errors=True)
    # private_mode: WebView2 keeps no cache on disk, so every update shows its new interface right away.
    webview.start(gui=gui, private_mode=True, debug=SMOKE)


if __name__ == "__main__":
    main()
