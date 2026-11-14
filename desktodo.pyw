"""
DeskTodo - a weekly to-do list and notes app for your Windows desktop.

Pure Python standard library (tkinter). No accounts. The only internet use is
weather (open-meteo.com) and, if you connect it, your Outlook calendar link.
Everything is saved automatically to %APPDATA%\\DeskTodo\\data.json.

To-do tab
  Click a day name             open / close that day
  Enter in "Add a new task..." add a task
  Double-click a task          edit it (Enter saves, Esc cancels)
  Hover a task: +              add a sub-task underneath it
  Hover a task: x              delete it
  Right-click a task           more options (move to tomorrow, ...)
  Unfinished tasks from earlier days move to today automatically.

Notes tab
  Ctrl+B                       bold
  Toolbar: B, bullet list, heading
  Enter on an empty bullet     ends the list

At a glance tab
  Big clock, weather for two cities (click "..." on a card to change city or units),
  upcoming Outlook meetings (via your calendar's published ICS link) and today's tasks.

Anywhere
  Ctrl+1 / 2 / 3               switch to At a glance / To-do / Notes
  Ctrl+T                       keep window on top
"""

import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import date, datetime, timedelta, timezone
from tkinter import font as tkfont
from tkinter import messagebox

APP_NAME = "DeskTodo"
BULLET = "•  "  # "•  "

# =========================================================================== paths & storage


def resource_dir():
    # PyInstaller unpacks bundled files to sys._MEIPASS
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


DATA_FILE = os.path.join(data_dir(), "data.json")
OLD_FILE = os.path.join(data_dir(), "tasks.json")  # version 1 of the app


def new_id():
    return uuid.uuid4().hex[:12]


def today_iso():
    return date.today().isoformat()


def load_data():
    data = None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        try:  # keep an unreadable file instead of silently overwriting it
            os.replace(DATA_FILE, DATA_FILE + ".broken")
        except OSError:
            pass
    if not isinstance(data, dict):
        data = {}
    data.setdefault("days", {})
    data.setdefault("notes", [])
    data.setdefault("settings", {})

    # One-time import of tasks from the first version of DeskTodo.
    if not data.get("imported_v1") and os.path.exists(OLD_FILE):
        try:
            with open(OLD_FILE, "r", encoding="utf-8") as f:
                old = json.load(f)
            day = data["days"].setdefault(today_iso(), [])
            for t in old.get("tasks", []):
                if not t.get("done"):
                    day.append({"id": new_id(), "text": t.get("text", ""), "done": False, "children": []})
        except (OSError, ValueError, AttributeError):
            pass
        data["imported_v1"] = True
    return data


def save_data(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)  # atomic: never leaves a half-written file


def roll_over(data):
    """Move unfinished tasks from past days to today. Returns True if anything moved."""
    today = today_iso()
    moved = []
    for day in sorted(data["days"]):
        if day >= today:
            continue
        keep = []
        for t in data["days"][day]:
            (keep if t.get("done") else moved).append(t)
        data["days"][day] = keep
    if moved:
        data["days"][today] = moved + data["days"].get(today, [])
    for day in [d for d, tasks in data["days"].items() if not tasks]:
        del data["days"][day]
    return bool(moved)


# =========================================================================== look

THEMES = {
    # Calm, warm neutrals with one amber accent (inspired by Rivian's app).
    "light": {
        "bg": "#efeee9", "card": "#ffffff", "text": "#161616", "muted": "#7b7a75", "faint": "#b2b1ab",
        "line": "#dcdbd5", "chip": "#e3e2dc", "field": "#efeee9", "sel": "#f6dc8c",
        "accent": "#f5b400", "accent_text": "#a77a00", "on_accent": "#161616", "on_accent_muted": "#5c4500",
        "check": "#161616",
    },
    "dark": {
        "bg": "#111111", "card": "#1d1d1d", "text": "#f2f2f0", "muted": "#8e8e8a", "faint": "#565654",
        "line": "#2b2b2b", "chip": "#282828", "field": "#111111", "sel": "#5a4500",
        "accent": "#f5b400", "accent_text": "#f5b400", "on_accent": "#111111", "on_accent_muted": "#3d2e00",
        "check": "#111111",
    },
}

# Design tokens shared by every screen, so the whole widget feels like one system.
PAD = 22        # outer padding left/right
GAP = 10        # space between cards
RADIUS = 16     # card corner radius
CARD_PAD = 16   # padding inside cards


def setup_fonts(root):
    """Load the bundled Barlow font; fall back to Windows' Bahnschrift or Segoe UI."""
    fdir = os.path.join(resource_dir(), "fonts")
    if sys.platform == "win32" and os.path.isdir(fdir):
        try:
            import ctypes
            for name in os.listdir(fdir):
                if name.lower().endswith(".ttf"):
                    # 0x10 = FR_PRIVATE: only this app sees the font, nothing is installed
                    ctypes.windll.gdi32.AddFontResourceExW(os.path.join(fdir, name), 0x10, 0)
        except Exception:
            pass
    fams = set(tkfont.families(root))
    if "Barlow" in fams:
        body, heavy = "Barlow", ("Barlow ExtraBold" if "Barlow ExtraBold" in fams else "Barlow")
        semi = "Barlow SemiBold" if "Barlow SemiBold" in fams else "Barlow"
        light = "Barlow Light" if "Barlow Light" in fams else "Barlow"
        heavy_w = "normal" if heavy != "Barlow" else "bold"
        semi_w = "normal" if semi != "Barlow" else "bold"
    elif "Bahnschrift" in fams:
        body = "Bahnschrift"
        heavy = "Bahnschrift SemiBold" if "Bahnschrift SemiBold" in fams else "Bahnschrift"
        semi, heavy_w, semi_w = heavy, "bold", "normal"
        light = "Bahnschrift Light" if "Bahnschrift Light" in fams else "Bahnschrift"
    else:
        body = heavy = semi = "Segoe UI"
        light = "Segoe UI Light" if "Segoe UI Light" in fams else "Segoe UI"
        heavy_w = semi_w = "bold"

    F = tkfont.Font
    return {
        "day": F(root, family=heavy, size=22, weight=heavy_w),
        "title": F(root, family=heavy, size=17, weight=heavy_w),
        "tab": F(root, family=heavy, size=11, weight=heavy_w),
        "body": F(root, family=body, size=11),
        "body_done": F(root, family=body, size=11, overstrike=True),
        "bold": F(root, family=body, size=11, weight="bold"),
        "h": F(root, family=semi, size=14, weight=semi_w),
        "small": F(root, family=body, size=9),
        "small_b": F(root, family=semi, size=9, weight=semi_w),
        "note_title": F(root, family=semi, size=12, weight=semi_w),
        "icon": F(root, family=body, size=14),
        "clock": F(root, family=light, size=56),
        "temp": F(root, family=light, size=32),
        "month": F(root, family=heavy, size=40, weight=heavy_w),
        "year": F(root, family=semi, size=15, weight=semi_w),
        "cal": F(root, family=semi, size=13, weight=semi_w),
    }


# =========================================================================== small widgets


class PlaceholderEntry(tk.Entry):
    def __init__(self, master, placeholder, colors, **kw):
        super().__init__(master, relief="flat", bd=0, highlightthickness=0, **kw)
        self.placeholder = placeholder
        self.colors = colors
        self.showing = False
        self.config(insertbackground=colors["text"])
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self._focus_out()

    def _focus_in(self, _e=None):
        if self.showing:
            self.delete(0, "end")
            self.config(fg=self.colors["text"])
            self.showing = False

    def _focus_out(self, _e=None):
        if not self.get():
            self.insert(0, self.placeholder)
            self.config(fg=self.colors["faint"])
            self.showing = True

    def value(self):
        return "" if self.showing else self.get()

    def clear(self):
        if not self.showing:
            self.delete(0, "end")


class ScrollArea(tk.Frame):
    """A vertically scrolling frame. Put widgets in .inner"""

    def __init__(self, master, colors, on_width=None):
        super().__init__(master, bg=colors["bg"])
        self.on_width = on_width
        self.canvas = tk.Canvas(self, bg=colors["bg"], highlightthickness=0, bd=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=8)
        self.canvas.configure(yscrollcommand=self._autoscroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=colors["bg"])
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)

    def _autoscroll(self, first, last):
        # No visible scrollbar (cleaner widget look): the mouse wheel scrolls.
        self.bar.set(first, last)

    def _resize(self, event):
        self.canvas.itemconfigure(self.win, width=event.width)
        if self.on_width:
            self.on_width(event.width)

    def wheel(self, units):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(units, "units")


def bind_hover(row, show, hide):
    """Show/hide hover actions without flicker when moving between child widgets."""
    def leave(e):
        w = row.winfo_containing(e.x_root, e.y_root)
        if w is None or not str(w).startswith(str(row)):
            hide()

    def walk(w):
        w.bind("<Enter>", lambda e: show(), add="+")
        w.bind("<Leave>", leave, add="+")
        for c in w.winfo_children():
            walk(c)
    walk(row)


def menu(root, colors, items):
    m = tk.Menu(root, tearoff=0, bg=colors["bg"], fg=colors["text"], bd=0,
                activebackground=colors["accent"], activeforeground=colors["on_accent"])
    for label, cmd in items:
        if label is None:
            m.add_separator()
        else:
            m.add_command(label="  " + label + "    ", command=cmd)
    return m


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Card(tk.Canvas):
    """A rounded card. Put widgets in .inner (its background is .fill)."""

    def __init__(self, master, outer, fill, pad=CARD_PAD, radius=RADIUS, cursor=""):
        super().__init__(master, bg=outer, highlightthickness=0, bd=0, height=10, width=10, cursor=cursor)
        self.fill, self.pad, self.radius = fill, pad, radius
        self.inner = tk.Frame(self, bg=fill, cursor=cursor)
        self.win = self.create_window(pad, pad, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._layout)
        self.inner.bind("<Configure>", self._fit)

    def _fit(self, _e=None):
        h = self.inner.winfo_reqheight() + 2 * self.pad
        if int(float(self.cget("height"))) != h:
            self.config(height=h)

    def _layout(self, e):
        self.delete("bg")
        round_rect(self, 0, 0, e.width - 1, e.height - 1, self.radius, fill=self.fill, outline="", tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self.win, width=max(10, e.width - 2 * self.pad))
        self._fit()


def pill(parent, text, command, colors, fonts, primary=True, bg=None):
    """Small rounded-looking button used everywhere (same look as + NEW)."""
    C = colors
    lbl = tk.Label(parent, text=text, font=fonts["small_b"], padx=12, pady=5, cursor="hand2",
                   bg=C["accent"] if primary else (bg or C["bg"]),
                   fg=C["on_accent"] if primary else C["text"],
                   highlightthickness=0 if primary else 1, highlightbackground=C["line"],
                   highlightcolor=C["line"])
    lbl.bind("<Button-1>", lambda e: command())
    return lbl


# =========================================================================== app


class App:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.settings = self.data["settings"]
        roll_over(self.data)
        self.today = today_iso()

        self.F = setup_fonts(root)
        self.tab = "glance"  # always open on At a glance
        self.view = None
        self.q = queue.Queue()
        self.set_icon(root)

        root.title(APP_NAME)
        root.minsize(360, 420)
        root.geometry(self.safe_geometry(self.settings.get("geometry", "400x720")))
        root.attributes("-topmost", bool(self.settings.get("on_top", False)))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._drag = self._rs = None
        self.apply_frame()

        root.bind_all("<MouseWheel>", self._wheel)
        root.bind_all("<Button-4>", lambda e: self._wheel(e, -1))
        root.bind_all("<Button-5>", lambda e: self._wheel(e, 1))
        root.bind("<Control-t>", lambda e: self.toggle_on_top())
        root.bind("<Control-Key-1>", lambda e: self.switch("glance"))
        root.bind("<Control-Key-2>", lambda e: self.switch("todo"))
        root.bind("<Control-Key-3>", lambda e: self.switch("notes"))

        self.build()
        self.persist()
        self.root.after(15_000, self._tick)
        self.root.after(150, self._poll)

    VIEWS = ("glance", "todo", "notes")
    TAB_LABELS = {"todo": "TO-DO", "notes": "NOTES", "glance": "AT A GLANCE"}

    @staticmethod
    def set_icon(win):
        assets = os.path.join(resource_dir(), "assets")
        try:
            if sys.platform == "win32" and os.path.exists(os.path.join(assets, "desktodo.ico")):
                win.iconbitmap(default=os.path.join(assets, "desktodo.ico"))
            elif os.path.exists(os.path.join(assets, "desktodo.png")):
                win._icon = tk.PhotoImage(file=os.path.join(assets, "desktodo.png"))
                win.iconphoto(True, win._icon)
        except tk.TclError:
            pass

    # ---- background work (network) ---------------------------------------------------

    def run_bg(self, work, done):
        """Run work() on a thread; call done(result, error) back on the UI thread."""
        def runner():
            try:
                res, err = work(), None
            except Exception as exc:  # network errors, bad data, ...
                res, err = None, exc
            self.q.put(lambda: done(res, err))
        threading.Thread(target=runner, daemon=True).start()

    def _poll(self):
        while True:
            try:
                job = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception:
                pass
        self.root.after(150, self._poll)

    def dialog(self, title, width=360):
        """A small window in the app's style. Returns (window, body frame)."""
        C, F = self.C, self.F
        d = tk.Toplevel(self.root)
        d.title(title)
        d.configure(bg=C["bg"])
        d.resizable(False, False)
        self.set_icon(d)
        if self.settings.get("on_top"):
            d.attributes("-topmost", True)
        d.geometry(f"+{self.root.winfo_rootx() + 16}+{self.root.winfo_rooty() + 70}")
        body = tk.Frame(d, bg=C["bg"], width=width)
        body.pack(fill="both", expand=True, padx=PAD, pady=(18, 20))
        tk.Frame(body, width=width - 2 * PAD, height=0, bg=C["bg"]).pack()  # fixes the dialog's width
        tk.Label(body, text=title.upper(), font=F["tab"], fg=C["text"], bg=C["bg"]).pack(anchor="w", pady=(0, 10))
        d.bind("<Escape>", lambda e: d.destroy())
        d.after(50, d.focus_force)
        return d, body

    # ---- widget mode (no title bar) -----------------------------------------------

    @property
    def widget(self):
        return self.settings.get("widget", True)

    def apply_frame(self):
        self.root.overrideredirect(self.widget)
        if sys.platform == "win32":
            self.root.after(20, self._win_style)

    def _win_style(self):
        """Keep a taskbar button while borderless, and ask Windows 11 for rounded corners."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id())
            if self.widget:
                GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
            self.root.after(60, self.root.focus_force)
        except Exception:
            pass

    def toggle_frame(self):
        self.settings["widget"] = not self.widget
        self.persist()
        self.apply_frame()
        self.leaving()
        self.build()

    def safe_geometry(self, geo):
        """Make sure a saved position is still on a screen (e.g. after unplugging a monitor)."""
        try:
            size, _, pos = geo.partition("+")
            w, h = (int(v) for v in size.split("x"))
            if not pos:
                return geo
            x, y = (int(v) for v in pos.split("+")[:2])
        except ValueError:
            return "400x720"
        left, top = 0, 0
        right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if sys.platform == "win32":
            try:
                import ctypes
                gm = ctypes.windll.user32.GetSystemMetrics
                left, top = gm(76), gm(77)
                right, bottom = left + gm(78), top + gm(79)
            except Exception:
                pass
        x = min(max(x, left), max(left, right - 120))
        y = min(max(y, top), max(top, bottom - 120))
        return f"{w}x{h}+{x}+{y}"

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        if self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _resize_start(self, e):
        self._rs = (e.x_root, e.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _resize_move(self, e):
        if self._rs:
            x0, y0, w0, h0 = self._rs
            self.root.geometry(f"{max(320, w0 + e.x_root - x0)}x{max(420, h0 + e.y_root - y0)}")

    def window_menu(self, e):
        on_top = self.settings.get("on_top")
        items = [
            (("✓ " if on_top else "    ") + "Keep on top", self.toggle_on_top),
            ("Show window frame" if self.widget else "Hide window frame (widget look)", self.toggle_frame),
            (None, None),
            ("Close DeskTodo", self.on_close),
        ]
        menu(self.root, self.C, items).tk_popup(e.x_root, e.y_root)

    @property
    def C(self):
        return THEMES[self.settings.get("theme", "dark")]

    # ---- shell -----------------------------------------------------------------

    def build(self):
        for w in self.root.winfo_children():
            w.destroy()
        C = self.C
        border = 1 if self.widget else 0
        self.root.configure(bg=C["bg"], highlightthickness=border,
                            highlightbackground=C["line"], highlightcolor=C["line"])

        top = tk.Frame(self.root, bg=C["bg"], cursor="fleur" if self.widget else "")
        top.pack(fill="x", padx=22, pady=(14, 0))
        if self.widget:
            top.bind("<ButtonPress-1>", self._drag_start)
            top.bind("<B1-Motion>", self._drag_move)
        top.bind("<Button-3>", self.window_menu)

        if self.widget:
            close = tk.Label(top, text="×", font=self.F["icon"], fg=C["faint"], bg=C["bg"],
                             cursor="hand2", padx=2)
            close.pack(side="right", padx=(10, 0))
            close.bind("<Button-1>", lambda e: self.on_close())
            close.bind("<Enter>", lambda e: close.config(fg=C["accent_text"]))
            close.bind("<Leave>", lambda e: close.config(fg=C["faint"]))
        for key in self.VIEWS:
            label = self.TAB_LABELS[key]
            on = key == self.tab
            box = tk.Frame(top, bg=C["bg"])
            box.pack(side="left", padx=(0, 16))
            lbl = tk.Label(box, text=label, font=self.F["tab"], bg=C["bg"], cursor="hand2",
                           fg=C["text"] if on else C["faint"])
            lbl.pack()
            tk.Frame(box, height=2, bg=C["accent"] if on else C["bg"]).pack(fill="x", pady=(2, 0))
            lbl.bind("<Button-1>", lambda e, k=key: self.switch(k))

        # theme toggle (drawn, so it looks the same everywhere)
        dark = self.settings.get("theme", "dark") == "dark"
        icon = tk.Canvas(top, width=22, height=22, bg=C["bg"], highlightthickness=0, cursor="hand2")
        icon.pack(side="right")
        if dark:  # sun -> switch to light
            icon.create_oval(7, 7, 15, 15, outline=C["text"], width=2)
            for x1, y1, x2, y2 in ((11, 1, 11, 4), (11, 18, 11, 21), (1, 11, 4, 11), (18, 11, 21, 11),
                                   (4, 4, 6, 6), (16, 16, 18, 18), (4, 18, 6, 16), (16, 6, 18, 4)):
                icon.create_line(x1, y1, x2, y2, fill=C["text"], width=2)
        else:  # moon -> switch to dark
            icon.create_oval(3, 3, 19, 19, fill=C["text"], outline="")
            icon.create_oval(8, 0, 22, 14, fill=C["bg"], outline="")
        icon.bind("<Button-1>", lambda e: self.toggle_theme())

        on_top = bool(self.settings.get("on_top"))
        pin = tk.Label(top, text="PIN", font=self.F["small_b"], cursor="hand2", padx=6,
                       bg=C["accent"] if on_top else C["bg"], fg=C["on_accent"] if on_top else C["faint"])
        pin.pack(side="right", padx=(0, 12))
        pin.bind("<Button-1>", lambda e: self.toggle_on_top())

        if self.widget:  # thin bottom strip with a resize handle in the corner
            strip_bg = C["bg"]
            if self.tab == "todo":
                strip_bg = section_bg(C, self.settings.get("theme", "dark") == "dark", TodoView.DAYS - 1)
            strip = tk.Frame(self.root, bg=strip_bg, height=14)
            strip.pack(side="bottom", fill="x")
            grip = tk.Canvas(strip, width=14, height=14, highlightthickness=0, bg=strip_bg,
                             cursor="size_nw_se" if sys.platform == "win32" else "bottom_right_corner")
            for k in (4, 8, 12):
                grip.create_line(13, k, k, 13, fill=C["faint"])
            grip.pack(side="right")
            grip.bind("<ButtonPress-1>", self._resize_start)
            grip.bind("<B1-Motion>", self._resize_move)

        self.body = tk.Frame(self.root, bg=C["bg"])
        self.body.pack(fill="both", expand=True)
        self.view = {"todo": TodoView, "notes": NotesView, "glance": GlanceView}[self.tab](self, self.body)


    def switch(self, tab):
        if tab == self.tab:
            return
        self.leaving()
        self.tab = self.settings["tab"] = tab
        self.build()

    def leaving(self):
        if self.view and hasattr(self.view, "flush"):
            self.view.flush()

    def toggle_theme(self):
        self.leaving()
        self.settings["theme"] = "light" if self.settings.get("theme", "dark") == "dark" else "dark"
        self.persist()
        self.build()

    def toggle_on_top(self):
        self.settings["on_top"] = not self.settings.get("on_top", False)
        self.root.attributes("-topmost", self.settings["on_top"])
        self.persist()
        self.leaving()
        self.build()

    def _wheel(self, e, units=None):
        if units is None:
            units = -1 if e.delta > 0 else 1
        if isinstance(e.widget, tk.Text):
            return  # the notes editor scrolls itself
        if self.view and getattr(self.view, "scroll", None):
            try:
                self.view.scroll.wheel(units)
            except tk.TclError:
                pass

    def _tick(self):
        # New day while the app is open: roll unfinished tasks over to today.
        if today_iso() != self.today:
            self.today = today_iso()
            roll_over(self.data)
            self.persist()
            if self.tab in ("todo", "glance"):
                self.leaving()
                self.build()
        self.root.after(15_000, self._tick)

    def persist(self):
        try:
            save_data(self.data)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Couldn't save your data:\n{exc}")

    def on_close(self):
        self.leaving()
        self.settings["geometry"] = self.root.geometry()
        self.persist()
        self.root.destroy()


# =========================================================================== to-do tab


def mix(color, target, amount):
    """Blend #rrggbb `color` towards `target` by `amount` (0..1)."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(target[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def section_bg(C, dark, i):
    """Background of the i-th day band: each later day steps a little further from the page colour."""
    return mix(C["bg"], "#ffffff" if dark else "#000000", (0.028 if dark else 0.035) * i)


def clock_text(now):
    return f"{now:%I}".lstrip("0") + f":{now:%M}" + f"{now:%p}".lower()


class TodoView:
    DAYS = 7  # today + the next six days

    def __init__(self, app, parent):
        self.app, self.C, self.F = app, app.C, app.F
        self.root = app.root
        self.today = date.fromisoformat(app.today)
        self.open_day = app.today
        self.editing = None       # id of task being edited
        self.adding_sub = None    # id of task getting a new sub-task
        self.focus_add = False
        self.wrap_labels = []
        self.clock_lbl = None

        self.scroll = ScrollArea(parent, self.C, on_width=self.rewrap)
        self.scroll.pack(fill="both", expand=True, pady=(6, 0))
        self.render(top=True)
        self.root.after(15_000, self.tick_clock)

    def tick_clock(self):
        try:
            if not self.scroll.winfo_exists():
                return  # this view was replaced
            if self.clock_lbl is not None and self.clock_lbl.winfo_exists():
                self.clock_lbl.config(text=self.today_line(self.today))
        except tk.TclError:
            return
        self.root.after(15_000, self.tick_clock)

    @staticmethod
    def today_line(d):
        return f"{d:%B} {d.day}, {d.year}  —  {clock_text(datetime.now())}"

    def day_bg(self, i):
        return section_bg(self.C, self.app.settings.get("theme", "dark") == "dark", i)

    # ---- data helpers ----------------------------------------------------------

    def tasks(self, iso):
        return self.app.data["days"].setdefault(iso, [])

    def find(self, task_id):
        """Return (task, list_it_lives_in, day_iso, parent_task_or_None)."""
        for iso, tasks in self.app.data["days"].items():
            for t in tasks:
                if t["id"] == task_id:
                    return t, tasks, iso, None
                for c in t.get("children", []):
                    if c["id"] == task_id:
                        return c, t["children"], iso, t
        return None, None, None, None

    def save_and_render(self):
        self.app.persist()
        self.render()

    # ---- rendering -------------------------------------------------------------

    def render(self, top=False):
        y = self.scroll.canvas.yview()[0]
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self.wrap_labels = []
        self.clock_lbl = None

        for i in range(self.DAYS):
            self.render_day(self.today + timedelta(days=i), i)
        # the last day's colour carries on to the bottom of the window
        last = self.day_bg(self.DAYS - 1)
        self.scroll.canvas.config(bg=last)
        self.scroll.inner.config(bg=last)

        self.root.update_idletasks()
        self.rewrap(self.scroll.canvas.winfo_width())
        self.scroll.canvas.yview_moveto(0 if top else y)

    def render_day(self, d, i):
        C, F = self.C, self.F
        bg = self.day_bg(i)
        iso = d.isoformat()
        is_open = iso == self.open_day
        tasks = self.app.data["days"].get(iso, [])

        outer = tk.Frame(self.scroll.inner, bg=bg)
        outer.pack(fill="x")
        sec = tk.Frame(outer, bg=bg)
        sec.pack(fill="x", padx=22)

        head = tk.Frame(sec, bg=bg, cursor="hand2")
        head.pack(fill="x", pady=(14 if i else 6, 14 if not is_open else 0))
        name = tk.Label(head, text=d.strftime("%A").upper(), font=F["day"], fg=C["text"], bg=bg)
        name.pack(side="left")
        clickers = [outer, head, name]
        if not is_open:
            left = sum(1 for t in tasks if not t["done"])
            if left:
                cnt = tk.Label(head, text=str(left), font=F["small_b"], fg=C["muted"], bg=bg)
                cnt.pack(side="right")
                clickers.append(cnt)
        for w in clickers:
            w.bind("<Button-1>", lambda e, k=iso: self.toggle_day(k))

        if not is_open:
            return

        if i == 0:
            sub = tk.Label(sec, text=self.today_line(d), font=F["small"], fg=C["muted"], bg=bg)
            self.clock_lbl = sub
        else:
            extra = "  —  Tomorrow" if i == 1 else ""
            sub = tk.Label(sec, text=f"{d:%B} {d.day}, {d.year}{extra}", font=F["small"], fg=C["muted"], bg=bg)
        sub.pack(anchor="w", pady=(0, 10))

        for t in tasks:
            self.render_task(sec, t, 0, bg)
            for c in t.get("children", []):
                self.render_task(sec, c, 1, bg)
            if self.adding_sub == t["id"]:
                self.render_sub_entry(sec, t, bg)

        add = PlaceholderEntry(sec, "Add a new task...", C, font=F["body"], bg=bg)
        add.pack(fill="x", pady=(14, 22))
        add.bind("<Return>", lambda e, k=iso, w=add: self.add_task(k, w))
        add.bind("<Escape>", lambda e: self.root.focus_set())
        if self.focus_add:
            self.focus_add = False
            add.focus_set()

    def render_task(self, parent, t, depth, bg):
        C, F = self.C, self.F
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=2, padx=(26 * depth, 0))

        size = 15 if depth == 0 else 13
        chk = tk.Canvas(row, width=size + 2, height=size + 2, bg=bg, highlightthickness=0, cursor="hand2")
        chk.pack(side="left", anchor="n", pady=(3, 0), padx=(0, 9))
        if t["done"]:
            chk.create_rectangle(1, 1, size, size, fill=C["accent"], outline=C["accent"])
            s = size / 15
            chk.create_line(4 * s, 8 * s, 7 * s, 11 * s, 12 * s, 4.5 * s, fill=C["check"], width=2)
        else:
            chk.create_rectangle(1, 1, size, size, outline=C["muted"], width=1.4)
        chk.bind("<Button-1>", lambda e: self.toggle_done(t["id"]))

        if self.editing == t["id"]:
            ed = tk.Entry(row, font=F["body"], bg=C["chip"], fg=C["text"], insertbackground=C["text"],
                          relief="flat", bd=0, highlightthickness=0)
            ed.insert(0, t["text"])
            ed.pack(side="left", fill="x", expand=True, ipady=1)
            ed.focus_set()
            ed.select_range(0, "end")
            ed.bind("<Return>", lambda e: self.finish_edit(t["id"], ed.get()))
            ed.bind("<Escape>", lambda e: self.cancel_edit())
            ed.bind("<FocusOut>", lambda e: self.finish_edit(t["id"], ed.get()))
            return

        actions = []
        dele = tk.Label(row, text="×", font=F["icon"], fg=bg, bg=bg, cursor="hand2", padx=3)
        dele.pack(side="right", anchor="n")
        dele.bind("<Button-1>", lambda e: self.delete(t["id"]))
        actions.append(dele)
        if depth == 0:
            plus = tk.Label(row, text="+", font=F["icon"], fg=bg, bg=bg, cursor="hand2", padx=3)
            plus.pack(side="right", anchor="n")
            plus.bind("<Button-1>", lambda e: self.start_sub(t["id"]))
            actions.append(plus)

        txt = tk.Label(row, text=t["text"], font=F["body_done"] if t["done"] else F["body"],
                       fg=C["muted"] if t["done"] else C["text"], bg=bg,
                       anchor="w", justify="left", wraplength=250)
        txt.pack(side="left", fill="x", expand=True)
        self.wrap_labels.append((txt, 26 * depth))

        for w in (row, txt):
            w.bind("<Double-Button-1>", lambda e: self.start_edit(t["id"]))
        for w in (row, txt, chk):
            w.bind("<Button-3>", lambda e: self.context(e, t["id"], depth))

        def show():
            for a in actions:
                a.config(fg=C["muted"])

        def hide():
            for a in actions:
                a.config(fg=bg)
        bind_hover(row, show, hide)

    def render_sub_entry(self, parent, t, bg):
        C = self.C
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=2, padx=(26, 0))
        tk.Label(row, text="↳", font=self.F["body"], fg=C["faint"], bg=bg).pack(side="left", padx=(0, 6))
        e = PlaceholderEntry(row, "Add a sub-task...", C, font=self.F["body"], bg=bg)
        e.pack(side="left", fill="x", expand=True)
        e.focus_set()
        e._focus_in()
        e.bind("<Return>", lambda ev: self.add_sub(t["id"], e))
        e.bind("<Escape>", lambda ev: self.stop_sub())
        e.bind("<FocusOut>", lambda ev: self.root.after(150, lambda: self.stop_sub() if not e.value() else None))

    def rewrap(self, width):
        for lbl, indent in self.wrap_labels:
            try:
                lbl.config(wraplength=max(120, width - 44 - indent - 70))
            except tk.TclError:
                pass

    # ---- actions ---------------------------------------------------------------

    def toggle_day(self, iso):
        self.open_day = None if self.open_day == iso else iso
        self.adding_sub = self.editing = None
        self.render()

    def add_task(self, iso, entry):
        text = entry.value().strip()
        if not text:
            return
        self.tasks(iso).append({"id": new_id(), "text": text, "done": False, "children": []})
        self.focus_add = True
        self.save_and_render()

    def toggle_done(self, tid):
        t, _, _, parent = self.find(tid)
        if not t:
            return
        t["done"] = not t["done"]
        if t["done"]:
            for c in t.get("children", []):  # finishing a task finishes its sub-tasks
                c["done"] = True
        elif parent and parent["done"]:     # reopening a sub-task reopens its parent
            parent["done"] = False
        self.save_and_render()

    def delete(self, tid):
        t, lst, _, _ = self.find(tid)
        if t:
            lst.remove(t)
            self.save_and_render()

    def start_edit(self, tid):
        self.editing, self.adding_sub = tid, None
        self.render()

    def finish_edit(self, tid, text):
        if self.editing != tid:
            return  # already handled (Enter is followed by FocusOut)
        self.editing = None
        t, _, _, _ = self.find(tid)
        if t and text.strip():
            t["text"] = text.strip()
            self.app.persist()
        self.root.after_idle(self.render)

    def cancel_edit(self):
        self.editing = None
        self.render()

    def start_sub(self, tid):
        self.adding_sub, self.editing = tid, None
        self.render()

    def stop_sub(self):
        if self.adding_sub:
            self.adding_sub = None
            self.render()

    def add_sub(self, tid, entry):
        text = entry.value().strip()
        t, _, _, _ = self.find(tid)
        if not text or not t:
            return
        t.setdefault("children", []).append({"id": new_id(), "text": text, "done": False})
        t["done"] = False
        self.save_and_render()  # keeps the sub-task box open for the next one

    def move(self, tid, iso):
        t, lst, _, _ = self.find(tid)
        if t:
            lst.remove(t)
            self.tasks(iso).append(t)
            self.save_and_render()

    def make_sub(self, tid):
        """Turn a task into a sub-task of the task above it."""
        t, lst, _, _ = self.find(tid)
        i = lst.index(t)
        if i == 0:
            return
        above = lst[i - 1]
        lst.remove(t)
        kids = t.pop("children", [])
        above.setdefault("children", []).append({"id": t["id"], "text": t["text"], "done": t["done"]})
        above["children"].extend(kids)
        self.save_and_render()

    def make_top(self, tid):
        t, lst, iso, parent = self.find(tid)
        lst.remove(t)
        day = self.tasks(iso)
        day.insert(day.index(parent) + 1, {**t, "children": []})
        self.save_and_render()

    def context(self, e, tid, depth):
        t, lst, iso, _ = self.find(tid)
        tomorrow = (date.fromisoformat(iso) + timedelta(days=1)).isoformat()
        items = [("Edit", lambda: self.start_edit(tid))]
        if depth == 0:
            items.append(("Add sub-task", lambda: self.start_sub(tid)))
            if lst.index(t) > 0:
                items.append(("Indent under task above", lambda: self.make_sub(tid)))
            items.append((None, None))
            items.append(("Move to next day", lambda: self.move(tid, tomorrow)))
            if iso != self.today.isoformat():
                items.append(("Move to today", lambda: self.move(tid, self.today.isoformat())))
        else:
            items.append(("Outdent (make a main task)", lambda: self.make_top(tid)))
        items += [(None, None), ("Delete", lambda: self.delete(tid))]
        m = menu(self.root, self.C, items)
        m.tk_popup(e.x_root, e.y_root)


# =========================================================================== online services
# Weather: open-meteo.com (free, no key). Calendar: an Outlook "published calendar" ICS link.

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

USER_AGENT = "DeskTodo/1.0 (desktop to-do widget)"


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


WEATHER_CODES = {
    0: ("Clear", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "partly"), 3: ("Cloudy", "cloud"),
    45: ("Fog", "fog"), 48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Storm & hail", "storm"), 99: ("Storm & hail", "storm"),
}

DEFAULT_CITIES = [
    {"name": "Glenwood Springs", "region": "Colorado", "lat": 39.5505, "lon": -107.3248},
    {"name": "Basalt", "region": "Colorado", "lat": 39.3689, "lon": -107.0328},
]


def city_key(c):
    return f"{c['lat']:.3f},{c['lon']:.3f}"


def fetch_weather(lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,apparent_temperature,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
    })
    j = json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))
    cur, d = j["current"], j["daily"]
    return {"temp": cur["temperature_2m"], "feels": cur["apparent_temperature"], "code": cur["weather_code"],
            "is_day": cur.get("is_day", 1), "hi": d["temperature_2m_max"][0], "lo": d["temperature_2m_min"][0],
            "sunrise": d["sunrise"][0], "sunset": d["sunset"][0],
            "fetched": datetime.now().isoformat(timespec="seconds")}


def geocode(text):
    """'Aspen, CO' -> list of places, best matches first."""
    name, _, hint = text.partition(",")
    q = urllib.parse.urlencode({"name": name.strip(), "count": 10, "language": "en", "format": "json"})
    j = json.loads(http_get("https://geocoding-api.open-meteo.com/v1/search?" + q))
    out = []
    for r in j.get("results", []):
        out.append({"name": r["name"], "region": r.get("admin1") or r.get("country", ""),
                    "country": r.get("country", ""), "cc": r.get("country_code", ""),
                    "lat": r["latitude"], "lon": r["longitude"]})
    hint = hint.strip().lower()
    if hint:
        abbr = US_STATES.get(hint.upper(), "").lower()

        def score(p):
            fields = [p["region"].lower(), p["country"].lower(), p["cc"].lower()]
            return 0 if any(hint == f or hint in f or (abbr and abbr == f) for f in fields) else 1
        out.sort(key=score)
    return out


US_STATES = dict(zip(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
    "OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split(),
    ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida",
     "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
     "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
     "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
     "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
     "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia"]))

# Outlook writes Windows time zone names into its calendar files.
WIN_TZ = {
    "Mountain Standard Time": "America/Denver", "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles", "Central Standard Time": "America/Chicago",
    "Eastern Standard Time": "America/New_York", "US Eastern Standard Time": "America/Indiana/Indianapolis",
    "Alaskan Standard Time": "America/Anchorage", "Hawaiian Standard Time": "Pacific/Honolulu",
    "Atlantic Standard Time": "America/Halifax", "Newfoundland Standard Time": "America/St_Johns",
    "Canada Central Standard Time": "America/Regina", "Mexico Standard Time": "America/Mexico_City",
    "Central Standard Time (Mexico)": "America/Mexico_City", "SA Pacific Standard Time": "America/Bogota",
    "E. South America Standard Time": "America/Sao_Paulo", "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik", "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris", "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw", "GTB Standard Time": "Europe/Bucharest",
    "FLE Standard Time": "Europe/Kiev", "Russian Standard Time": "Europe/Moscow",
    "Israel Standard Time": "Asia/Jerusalem", "South Africa Standard Time": "Africa/Johannesburg",
    "Arabian Standard Time": "Asia/Dubai", "India Standard Time": "Asia/Kolkata",
    "Singapore Standard Time": "Asia/Singapore", "China Standard Time": "Asia/Shanghai",
    "Tokyo Standard Time": "Asia/Tokyo", "Korea Standard Time": "Asia/Seoul",
    "AUS Eastern Standard Time": "Australia/Sydney", "New Zealand Standard Time": "Pacific/Auckland",
    "UTC": "UTC", "Coordinated Universal Time": "UTC",
}


def get_tz(tzid):
    if not tzid or ZoneInfo is None:
        return None
    tzid = tzid.strip('"')
    for name in (WIN_TZ.get(tzid), tzid):
        if name:
            try:
                return ZoneInfo(name)
            except Exception:
                pass
    return None  # unknown zone: treat times as local


def ics_line(line):
    inq = False
    for i, ch in enumerate(line):
        if ch == '"':
            inq = not inq
        elif ch == ":" and not inq:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def ics_dt(value, params):
    """-> (naive wall-clock datetime, tz or None, all_day)"""
    v = value.strip()
    if params.get("VALUE") == "DATE" or len(v) == 8:
        return datetime.strptime(v[:8], "%Y%m%d"), None, True
    dt = datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
    if v.endswith("Z"):
        return dt, timezone.utc, False
    return dt, get_tz(params.get("TZID")), False


def to_local(naive, tz):
    if tz is None:
        return naive
    return naive.replace(tzinfo=tz).astimezone().replace(tzinfo=None)


def ics_text(v):
    return (v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\").strip())


def ics_duration(v):
    m = re.match(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v or "")
    if not m:
        return timedelta(0)
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def add_months(y, m, n):
    m0 = m - 1 + n
    return y + m0 // 12, m0 % 12 + 1


def days_in_month(y, m):
    y2, m2 = add_months(y, m, 1)
    return (date(y2, m2, 1) - date(y, m, 1)).days


def expand_rrule(start, rule, tz, limit):
    """Yield occurrence start times (naive, in the event's own time zone) up to `limit`."""
    r = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = r.get("FREQ", "")
    interval = max(1, int(r.get("INTERVAL", 1)))
    count = int(r["COUNT"]) if "COUNT" in r else None
    until = None
    if "UNTIL" in r:
        u = r["UNTIL"]
        if "T" in u:
            until = datetime.strptime(u[:15], "%Y%m%dT%H%M%S")
            if u.endswith("Z") and tz is not None:
                until = until.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)
            elif u.endswith("Z"):
                until = until.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        else:
            until = datetime.strptime(u[:8], "%Y%m%d").replace(hour=23, minute=59, second=59)
    byday = [d.strip() for d in r.get("BYDAY", "").split(",") if d.strip()]
    bymonthday = [int(x) for x in r.get("BYMONTHDAY", "").split(",") if x.strip()]
    t = start.time()

    def candidates():
        k = 0
        while True:
            if freq == "DAILY":
                yield [start + timedelta(days=k * interval)]
            elif freq == "WEEKLY":
                wds = sorted({WEEKDAYS[d[-2:]] for d in byday if d[-2:] in WEEKDAYS}) or [start.weekday()]
                week0 = start - timedelta(days=start.weekday())
                base = week0 + timedelta(weeks=k * interval)
                yield [base + timedelta(days=wd) for wd in wds]
            elif freq == "MONTHLY":
                y, m = add_months(start.year, start.month, k * interval)
                n = days_in_month(y, m)
                days = []
                if byday:
                    for spec in byday:
                        wd = WEEKDAYS.get(spec[-2:])
                        if wd is None:
                            continue
                        nth = int(spec[:-2] or 0)
                        all_days = [d for d in range(1, n + 1) if date(y, m, d).weekday() == wd]
                        if nth == 0:
                            days += all_days
                        elif -len(all_days) <= nth <= len(all_days) and nth != 0:
                            days.append(all_days[nth - 1] if nth > 0 else all_days[nth])
                else:
                    for md in (bymonthday or [start.day]):
                        d = md if md > 0 else n + 1 + md
                        if 1 <= d <= n:
                            days.append(d)
                yield [datetime.combine(date(y, m, d), t) for d in sorted(set(days))]
            elif freq == "YEARLY":
                y = start.year + k * interval
                try:
                    yield [datetime.combine(date(y, start.month, start.day), t)]
                except ValueError:
                    yield []
            else:
                yield [start]
                return
            k += 1

    n = 0
    for batch in candidates():
        if n > 3000:
            return
        stop = False
        for dt in batch:
            if dt < start:
                continue
            if (until and dt > until) or dt > limit:
                stop = True
                break
            n += 1
            if count is not None and n > count:
                return
            yield dt
        if stop:
            return
        if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
            return


def parse_ics(text, win_start, win_end):
    """Events overlapping [win_start, win_end) as dicts with local start/end."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = []
    for ln in raw:
        if ln[:1] in (" ", "\t") and lines:
            lines[-1] += ln[1:]
        elif ln:
            lines.append(ln)
    events, cur, in_alarm = [], None, False
    for ln in lines:
        up = ln.upper()
        if up == "BEGIN:VEVENT":
            cur, in_alarm = {"EXDATE": []}, False
        elif up == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None:
            if up == "BEGIN:VALARM":
                in_alarm = True
            elif up == "END:VALARM":
                in_alarm = False
            elif not in_alarm:
                p = ics_line(ln)
                if not p:
                    continue
                name, params, value = p
                if name == "EXDATE":
                    for v in value.split(","):
                        cur["EXDATE"].append((v, params))
                else:
                    cur[name] = (value, params)

    overrides = set()
    for ev in events:
        if "RECURRENCE-ID" in ev:
            rid, tz, _ = ics_dt(*ev["RECURRENCE-ID"])
            overrides.add((ev.get("UID", ("", {}))[0], to_local(rid, tz)))

    out = []
    for ev in events:
        if "DTSTART" not in ev:
            continue
        if ev.get("STATUS", ("", {}))[0].upper() == "CANCELLED":
            continue
        uid = ev.get("UID", ("", {}))[0]
        title = ics_text(ev.get("SUMMARY", ("(No title)", {}))[0]) or "(No title)"
        if title.lower().startswith("canceled:") or title.lower().startswith("cancelled:"):
            continue
        location = ics_text(ev.get("LOCATION", ("", {}))[0])
        start, tz, all_day = ics_dt(*ev["DTSTART"])
        if "DTEND" in ev:
            end, _, _ = ics_dt(*ev["DTEND"])
            dur = end - start
        elif "DURATION" in ev:
            dur = ics_duration(ev["DURATION"][0])
        else:
            dur = timedelta(days=1) if all_day else timedelta(0)
        exdates = set()
        for v, p in ev["EXDATE"]:
            try:
                xd, xtz, xall = ics_dt(v, p)
                exdates.add(xd if xall else to_local(xd, xtz))
            except ValueError:
                pass
        is_override = "RECURRENCE-ID" in ev
        if "RRULE" in ev and not is_override:
            starts = expand_rrule(start, ev["RRULE"][0], tz, win_end + timedelta(days=2))
        else:
            starts = [start]
        for s in starts:
            local = s if all_day else to_local(s, tz)
            if local in exdates or (all_day and s in exdates):
                continue
            if not is_override and (uid, local) in overrides:
                continue
            local_end = (s + dur) if all_day else to_local(s + dur, tz)
            if local_end <= local:
                local_end = local + (timedelta(days=1) if all_day else timedelta(minutes=1))
            if local_end > win_start and local < win_end:
                out.append({"start": local.isoformat(), "end": local_end.isoformat(),
                            "title": title, "location": location, "all_day": all_day})
    out.sort(key=lambda e: (e["start"], not e["all_day"]))
    return out


def fetch_events(url):
    url = url.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    text = http_get(url, timeout=30)
    if "BEGIN:VCALENDAR" not in text[:2000].upper():
        raise ValueError("That link didn't return a calendar (ICS) file.")
    today0 = datetime.combine(date.today(), datetime.min.time())
    # a window wide enough for the month calendar as well as "Up next"
    return parse_ics(text, today0 - timedelta(days=35), today0 + timedelta(days=100))


# =========================================================================== at-a-glance tab


def draw_weather_icon(c, kind, is_day, fg, sun):
    c.delete("all")

    def cloud(x, y, col):
        c.create_oval(x, y + 7, x + 14, y + 19, fill=col, outline="")
        c.create_oval(x + 6, y, x + 22, y + 16, fill=col, outline="")
        c.create_oval(x + 14, y + 6, x + 28, y + 19, fill=col, outline="")
        c.create_rectangle(x + 7, y + 11, x + 21, y + 19, fill=col, outline="")

    def orb(x, y, r):
        if is_day:
            c.create_oval(x - r, y - r, x + r, y + r, fill=sun, outline="")
        else:
            c.create_oval(x - r, y - r, x + r, y + r, fill=fg, outline="")
            c.create_oval(x - r + 5, y - r - 2, x + r + 5, y + r - 2, fill=c["bg"], outline="")

    if kind == "clear":
        orb(18, 16, 10)
    elif kind == "partly":
        orb(12, 10, 8)
        cloud(6, 10, fg)
    elif kind == "fog":
        for i, y in enumerate((8, 15, 22)):
            c.create_line(4 + 3 * (i % 2), y, 30 - 3 * (i % 2), y, fill=fg, width=3, capstyle="round")
    else:
        cloud(4, 2, fg)
        if kind == "rain":
            for x in (10, 17, 24):
                c.create_line(x, 25, x - 3, 31, fill=fg, width=2)
        elif kind == "snow":
            for x in (10, 17, 24):
                c.create_oval(x - 2, 25, x + 2, 29, fill=fg, outline="")
        elif kind == "storm":
            c.create_line(19, 22, 15, 28, 20, 28, 16, 34, fill=sun, width=2)


def fmt_time(dt, h24=False):
    if h24:
        return dt.strftime("%H:%M")
    return dt.strftime("%I:%M").lstrip("0") + dt.strftime("%p").lower()


class GlanceView:
    def __init__(self, app, parent):
        self.app, self.C, self.F, self.root = app, app.C, app.F, app.root
        self.settings = app.settings
        self.settings.setdefault("cities", [dict(c) for c in DEFAULT_CITIES])
        self.cache = app.data.setdefault("cache", {})
        self.cache.setdefault("weather", {})
        self.measure = self.F["clock"].copy()
        self.measure.configure(size=100)
        self.width = 400
        t = date.today()
        self.cal_month, self.cal_sel = (t.year, t.month), t
        self.wraps = []
        self.scroll = ScrollArea(parent, self.C, on_width=self.on_width)
        self.scroll.pack(fill="both", expand=True)
        self.build()
        self.tick()
        self.refresh()

    def alive(self):
        try:
            return bool(self.scroll.winfo_exists())
        except tk.TclError:
            return False

    @property
    def h24(self):
        return bool(self.settings.get("clock24"))

    def to_unit(self, c):
        if c is None:
            return "–"
        return f"{round(c * 9 / 5 + 32) if self.settings.get('units', 'F') == 'F' else round(c)}°"

    # ---- layout ----------------------------------------------------------------

    def build(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self.wraps = []
        C, F = self.C, self.F
        wrap = tk.Frame(self.scroll.inner, bg=C["bg"])
        wrap.pack(fill="x", padx=PAD, pady=(10, 24))

        # clock
        self.date_lbl = tk.Label(wrap, font=F["small_b"], fg=C["muted"], bg=C["bg"])
        self.date_lbl.pack(anchor="w")
        row = tk.Frame(wrap, bg=C["bg"])
        row.pack(fill="x")
        self.clock_lbl = tk.Label(row, font=F["clock"], fg=C["text"], bg=C["bg"], bd=0, padx=0, pady=0)
        self.clock_lbl.pack(side="left")
        self.ampm_lbl = tk.Label(row, font=F["tab"], fg=C["muted"], bg=C["bg"])
        self.ampm_lbl.pack(side="left", anchor="s", pady=(0, 16), padx=(4, 0))

        info = tk.Frame(wrap, bg=C["bg"])
        info.pack(fill="x", pady=(0, GAP + 2))
        self.sun_lbl = tk.Label(info, font=F["small"], fg=C["muted"], bg=C["bg"])
        self.sun_lbl.pack(side="left")
        tog = tk.Frame(info, bg=C["chip"])
        tog.pack(side="right")
        for label, val in (("12h", False), ("24h", True)):
            on = self.h24 == val
            b = tk.Label(tog, text=label, font=F["small_b"], padx=9, pady=2, cursor="hand2",
                         bg=C["text"] if on else C["chip"], fg=C["bg"] if on else C["muted"])
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, v=val: self.set_24(v))

        # weather cards
        grid = tk.Frame(wrap, bg=C["bg"])
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="w")
        grid.columnconfigure(1, weight=1, uniform="w")
        for i, city in enumerate(self.settings["cities"][:2]):
            card = self.weather_card(grid, i, city)
            card.grid(row=0, column=i, sticky="ew", padx=(0, GAP // 2) if i == 0 else (GAP // 2, 0))

        self.calendar_card(wrap).pack(fill="x", pady=(GAP, 0))
        self.events_card(wrap).pack(fill="x", pady=(GAP, 0))

        self.update_clock()
        self.on_width(self.width)

    def weather_card(self, parent, i, city):
        C, F = self.C, self.F
        accent = False  # all weather cards share the neutral card style
        fill = C["accent"] if accent else C["card"]
        fg = C["on_accent"] if accent else C["text"]
        mut = C["on_accent_muted"] if accent else C["muted"]
        card = Card(parent, C["bg"], fill)
        top = tk.Frame(card.inner, bg=fill)
        top.pack(fill="x")
        name = tk.Label(top, text=city["name"], font=F["small_b"], fg=fg, bg=fill, anchor="w", justify="left")
        name.pack(side="left", fill="x", expand=True)
        self.wraps.append((name, "half"))
        more = tk.Label(top, text="···", font=F["tab"], fg=mut, bg=fill, cursor="hand2")
        more.pack(side="right", anchor="n")
        more.bind("<Button-1>", lambda e: self.city_menu(e, i))
        tk.Label(card.inner, text=city.get("region", ""), font=F["small"], fg=mut, bg=fill).pack(anchor="w")

        w = self.cache["weather"].get(city_key(city))
        mid = tk.Frame(card.inner, bg=fill)
        mid.pack(fill="x", pady=(8, 2))
        tk.Label(mid, text=self.to_unit(w["temp"]) if w else "–", font=F["temp"], fg=fg, bg=fill).pack(side="left")
        if w:
            icon = tk.Canvas(mid, width=34, height=36, bg=fill, highlightthickness=0)
            icon.pack(side="right", anchor="s")
            desc, kind = WEATHER_CODES.get(int(w["code"]), ("", "cloud"))
            draw_weather_icon(icon, kind, w.get("is_day", 1), C["muted"], C["accent"])
            tk.Label(card.inner, text=desc, font=F["small_b"], fg=fg, bg=fill).pack(anchor="w")
            tk.Label(card.inner, text=f"H {self.to_unit(w['hi'])}   L {self.to_unit(w['lo'])}",
                     font=F["small"], fg=mut, bg=fill).pack(anchor="w")
        else:
            tk.Label(card.inner, text="Loading weather..." if not self.cache.get("weather_error")
                     else "Weather unavailable", font=F["small"], fg=mut, bg=fill).pack(anchor="w")
        for wdg in (card, card.inner):
            wdg.bind("<Button-3>", lambda e: self.city_menu(e, i))
        return card

    def events_card(self, parent):
        C, F = self.C, self.F
        card = Card(parent, C["bg"], C["card"])
        head = tk.Frame(card.inner, bg=C["card"])
        head.pack(fill="x")
        tk.Label(head, text="UP NEXT", font=F["tab"], fg=C["text"], bg=C["card"]).pack(side="left")
        url = self.settings.get("ics_url")
        if url:
            more = tk.Label(head, text="···", font=F["tab"], fg=C["muted"], bg=C["card"], cursor="hand2")
            more.pack(side="right")
            more.bind("<Button-1>", self.calendar_menu)

        now = datetime.now()
        events = [e for e in self.cache.get("events", []) if datetime.fromisoformat(e["end"]) > now
                  and datetime.fromisoformat(e["start"]) < now + timedelta(days=7)] if url else []
        today_left = sum(1 for e in events if datetime.fromisoformat(e["start"]).date() == now.date())
        tasks_left = sum(1 for t in self.app.data["days"].get(today_iso(), []) if not t["done"])
        brief = (f"Today: {today_left} event{'s' if today_left != 1 else ''} · " if url else "Today: ") + \
            f"{tasks_left} task{'s' if tasks_left != 1 else ''} left"
        tk.Label(card.inner, text=brief, font=F["small"], fg=C["muted"], bg=C["card"]).pack(anchor="w", pady=(2, 8))

        if not url:
            msg = tk.Label(card.inner, text="See your upcoming Outlook meetings here.", font=F["body"],
                           fg=C["text"], bg=C["card"], justify="left", anchor="w")
            msg.pack(fill="x")
            self.wraps.append((msg, "full"))
            pill(card.inner, "+ CONNECT OUTLOOK", self.connect_calendar, C, F).pack(anchor="w", pady=(10, 0))
            return card

        if self.cache.get("events_error"):
            err = tk.Label(card.inner, text="Couldn't refresh the calendar — showing the last saved events.",
                           font=F["small"], fg=C["accent_text"], bg=C["card"], justify="left", anchor="w")
            err.pack(fill="x", pady=(0, 6))
            self.wraps.append((err, "full"))
        if not events:
            tk.Label(card.inner, text="Nothing scheduled for the next week." if "events" in self.cache
                     else "Loading calendar...", font=F["body"], fg=C["muted"], bg=C["card"]).pack(anchor="w")
            return card

        shown_day, first_group = None, False
        for e in events[:5]:
            s, en = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
            d = s.date() if s > now else now.date()
            if d != shown_day:
                shown_day = d
                label = "TODAY" if d == now.date() else "TOMORROW" if d == now.date() + timedelta(days=1) \
                    else f"{d:%a} {d:%b} {d.day}".upper()
                tk.Label(card.inner, text=label, font=F["small_b"], fg=C["muted"], bg=C["card"]).pack(
                    anchor="w", pady=(6 if first_group else 0, 2))
                first_group = True
            row = tk.Frame(card.inner, bg=C["card"])
            row.pack(fill="x", pady=2)
            live = s <= now < en
            when = "All day" if e["all_day"] else ("NOW" if live else fmt_time(s, self.h24))
            tk.Label(row, text=when, font=F["small_b"], width=7, anchor="w", bg=C["card"],
                     fg=C["accent_text"] if live else C["text"]).pack(side="left", anchor="n", pady=(2, 0))
            col = tk.Frame(row, bg=C["card"])
            col.pack(side="left", fill="x", expand=True)
            t = tk.Label(col, text=e["title"], font=F["body"], fg=C["text"], bg=C["card"], anchor="w", justify="left")
            t.pack(fill="x")
            self.wraps.append((t, "event"))
            if e.get("location"):
                loc = tk.Label(col, text=e["location"], font=F["small"], fg=C["muted"], bg=C["card"],
                               anchor="w", justify="left")
                loc.pack(fill="x")
                self.wraps.append((loc, "event"))
        return card

    def tasks_card(self, parent):
        C, F = self.C, self.F
        card = Card(parent, C["bg"], C["card"])
        head = tk.Frame(card.inner, bg=C["card"], cursor="hand2")
        head.pack(fill="x")
        h = tk.Label(head, text="TODAY'S TASKS", font=F["tab"], fg=C["text"], bg=C["card"], cursor="hand2")
        h.pack(side="left")
        go = tk.Label(head, text="OPEN ›", font=F["small_b"], fg=C["muted"], bg=C["card"], cursor="hand2")
        go.pack(side="right")
        for w in (head, h, go):
            w.bind("<Button-1>", lambda e: self.app.switch("todo"))
        tasks = [t for t in self.app.data["days"].get(today_iso(), []) if not t["done"]]
        if not tasks:
            tk.Label(card.inner, text="Nothing left for today.", font=F["body"], fg=C["muted"],
                     bg=C["card"]).pack(anchor="w", pady=(8, 0))
            return card
        box = tk.Frame(card.inner, bg=C["card"])
        box.pack(fill="x", pady=(8, 0))
        for t in tasks[:6]:
            row = tk.Frame(box, bg=C["card"])
            row.pack(fill="x", pady=2)
            chk = tk.Canvas(row, width=17, height=17, bg=C["card"], highlightthickness=0, cursor="hand2")
            chk.create_rectangle(1, 1, 15, 15, outline=C["muted"], width=1.4)
            chk.pack(side="left", anchor="n", pady=(3, 0), padx=(0, 9))
            chk.bind("<Button-1>", lambda e, task=t: self.finish_task(task))
            sub = f"  ({sum(1 for c in t.get('children', []) if c['done'])}/{len(t['children'])})" \
                if t.get("children") else ""
            lbl = tk.Label(row, text=t["text"] + sub, font=F["body"], fg=C["text"], bg=C["card"],
                           anchor="w", justify="left")
            lbl.pack(side="left", fill="x", expand=True)
            self.wraps.append((lbl, "task"))
        if len(tasks) > 6:
            tk.Label(card.inner, text=f"+ {len(tasks) - 6} more", font=F["small"], fg=C["muted"],
                     bg=C["card"]).pack(anchor="w", pady=(4, 0))
        return card

    def on_width(self, width):
        self.width = width
        avail = max(150, width - 2 * PAD - (44 if not self.h24 else 0))
        sample = "00:00:00"
        size = int(100 * avail / max(1, self.measure.measure(sample)))
        self.F["clock"].configure(size=max(28, min(90, size)))
        inner = width - 2 * PAD - 2 * CARD_PAD
        self.wraps = [(l, k) for l, k in self.wraps if l.winfo_exists()]
        for lbl, kind in self.wraps:
            try:
                wl = {"full": inner, "event": inner - 70, "task": inner - 30,
                      "half": (width - 2 * PAD - GAP) // 2 - 2 * CARD_PAD - 24}[kind]
                lbl.config(wraplength=max(60, wl))
            except tk.TclError:
                pass

    # ---- calendar ------------------------------------------------------------------

    def calendar_card(self, parent):
        card = Card(parent, self.C["bg"], self.C["card"])
        self.cal_box = card.inner
        self.render_calendar()
        return card

    def events_on(self, d):
        if not self.settings.get("ics_url"):
            return []
        out = []
        for e in self.cache.get("events", []):
            s, en = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
            if s.date() == d or s.date() < d < en.date() or (s.date() < d == en.date() and en.time() != datetime.min.time()):
                out.append(e)
        return out

    def busy_days(self, y, m):
        busy = set()
        for iso, tasks in self.app.data["days"].items():
            if iso[:7] == f"{y:04d}-{m:02d}" and any(not t["done"] for t in tasks):
                busy.add(int(iso[8:10]))
        for e in self.cache.get("events", []) if self.settings.get("ics_url") else []:
            s = datetime.fromisoformat(e["start"])
            if (s.year, s.month) == (y, m):
                busy.add(s.day)
        return busy

    def render_calendar(self):
        box, C, F = self.cal_box, self.C, self.F
        fill = C["card"]
        for w in box.winfo_children():
            w.destroy()
        today = date.today()
        y, m = self.cal_month
        current = (y, m) == (today.year, today.month)

        head = tk.Frame(box, bg=fill)
        head.pack(fill="x")
        left = tk.Frame(head, bg=fill)
        left.pack(side="left")
        col = C["accent_text"] if current else C["text"]
        tk.Label(left, text=date(y, m, 1).strftime("%b"), font=F["month"], fg=col, bg=fill,
                 bd=0, pady=0).pack(anchor="w")
        tk.Label(left, text=str(y), font=F["year"], fg=col, bg=fill).pack(anchor="w")
        nav = tk.Frame(head, bg=fill)
        nav.pack(side="right", anchor="n", pady=(6, 0))
        for txt, delta in (("›", 1), ("‹", -1)):
            b = tk.Label(nav, text=txt, font=F["title"], fg=C["muted"], bg=fill, cursor="hand2", padx=7)
            b.pack(side="right")
            b.bind("<Button-1>", lambda e, d=delta: self.shift_month(d))
        pill(nav, "TODAY", self.cal_today, C, F, primary=False, bg=fill).pack(side="right", padx=(0, 6))

        tk.Frame(box, height=1, bg=C["line"]).pack(fill="x", pady=(10, 8))
        grid = tk.Frame(box, bg=fill)
        grid.pack(fill="x")
        for c in range(7):
            grid.columnconfigure(c, weight=1, uniform="cal")
        for c, letter in enumerate("MTWTFSS"):
            tk.Label(grid, text=letter, font=F["small_b"], fg=C["muted"], bg=fill, anchor="w").grid(
                row=0, column=c, sticky="w", padx=(7, 0), pady=(0, 2))
        first = date(y, m, 1)
        busy = self.busy_days(y, m)
        swipe_targets = [grid, box]
        for i in range(days_in_month(y, m)):
            d = first + timedelta(days=i)
            r, c = divmod(first.weekday() + i, 7)
            cell = tk.Canvas(grid, height=38, width=10, bg=fill, highlightthickness=0, cursor="hand2")
            cell.grid(row=r + 1, column=c, sticky="ew")
            cell.bind("<Configure>", lambda e, cv=cell, dd=d: self.draw_cell(cv, dd, dd.day in busy))
            cell.bind("<ButtonPress-1>", self._swipe_start)
            cell.bind("<ButtonRelease-1>", lambda e, dd=d: self._swipe_end(e, dd))
        for w in swipe_targets:
            w.bind("<ButtonPress-1>", self._swipe_start)
            w.bind("<ButtonRelease-1>", lambda e: self._swipe_end(e, None))

        tk.Frame(box, height=1, bg=C["line"]).pack(fill="x", pady=(8, 10))
        self.render_day_detail(box)
        self.on_width(self.width)

    def draw_cell(self, cv, d, busy):
        C, F = self.C, self.F
        cv.delete("all")
        w = cv.winfo_width()
        selected, is_today = d == self.cal_sel, d == date.today()
        fg = C["text"]
        if selected:
            round_rect(cv, 1, 2, min(w - 3, 44), 33, 10, fill=C["accent"], outline="")
            fg = C["on_accent"]
        elif is_today:
            fg = C["accent_text"]
        cv.create_text(8, 18, text=str(d.day), anchor="w", font=F["cal"], fill=fg)
        if busy:
            x = 8 + F["cal"].measure(str(d.day)) / 2
            cv.create_oval(x - 2, 29, x + 2, 33, fill=fg if selected else C["muted"], outline="")

    def _swipe_start(self, e):
        self._swipe_x = e.x_root

    def _swipe_end(self, e, d):
        dx = e.x_root - getattr(self, "_swipe_x", e.x_root)
        if dx > 40:
            self.shift_month(-1)   # drag right -> previous month
        elif dx < -40:
            self.shift_month(1)    # drag left -> next month
        elif d is not None:
            self.cal_sel = d
            self.render_calendar()

    def shift_month(self, delta):
        self.cal_month = add_months(*self.cal_month, delta)
        self.render_calendar()

    def cal_today(self):
        t = date.today()
        self.cal_month, self.cal_sel = (t.year, t.month), t
        self.render_calendar()

    def render_day_detail(self, box):
        C, F = self.C, self.F
        fill = C["card"]
        d = self.cal_sel
        label = f"{d:%A}, {d:%B} {d.day}".upper()
        if d == date.today():
            label += "  ·  TODAY"
        tk.Label(box, text=label, font=F["small_b"], fg=C["muted"], bg=fill).pack(anchor="w", pady=(0, 4))
        events = self.events_on(d)
        tasks = self.app.data["days"].get(d.isoformat(), [])
        for e in events:
            row = tk.Frame(box, bg=fill)
            row.pack(fill="x", pady=1)
            s = datetime.fromisoformat(e["start"])
            when = "All day" if e["all_day"] or s.date() != d else fmt_time(s, self.h24)
            tk.Label(row, text=when, font=F["small_b"], width=7, anchor="w", fg=C["text"], bg=fill).pack(
                side="left", anchor="n", pady=(2, 0))
            t = tk.Label(row, text=e["title"], font=F["body"], fg=C["text"], bg=fill, anchor="w", justify="left")
            t.pack(side="left", fill="x", expand=True)
            self.wraps.append((t, "event"))
        for task in tasks:
            row = tk.Frame(box, bg=fill)
            row.pack(fill="x", pady=1)
            chk = tk.Canvas(row, width=15, height=15, bg=fill, highlightthickness=0, cursor="hand2")
            if task["done"]:
                chk.create_rectangle(1, 1, 13, 13, fill=C["accent"], outline=C["accent"])
                chk.create_line(3.5, 7, 6, 9.8, 10.5, 4, fill=C["check"], width=2)
            else:
                chk.create_rectangle(1, 1, 13, 13, outline=C["muted"], width=1.4)
            chk.pack(side="left", anchor="n", pady=(3, 0), padx=(0, 8))
            chk.bind("<Button-1>", lambda e, t=task: self.toggle_task(t))
            t = tk.Label(row, text=task["text"], font=F["body_done"] if task["done"] else F["body"],
                         fg=C["muted"] if task["done"] else C["text"], bg=fill, anchor="w", justify="left")
            t.pack(side="left", fill="x", expand=True)
            self.wraps.append((t, "task"))
        if not events and not tasks:
            tk.Label(box, text="Nothing planned.", font=F["body"], fg=C["muted"], bg=fill).pack(anchor="w")
        add = PlaceholderEntry(box, "Add a task for this day...", C, font=F["body"], bg=fill)
        add.pack(fill="x", pady=(8, 0))

        def add_task(_e=None):
            text = add.value().strip()
            if text:
                self.app.data["days"].setdefault(d.isoformat(), []).append(
                    {"id": new_id(), "text": text, "done": False, "children": []})
                self.app.persist()
                self.build()
        add.bind("<Return>", add_task)

    def toggle_task(self, task):
        task["done"] = not task["done"]
        if task["done"]:
            for c in task.get("children", []):
                c["done"] = True
        self.app.persist()
        self.build()

    # ---- clock -----------------------------------------------------------------

    def tick(self):
        if not self.alive():
            return
        self.update_clock()
        self.root.after(1000 - datetime.now().microsecond // 1000 + 5, self.tick)

    def update_clock(self):
        now = datetime.now()
        self.clock_lbl.config(text=now.strftime("%H:%M:%S" if self.h24 else "%I:%M:%S"))
        self.ampm_lbl.config(text="" if self.h24 else now.strftime("%p"))
        self.date_lbl.config(text=f"{now:%A}, {now:%B} {now.day}".upper())
        w = self.cache["weather"].get(city_key(self.settings["cities"][0])) if self.settings["cities"] else None
        if w and w.get("sunrise"):
            try:
                sr, ss = datetime.fromisoformat(w["sunrise"]), datetime.fromisoformat(w["sunset"])
                mins = int((ss - sr).total_seconds() // 60)
                self.sun_lbl.config(text=f"Sun  {fmt_time(sr, self.h24)} – {fmt_time(ss, self.h24)}"
                                         f"  ({mins // 60}h {mins % 60:02d}m)")
            except ValueError:
                pass

    def set_24(self, v):
        self.settings["clock24"] = v
        self.app.persist()
        self.build()

    # ---- data refresh ------------------------------------------------------------

    def refresh(self, force=False):
        if not self.alive():
            return
        now = datetime.now()

        def stale(stamp, minutes):
            return force or not stamp or now - datetime.fromisoformat(stamp) > timedelta(minutes=minutes)

        for city in self.settings["cities"][:2]:
            k = city_key(city)
            if stale(self.cache["weather"].get(k, {}).get("fetched"), 15):
                self.app.run_bg(lambda c=city: fetch_weather(c["lat"], c["lon"]),
                                lambda res, err, k=k: self.got_weather(k, res, err))
        url = self.settings.get("ics_url")
        if url and stale(self.cache.get("events_fetched"), 10):
            self.app.run_bg(lambda: fetch_events(url), self.got_events)
        self.root.after(5 * 60 * 1000, self.refresh)

    def got_weather(self, key, res, err):
        if err is None:
            self.cache["weather"][key] = res
            self.cache.pop("weather_error", None)
        else:
            self.cache["weather_error"] = str(err)
        self.app.persist()
        if self.alive():
            self.build()

    def got_events(self, res, err):
        if err is None:
            self.cache["events"] = res
            self.cache.pop("events_error", None)
        else:
            self.cache["events_error"] = str(err)
        self.cache["events_fetched"] = datetime.now().isoformat(timespec="seconds")
        self.app.persist()
        if self.alive():
            self.build()

    def finish_task(self, task):
        task["done"] = True
        for c in task.get("children", []):
            c["done"] = True
        self.app.persist()
        self.build()

    # ---- menus & dialogs -----------------------------------------------------------

    def city_menu(self, e, i):
        units = self.settings.get("units", "F")
        items = [("Change city...", lambda: self.change_city(i)),
                 (f"Show °{'C' if units == 'F' else 'F'}", self.toggle_units),
                 (None, None), ("Refresh weather", lambda: self.refresh(force=True))]
        menu(self.root, self.C, items).tk_popup(e.x_root, e.y_root)

    def toggle_units(self):
        self.settings["units"] = "C" if self.settings.get("units", "F") == "F" else "F"
        self.app.persist()
        self.build()

    def change_city(self, i):
        C, F = self.C, self.F
        d, body = self.app.dialog("Change city")
        tk.Label(body, text="Type a town or city, e.g. “Aspen, CO”", font=F["small"],
                 fg=C["muted"], bg=C["bg"]).pack(anchor="w")
        field = Card(body, C["bg"], C["card"], pad=10, radius=12)
        field.pack(fill="x", pady=(6, 8))
        entry = tk.Entry(field.inner, font=F["body"], bg=C["card"], fg=C["text"], insertbackground=C["text"],
                         relief="flat", bd=0, highlightthickness=0)
        entry.pack(fill="x")
        status = tk.Label(body, font=F["small"], fg=C["muted"], bg=C["bg"])
        status.pack(anchor="w")
        results = tk.Frame(body, bg=C["bg"])
        results.pack(fill="x", pady=(4, 0))

        def pick(place):
            self.settings["cities"][i] = {k: place[k] for k in ("name", "region", "lat", "lon")}
            self.app.persist()
            d.destroy()
            self.build()
            self.refresh(force=True)

        def show(res, err):
            if not d.winfo_exists():
                return
            for w in results.winfo_children():
                w.destroy()
            if err:
                status.config(text="Couldn't search. Are you online?")
                return
            if not res:
                status.config(text="No places found. Try another spelling.")
                return
            status.config(text="Choose one:")
            for place in res[:6]:
                where = ", ".join(x for x in (place["region"], place["country"]) if x and x != place["name"])
                lbl = tk.Label(results, text=f"{place['name']}  ·  {where}", font=F["body"], fg=C["text"],
                               bg=C["bg"], anchor="w", cursor="hand2", pady=3)
                lbl.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, p=place: pick(p))
                lbl.bind("<Enter>", lambda e, w=lbl: w.config(fg=C["accent_text"]))
                lbl.bind("<Leave>", lambda e, w=lbl: w.config(fg=C["text"]))

        def search():
            q = entry.get().strip()
            if q:
                status.config(text="Searching...")
                self.app.run_bg(lambda: geocode(q), show)

        entry.bind("<Return>", lambda e: search())
        d.search, d.entry = search, entry
        btns = tk.Frame(body, bg=C["bg"])
        btns.pack(fill="x", pady=(12, 0))
        pill(btns, "SEARCH", search, C, F).pack(side="left")
        pill(btns, "CANCEL", d.destroy, C, F, primary=False).pack(side="left", padx=(8, 0))
        entry.focus_set()

    def calendar_menu(self, e):
        items = [("Refresh calendar", lambda: self.refresh(force=True)),
                 ("Change calendar link...", self.connect_calendar),
                 (None, None), ("Disconnect calendar", self.disconnect_calendar)]
        menu(self.root, self.C, items).tk_popup(e.x_root, e.y_root)

    def disconnect_calendar(self):
        self.settings.pop("ics_url", None)
        for k in ("events", "events_fetched", "events_error"):
            self.cache.pop(k, None)
        self.app.persist()
        self.build()

    def connect_calendar(self):
        C, F = self.C, self.F
        d, body = self.app.dialog("Connect Outlook calendar", width=380)

        def text(t, color=None, font=None, pady=(0, 6)):
            lbl = tk.Label(body, text=t, font=font or F["small"], fg=color or C["text"], bg=C["bg"],
                           justify="left", anchor="w", wraplength=330)
            lbl.pack(fill="x", pady=pady)
            return lbl

        def link(t, url):
            lbl = tk.Label(body, text=t + "  ↗", font=F["small_b"], fg=C["accent_text"], bg=C["bg"],
                           cursor="hand2", anchor="w")
            lbl.pack(fill="x", pady=(0, 4))
            lbl.bind("<Button-1>", lambda e: webbrowser.open(url))

        text("1.  Open your Outlook calendar settings in the browser:")
        link("Work or school account", "https://outlook.office.com/calendar/options/calendar/SharedCalendars")
        link("Personal account (Outlook.com / Hotmail)",
             "https://outlook.live.com/calendar/0/options/calendar/SharedCalendars")
        text("2.  Under “Publish a calendar”, choose your calendar and “Can view all details”, "
             "then click Publish.", pady=(6, 6))
        text("3.  Copy the ICS link and paste it here:")
        field = Card(body, C["bg"], C["card"], pad=10, radius=12)
        field.pack(fill="x", pady=(2, 6))
        entry = tk.Entry(field.inner, font=F["small"], bg=C["card"], fg=C["text"], insertbackground=C["text"],
                         relief="flat", bd=0, highlightthickness=0)
        entry.pack(fill="x")
        entry.insert(0, self.settings.get("ics_url", ""))
        status = text("", color=C["muted"])
        text("The link is saved only on this PC. Anyone who has it can see your calendar, so keep it private.",
             color=C["muted"], pady=(2, 0))

        def done(res, err):
            if not d.winfo_exists():
                return
            if err:
                status.config(text=f"That didn't work: {err}", fg=C["accent_text"])
                return
            self.settings["ics_url"] = entry.get().strip()
            self.cache["events"] = res
            self.cache["events_fetched"] = datetime.now().isoformat(timespec="seconds")
            self.cache.pop("events_error", None)
            self.app.persist()
            d.destroy()
            if self.alive():
                self.build()

        def save():
            url = entry.get().strip()
            if not url.lower().startswith(("https://", "http://", "webcal://")):
                status.config(text="Paste the full link (it starts with https://).", fg=C["accent_text"])
                return
            status.config(text="Checking the link...", fg=C["muted"])
            self.app.run_bg(lambda: fetch_events(url), done)

        btns = tk.Frame(body, bg=C["bg"])
        btns.pack(fill="x", pady=(12, 0))
        pill(btns, "CONNECT", save, C, F).pack(side="left")
        pill(btns, "CANCEL", d.destroy, C, F, primary=False).pack(side="left", padx=(8, 0))
        entry.bind("<Return>", lambda e: save())
        entry.focus_set()


# =========================================================================== notes tab


class NotesView:
    def __init__(self, app, parent):
        self.app, self.C, self.F = app, app.C, app.F
        self.root = app.root
        self.parent = parent
        self.note = None
        self.scroll = None
        self.text = None
        self._save_job = None
        open_id = app.settings.get("open_note")
        note = next((n for n in app.data["notes"] if n["id"] == open_id), None)
        self.open(note) if note else self.show_list()

    def clear(self):
        for w in self.parent.winfo_children():
            w.destroy()
        self.scroll = self.text = None

    # ---- list ------------------------------------------------------------------

    def show_list(self):
        self.flush()
        self.note = None
        self.app.settings["open_note"] = None
        self.clear()
        C, F = self.C, self.F

        head = tk.Frame(self.parent, bg=C["bg"])
        head.pack(fill="x", padx=PAD, pady=(16, GAP + 2))
        tk.Label(head, text="NOTES", font=F["day"], fg=C["text"], bg=C["bg"]).pack(side="left")
        pill(head, "+ NEW", self.new_note, C, F).pack(side="right")

        self.scroll = ScrollArea(self.parent, C, on_width=self.rewrap)
        self.scroll.pack(fill="both", expand=True)
        self.previews = []
        notes = sorted(self.app.data["notes"], key=lambda n: n.get("updated", ""), reverse=True)
        if not notes:
            tk.Label(self.scroll.inner, text="No notes yet.\nClick + NEW to write one.", font=F["body"],
                     fg=C["faint"], bg=C["bg"], justify="center").pack(pady=50)
        for n in notes:
            self.render_card(n)
        tk.Frame(self.scroll.inner, height=PAD, bg=C["bg"]).pack(fill="x")

    def rewrap(self, width):
        for lbl in getattr(self, "previews", []):
            try:
                lbl.config(wraplength=max(80, width - 2 * PAD - 2 * CARD_PAD))
            except tk.TclError:
                pass

    def render_card(self, n):
        C, F = self.C, self.F
        card = Card(self.scroll.inner, C["bg"], C["card"], cursor="hand2")
        card.pack(fill="x", padx=PAD, pady=(0, GAP))
        fill = C["card"]
        top = tk.Frame(card.inner, bg=fill, cursor="hand2")
        top.pack(fill="x")
        title = tk.Label(top, text=n.get("title") or "Untitled", font=F["note_title"], fg=C["text"],
                         bg=fill, anchor="w", cursor="hand2")
        title.pack(side="left")
        dele = tk.Label(top, text="\u00d7", font=F["icon"], fg=fill, bg=fill, cursor="hand2")
        dele.pack(side="right")
        when = tk.Label(top, text=self.when(n.get("updated")), font=F["small"], fg=C["muted"], bg=fill)
        when.pack(side="right", padx=6)
        plain = " ".join("".join(r[0] for r in n.get("content", [])).replace(BULLET, "").split())
        if len(plain) > 110:
            plain = plain[:108].rstrip() + "\u2026"
        prev = tk.Label(card.inner, text=plain or "Empty note", font=F["small"], cursor="hand2",
                        fg=C["muted"], bg=fill, anchor="w", justify="left")
        prev.pack(fill="x", pady=(4, 0))
        self.previews.append(prev)
        for w in (card, card.inner, top, title, when, prev):
            w.bind("<Button-1>", lambda e: self.open(n))
        dele.bind("<Button-1>", lambda e: self.delete(n))
        bind_hover(card, lambda: dele.config(fg=C["muted"]), lambda: dele.config(fg=fill))

    @staticmethod
    def when(stamp):
        if not stamp:
            return ""
        d = datetime.fromisoformat(stamp)
        if d.date() == date.today():
            return d.strftime("%I:%M %p").lstrip("0").lower()
        return f"{d:%b} {d.day}"

    def new_note(self):
        n = {"id": new_id(), "title": "", "content": [], "updated": datetime.now().isoformat(timespec="seconds")}
        self.app.data["notes"].append(n)
        self.app.persist()
        self.open(n, focus_title=True)

    def delete(self, n):
        name = n.get("title") or "this note"
        if messagebox.askyesno(APP_NAME, f"Delete “{name}”?", parent=self.root):
            self.app.data["notes"].remove(n)
            self.app.persist()
            self.show_list()

    # ---- editor ----------------------------------------------------------------

    def open(self, n, focus_title=False):
        self.flush()
        self.note = n
        self.app.settings["open_note"] = n["id"]
        self.clear()
        C, F = self.C, self.F

        bar = tk.Frame(self.parent, bg=C["bg"])
        bar.pack(fill="x", padx=22, pady=(16, 6))
        back = tk.Label(bar, text="‹  ALL NOTES", font=F["small_b"], fg=C["muted"], bg=C["bg"], cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda e: self.show_list())

        self.tools = {}
        for key, label, fnt, tip in (("bullet", "• ≡", F["small_b"], "Bullet list"),
                                     ("h", "H", F["small_b"], "Heading"),
                                     ("b", "B", F["small_b"], "Bold (Ctrl+B)")):
            btn = tk.Label(bar, text=label, font=fnt, width=3, pady=2, cursor="hand2", bg=C["chip"], fg=C["text"])
            btn.pack(side="right", padx=(4, 0))
            btn.bind("<Button-1>", lambda e, k=key: self.tool(k))
            self.tools[key] = btn

        self.title = PlaceholderEntry(self.parent, "Title", C, font=F["title"], bg=C["bg"])
        self.title.pack(fill="x", padx=22, pady=(10, 4))
        if n.get("title"):
            self.title._focus_in()
            self.title.insert(0, n["title"])
        self.title.bind("<KeyRelease>", lambda e: self.schedule_save())
        self.title.bind("<Return>", lambda e: self.text.focus_set())
        tk.Frame(self.parent, height=1, bg=C["line"]).pack(fill="x", padx=22, pady=(0, 8))

        wrap = tk.Frame(self.parent, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=(22, 6), pady=(0, 14))
        sb = tk.Scrollbar(wrap, width=8)
        t = self.text = tk.Text(wrap, wrap="word", font=F["body"], bg=C["bg"], fg=C["text"],
                                insertbackground=C["text"], relief="flat", bd=0, highlightthickness=0,
                                selectbackground=C["sel"], selectforeground=C["text"], inactiveselectbackground=C["sel"],
                                padx=0, pady=4, spacing1=2, spacing3=2, undo=True, yscrollcommand=sb.set)
        sb.config(command=t.yview)
        t.pack(side="left", fill="both", expand=True)

        indent = F["body"].measure(BULLET)
        t.tag_configure("h", font=F["h"], spacing1=8, spacing3=4)
        t.tag_configure("b", font=F["bold"])
        t.tag_configure("bullet", lmargin1=6, lmargin2=6 + indent)
        t.tag_raise("b")

        for run in n.get("content", []):
            t.insert("end", run[0], tuple(run[1]))
        t.edit_reset()
        t.edit_modified(False)
        self.bold_mode = False

        t.bind("<<Modified>>", self.on_modified)
        t.bind("<Return>", self.on_return)
        t.bind("<BackSpace>", self.on_backspace)
        t.bind("<KeyPress>", self.on_key, add="+")
        t.bind("<KeyRelease>", self.on_nav, add="+")
        t.bind("<ButtonRelease-1>", self.on_nav, add="+")
        for seq in ("<Control-b>", "<Control-B>"):
            t.bind(seq, lambda e: (self.tool("b"), "break")[1])

        (self.title if focus_title else t).focus_set()
        if not focus_title:
            t.mark_set("insert", "end-1c")
        self.update_tools()

    # formatting -------------------------------------------------------------

    def line_range(self, idx):
        return self.text.index(f"{idx} linestart"), self.text.index(f"{idx} lineend +1c")

    def selected_lines(self):
        t = self.text
        if t.tag_ranges("sel"):
            a, b = int(t.index("sel.first").split(".")[0]), int(t.index("sel.last -1c").split(".")[0])
        else:
            a = b = int(t.index("insert").split(".")[0])
        return list(range(a, b + 1))

    def tool(self, key):
        t = self.text
        if key == "b":
            if t.tag_ranges("sel"):
                start, end = t.index("sel.first"), t.index("sel.last")
                n = len(t.get(start, end))
                all_bold = all("b" in t.tag_names(f"{start} +{i}c") for i in range(n))
                (t.tag_remove if all_bold else t.tag_add)("b", start, end)
                self.bold_mode = not all_bold
            else:
                self.bold_mode = not self.bold_mode
        elif key == "bullet":
            lines = self.selected_lines()
            all_b = all(t.get(f"{ln}.0", f"{ln}.{len(BULLET)}") == BULLET for ln in lines)
            for ln in lines:
                if all_b:
                    self.remove_bullet(ln)
                elif t.get(f"{ln}.0", f"{ln}.{len(BULLET)}") != BULLET:
                    t.insert(f"{ln}.0", BULLET)
                    t.tag_remove("b", f"{ln}.0", f"{ln}.{len(BULLET)}")
                    t.tag_remove("h", *self.line_range(f"{ln}.0"))
                    t.tag_add("bullet", *self.line_range(f"{ln}.0"))
        elif key == "h":
            lines = self.selected_lines()
            all_h = all("h" in t.tag_names(f"{ln}.0") for ln in lines)
            for ln in lines:
                rng = self.line_range(f"{ln}.0")
                if all_h:
                    t.tag_remove("h", *rng)
                else:
                    if t.get(f"{ln}.0", f"{ln}.{len(BULLET)}") == BULLET:
                        self.remove_bullet(ln)
                        rng = self.line_range(f"{ln}.0")
                    t.tag_add("h", *rng)
        t.focus_set()
        self.schedule_save()
        self.update_tools()

    def remove_bullet(self, ln):
        t = self.text
        if t.get(f"{ln}.0", f"{ln}.{len(BULLET)}") == BULLET:
            t.delete(f"{ln}.0", f"{ln}.{len(BULLET)}")
        t.tag_remove("bullet", *self.line_range(f"{ln}.0"))

    def is_bullet_line(self, idx="insert"):
        t = self.text
        ls = t.index(f"{idx} linestart")
        return t.get(ls, f"{ls} +{len(BULLET)}c") == BULLET

    def on_return(self, _e):
        t = self.text
        ls = t.index("insert linestart")
        line = t.get(ls, f"{ls} lineend")
        bullet = line.startswith(BULLET)
        if bullet and not line[len(BULLET):].strip():
            self.remove_bullet(int(ls.split(".")[0]))  # Enter on an empty bullet ends the list
            self.schedule_save()
            self.update_tools()
            return "break"
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        t.insert("insert", "\n")
        nls = t.index("insert linestart")
        rng = (nls, t.index(f"{nls} lineend +1c"))
        t.tag_remove("bullet", *rng)
        if not t.get(nls, f"{nls} lineend"):
            t.tag_remove("h", *rng)  # a heading doesn't carry on to the next line
        if bullet:
            t.insert(nls, BULLET)
            t.tag_remove("b", nls, f"{nls} +{len(BULLET)}c")
            t.tag_add("bullet", nls, t.index(f"{nls} lineend +1c"))
        t.see("insert")
        self.schedule_save()
        self.update_tools()
        return "break"

    def on_backspace(self, _e):
        t = self.text
        if not t.tag_ranges("sel") and self.is_bullet_line():
            col = int(t.index("insert").split(".")[1])
            if col == len(BULLET):
                self.remove_bullet(int(t.index("insert").split(".")[0]))
                self.schedule_save()
                self.update_tools()
                return "break"
        return None

    def on_key(self, e):
        if e.char and len(e.char) == 1 and ord(e.char) >= 32 and not (e.state & 0x4):
            bold = self.bold_mode

            def fix():
                if self.text is None:
                    return
                (self.text.tag_add if bold else self.text.tag_remove)("b", "insert -1c", "insert")
            self.root.after_idle(fix)

    def on_nav(self, e):
        nav_keys = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next"}
        if e.type == tk.EventType.ButtonRelease or getattr(e, "keysym", "") in nav_keys:
            t = self.text
            probe = "insert -1c" if t.index("insert") != t.index("insert linestart") else "insert"
            self.bold_mode = "b" in t.tag_names(probe)
        self.update_tools()

    def update_tools(self):
        if not self.text:
            return
        C = self.C
        state = {"b": self.bold_mode, "bullet": self.is_bullet_line(),
                 "h": "h" in self.text.tag_names("insert linestart")}
        for k, btn in self.tools.items():
            btn.config(bg=C["accent"] if state[k] else C["chip"], fg=C["on_accent"] if state[k] else C["text"])

    # saving -----------------------------------------------------------------

    def on_modified(self, _e):
        if self.text and self.text.edit_modified():
            self.text.edit_modified(False)
            self.schedule_save()

    def schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self.flush)

    def serialize(self):
        runs, active, buf = [], set(), []
        t = self.text

        def push():
            if buf:
                text = "".join(buf)
                tags = sorted(active)
                if runs and runs[-1][1] == tags:
                    runs[-1][0] += text
                else:
                    runs.append([text, tags])
                buf.clear()
        for kind, value, _ in t.dump("1.0", "end-1c", text=True, tag=True):
            if kind == "text":
                buf.append(value)
            elif value in ("b", "h", "bullet"):
                push()
                (active.add if kind == "tagon" else active.discard)(value)
        push()
        return runs

    def flush(self):
        if self._save_job:
            try:
                self.root.after_cancel(self._save_job)
            except tk.TclError:
                pass
            self._save_job = None
        if not self.note or not self.text:
            return
        try:
            content = self.serialize()
            title = self.title.value().strip()
        except tk.TclError:
            return
        if content != self.note.get("content") or title != self.note.get("title"):
            self.note["content"] = content
            self.note["title"] = title
            self.note["updated"] = datetime.now().isoformat(timespec="seconds")
            self.app.persist()


# =========================================================================== start


def sample_ics(today):
    """A small Outlook-style calendar used by --selftest."""
    mon = today - timedelta(days=today.weekday())
    d = lambda x: x.strftime("%Y%m%d")
    t1 = today + timedelta(days=1)
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:Microsoft Exchange Server 2010",
        "BEGIN:VTIMEZONE", "TZID:Mountain Standard Time", "END:VTIMEZONE",
        # every weekday 9:00, but not tomorrow (EXDATE)
        "BEGIN:VEVENT", "UID:standup", "SUMMARY:Team stand-up", "LOCATION:Teams",
        f"DTSTART;TZID=Mountain Standard Time:{d(mon - timedelta(weeks=2))}T090000",
        f"DTEND;TZID=Mountain Standard Time:{d(mon - timedelta(weeks=2))}T091500",
        "RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,TU,WE,TH,FR,SA,SU;WKST=SU",
        f"EXDATE;TZID=Mountain Standard Time:{d(t1)}T090000", "END:VEVENT",
        # a moved occurrence of the stand-up: today at 10:30 instead of 9:00
        "BEGIN:VEVENT", "UID:standup", "SUMMARY:Team stand-up (moved)",
        f"RECURRENCE-ID;TZID=Mountain Standard Time:{d(today)}T090000",
        f"DTSTART;TZID=Mountain Standard Time:{d(today)}T103000",
        f"DTEND;TZID=Mountain Standard Time:{d(today)}T104500", "END:VEVENT",
        "BEGIN:VEVENT", "UID:allday", "SUMMARY:Office closed", f"DTSTART;VALUE=DATE:{d(t1)}",
        f"DTEND;VALUE=DATE:{d(t1 + timedelta(days=1))}", "END:VEVENT",
        "BEGIN:VEVENT", "UID:gone", "SUMMARY:Canceled: Old meeting", "STATUS:CANCELLED",
        f"DTSTART:{d(t1)}T180000Z", f"DTEND:{d(t1)}T190000Z", "END:VEVENT",
        "BEGIN:VEVENT", "UID:monthly", "SUMMARY:Monthly review\\, Q&A",
        f"DTSTART;TZID=Mountain Standard Time:{d(today.replace(day=1) - timedelta(days=60))}T140000",
        "DURATION:PT1H", "RRULE:FREQ=MONTHLY;BYDAY=1MO,3MO", "BEGIN:VALARM", "TRIGGER:-PT15M",
        "END:VALARM", "END:VEVENT",
        "END:VCALENDAR", ""])


def selftest():
    """python desktodo.pyw --selftest : checks weather, city search and calendar parsing."""
    ok = True
    today = date.today()
    events = parse_ics(sample_ics(today), datetime.combine(today, datetime.min.time()),
                       datetime.combine(today + timedelta(days=8), datetime.min.time()))
    for e in events:
        print("event:", e["start"], e["title"], "| all day" if e["all_day"] else "")
    titles = [e["title"] for e in events]
    checks = {
        "moved occurrence replaces today's 9:00": titles.count("Team stand-up (moved)") == 1
        and not any(e["title"] == "Team stand-up" and e["start"].startswith(today.isoformat()) for e in events),
        "EXDATE skips tomorrow": not any(e["title"] == "Team stand-up"
                                         and e["start"].startswith((today + timedelta(days=1)).isoformat())
                                         for e in events),
        "recurring weekly expands": titles.count("Team stand-up") >= 5,
        "cancelled hidden": not any("Old meeting" in t for t in titles),
        "all-day event": "Office closed" in titles,
        "text unescaped": all("\\" not in t for t in titles),
    }
    for name, passed in checks.items():
        print(("PASS " if passed else "FAIL ") + name)
        ok &= passed
    try:
        places = geocode("Basalt, CO")
        print("geocode:", places[0])
        ok &= places[0]["region"] == "Colorado"
        for c in DEFAULT_CITIES:
            w = fetch_weather(c["lat"], c["lon"])
            print("weather:", c["name"], w)
    except Exception as exc:
        print("FAIL network:", exc)
        ok = False
    print("SELFTEST", "OK" if ok else "FAILED")
    return ok


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
