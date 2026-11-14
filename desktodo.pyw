"""
DeskTodo - a weekly to-do list and notes app for your Windows desktop.

Pure Python standard library (tkinter). No internet, no accounts.
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

Anywhere
  Ctrl+1 / Ctrl+2              switch to To-do / Notes
  Ctrl+T                       keep window on top
"""

import json
import os
import sys
import tkinter as tk
import uuid
from datetime import date, datetime, timedelta
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
    "light": {
        "bg": "#e8e8e8", "text": "#3a3a3a", "muted": "#8d8d8d", "faint": "#b3b3b3",
        "line": "#cfcfcf", "accent": "#f2551d", "check": "#ffffff", "field": "#e8e8e8",
        "chip": "#d9d9d9", "sel": "#f7c3ae",
    },
    "dark": {
        "bg": "#3c3c3c", "text": "#f1f1f1", "muted": "#a6a6a6", "faint": "#777777",
        "line": "#545454", "accent": "#f2551d", "check": "#ffffff", "field": "#3c3c3c",
        "chip": "#4b4b4b", "sel": "#7a3a22",
    },
}


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
        heavy_w = "normal" if heavy != "Barlow" else "bold"
        semi_w = "normal" if semi != "Barlow" else "bold"
    elif "Bahnschrift" in fams:
        body = "Bahnschrift"
        heavy = "Bahnschrift SemiBold" if "Bahnschrift SemiBold" in fams else "Bahnschrift"
        semi, heavy_w, semi_w = heavy, "bold", "normal"
    else:
        body = heavy = semi = "Segoe UI"
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
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)
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
                activebackground=colors["accent"], activeforeground="#ffffff")
    for label, cmd in items:
        if label is None:
            m.add_separator()
        else:
            m.add_command(label="  " + label + "    ", command=cmd)
    return m


# =========================================================================== app


class App:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.settings = self.data["settings"]
        roll_over(self.data)
        self.today = today_iso()

        self.F = setup_fonts(root)
        self.tab = self.settings.get("tab", "todo")
        self.view = None

        root.title(APP_NAME)
        root.minsize(320, 420)
        root.geometry(self.settings.get("geometry", "400x720"))
        root.attributes("-topmost", bool(self.settings.get("on_top", False)))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        root.bind_all("<MouseWheel>", self._wheel)
        root.bind_all("<Button-4>", lambda e: self._wheel(e, -1))
        root.bind_all("<Button-5>", lambda e: self._wheel(e, 1))
        root.bind("<Control-t>", lambda e: self.toggle_on_top())
        root.bind("<Control-Key-1>", lambda e: self.switch("todo"))
        root.bind("<Control-Key-2>", lambda e: self.switch("notes"))

        self.build()
        self.persist()
        self.root.after(60_000, self._tick)

    @property
    def C(self):
        return THEMES[self.settings.get("theme", "light")]

    # ---- shell -----------------------------------------------------------------

    def build(self):
        for w in self.root.winfo_children():
            w.destroy()
        C = self.C
        self.root.configure(bg=C["bg"])

        top = tk.Frame(self.root, bg=C["bg"])
        top.pack(fill="x", padx=22, pady=(14, 0))
        for key, label in (("todo", "TO-DO"), ("notes", "NOTES")):
            on = key == self.tab
            box = tk.Frame(top, bg=C["bg"])
            box.pack(side="left", padx=(0, 18))
            lbl = tk.Label(box, text=label, font=self.F["tab"], bg=C["bg"], cursor="hand2",
                           fg=C["text"] if on else C["faint"])
            lbl.pack()
            tk.Frame(box, height=2, bg=C["accent"] if on else C["bg"]).pack(fill="x", pady=(2, 0))
            lbl.bind("<Button-1>", lambda e, k=key: self.switch(k))

        # theme toggle (drawn, so it looks the same everywhere)
        dark = self.settings.get("theme") == "dark"
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
                       bg=C["accent"] if on_top else C["bg"], fg="#ffffff" if on_top else C["faint"])
        pin.pack(side="right", padx=(0, 12))
        pin.bind("<Button-1>", lambda e: self.toggle_on_top())

        self.body = tk.Frame(self.root, bg=C["bg"])
        self.body.pack(fill="both", expand=True)
        self.view = (TodoView if self.tab == "todo" else NotesView)(self, self.body)

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
        self.settings["theme"] = "light" if self.settings.get("theme") == "dark" else "dark"
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
            if self.tab == "todo":
                self.leaving()
                self.build()
        self.root.after(60_000, self._tick)

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


class TodoView:
    def __init__(self, app, parent):
        self.app, self.C, self.F = app, app.C, app.F
        self.root = app.root
        self.today = date.fromisoformat(app.today)
        self.week = self.today - timedelta(days=self.today.weekday())  # Monday
        self.open_day = app.today
        self.editing = None       # id of task being edited
        self.adding_sub = None    # id of task getting a new sub-task
        self.focus_add = False
        self.wrap_labels = []

        C = self.C
        nav = tk.Frame(parent, bg=C["bg"])
        nav.pack(fill="x", padx=22, pady=(14, 0))
        prev = tk.Label(nav, text="‹", font=self.F["title"], fg=C["muted"], bg=C["bg"], cursor="hand2")
        prev.pack(side="left")
        prev.bind("<Button-1>", lambda e: self.shift_week(-1))
        self.week_lbl = tk.Label(nav, font=self.F["small_b"], fg=C["muted"], bg=C["bg"], cursor="hand2")
        self.week_lbl.pack(side="left", padx=8)
        self.week_lbl.bind("<Button-1>", lambda e: self.shift_week(0))
        nxt = tk.Label(nav, text="›", font=self.F["title"], fg=C["muted"], bg=C["bg"], cursor="hand2")
        nxt.pack(side="left")
        nxt.bind("<Button-1>", lambda e: self.shift_week(1))

        self.scroll = ScrollArea(parent, C, on_width=self.rewrap)
        self.scroll.pack(fill="both", expand=True, pady=(4, 0))
        self.render(top=True)

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

    def shift_week(self, n):
        if n == 0:
            self.week = self.today - timedelta(days=self.today.weekday())
            self.open_day = self.today.isoformat()
        else:
            self.week += timedelta(weeks=n)
            self.open_day = None
        self.render(top=True)

    def render(self, top=False):
        y = self.scroll.canvas.yview()[0]
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self.wrap_labels = []

        end = self.week + timedelta(days=6)
        this_week = self.week == self.today - timedelta(days=self.today.weekday())
        rng = f"{self.week:%b} {self.week.day} – {end:%b} {end.day}"
        self.week_lbl.config(text=("THIS WEEK  ·  " if this_week else "") + rng.upper())
        self.open_section = None

        for i in range(7):
            self.render_day(self.week + timedelta(days=i), first=(i == 0))
        tk.Frame(self.scroll.inner, height=1, bg=self.C["line"]).pack(fill="x")
        tk.Frame(self.scroll.inner, height=30, bg=self.C["bg"]).pack(fill="x")

        self.root.update_idletasks()
        self.rewrap(self.scroll.canvas.winfo_width())
        if top and self.open_section is not None:
            # bring the open day (usually today) into view
            total = max(1, self.scroll.inner.winfo_height())
            y = max(0, self.open_section.winfo_y() - 60) / total
        elif top:
            y = 0
        self.scroll.canvas.yview_moveto(y)

    def render_day(self, d, first):
        C, F = self.C, self.F
        iso = d.isoformat()
        is_open = iso == self.open_day
        is_today = iso == self.today.isoformat()
        tasks = self.app.data["days"].get(iso, [])

        tk.Frame(self.scroll.inner, height=1, bg=C["bg"] if first else C["line"]).pack(fill="x")
        sec = tk.Frame(self.scroll.inner, bg=C["bg"])
        sec.pack(fill="x", padx=22)
        if is_open:
            self.open_section = sec

        head = tk.Frame(sec, bg=C["bg"], cursor="hand2")
        head.pack(fill="x", pady=(14, 14 if not is_open else 0))
        name = tk.Label(head, text=d.strftime("%A").upper(), font=F["day"], fg=C["text"], bg=C["bg"])
        name.pack(side="left")
        clickers = [head, name]
        if not is_open:
            left = sum(1 for t in tasks if not t["done"])
            if is_today:
                dot = tk.Canvas(head, width=10, height=10, bg=C["bg"], highlightthickness=0)
                dot.create_oval(1, 1, 9, 9, fill=C["accent"], outline="")
                dot.pack(side="left", padx=(8, 0))
                clickers.append(dot)
            if left:
                cnt = tk.Label(head, text=str(left), font=F["small_b"], fg=C["muted"], bg=C["bg"])
                cnt.pack(side="right")
                clickers.append(cnt)
        for w in clickers:
            w.bind("<Button-1>", lambda e, i=iso: self.toggle_day(i))

        if not is_open:
            return

        sub = f"{d:%B} {d.day}, {d.year}" + ("  —  Today" if is_today else "")
        tk.Label(sec, text=sub, font=F["small"], fg=C["muted"], bg=C["bg"]).pack(anchor="w", pady=(0, 10))

        for t in tasks:
            self.render_task(sec, t, depth=0)
            for c in t.get("children", []):
                self.render_task(sec, c, depth=1, parent_task=t)
            if self.adding_sub == t["id"]:
                self.render_sub_entry(sec, t)

        add = PlaceholderEntry(sec, "Add a new task...", C, font=F["body"], bg=C["bg"])
        add.pack(fill="x", pady=(14, 18))
        add.bind("<Return>", lambda e, i=iso, w=add: self.add_task(i, w))
        add.bind("<Escape>", lambda e: self.root.focus_set())
        if self.focus_add:
            self.focus_add = False
            add.focus_set()

    def render_task(self, parent, t, depth, parent_task=None, **_):
        C, F = self.C, self.F
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x", pady=2, padx=(26 * depth, 0))

        size = 15 if depth == 0 else 13
        chk = tk.Canvas(row, width=size + 2, height=size + 2, bg=C["bg"], highlightthickness=0, cursor="hand2")
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
        dele = tk.Label(row, text="×", font=F["icon"], fg=C["bg"], bg=C["bg"], cursor="hand2", padx=3)
        dele.pack(side="right", anchor="n")
        dele.bind("<Button-1>", lambda e: self.delete(t["id"]))
        actions.append(dele)
        if depth == 0:
            plus = tk.Label(row, text="+", font=F["icon"], fg=C["bg"], bg=C["bg"], cursor="hand2", padx=3)
            plus.pack(side="right", anchor="n")
            plus.bind("<Button-1>", lambda e: self.start_sub(t["id"]))
            actions.append(plus)

        txt = tk.Label(row, text=t["text"], font=F["body_done"] if t["done"] else F["body"],
                       fg=C["muted"] if t["done"] else C["text"], bg=C["bg"],
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
                a.config(fg=C["bg"])
        bind_hover(row, show, hide)

    def render_sub_entry(self, parent, t):
        C = self.C
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x", pady=2, padx=(26, 0))
        tk.Label(row, text="↳", font=self.F["body"], fg=C["faint"], bg=C["bg"]).pack(side="left", padx=(0, 6))
        e = PlaceholderEntry(row, "Add a sub-task...", C, font=self.F["body"], bg=C["bg"])
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
        head.pack(fill="x", padx=22, pady=(18, 12))
        tk.Label(head, text="NOTES", font=F["day"], fg=C["text"], bg=C["bg"]).pack(side="left")
        new = tk.Label(head, text="+ NEW", font=F["small_b"], fg="#ffffff", bg=C["accent"],
                       padx=10, pady=4, cursor="hand2")
        new.pack(side="right")
        new.bind("<Button-1>", lambda e: self.new_note())

        self.scroll = ScrollArea(self.parent, C)
        self.scroll.pack(fill="both", expand=True)
        notes = sorted(self.app.data["notes"], key=lambda n: n.get("updated", ""), reverse=True)
        if not notes:
            tk.Label(self.scroll.inner, text="No notes yet.\nClick + NEW to write one.", font=F["body"],
                     fg=C["faint"], bg=C["bg"], justify="center").pack(pady=50)
        for n in notes:
            self.render_card(n)
        if notes:
            tk.Frame(self.scroll.inner, height=1, bg=C["line"]).pack(fill="x")

    def render_card(self, n):
        C, F = self.C, self.F
        tk.Frame(self.scroll.inner, height=1, bg=C["line"]).pack(fill="x")
        card = tk.Frame(self.scroll.inner, bg=C["bg"], cursor="hand2")
        card.pack(fill="x", padx=22, pady=12)
        top = tk.Frame(card, bg=C["bg"])
        top.pack(fill="x")
        title = tk.Label(top, text=n.get("title") or "Untitled", font=F["note_title"], fg=C["text"],
                         bg=C["bg"], anchor="w")
        title.pack(side="left")
        dele = tk.Label(top, text="×", font=F["icon"], fg=C["bg"], bg=C["bg"], cursor="hand2")
        dele.pack(side="right")
        when = tk.Label(top, text=self.when(n.get("updated")), font=F["small"], fg=C["muted"], bg=C["bg"])
        when.pack(side="right", padx=6)
        plain = " ".join("".join(r[0] for r in n.get("content", [])).replace(BULLET, "").split())
        if len(plain) > 52:
            plain = plain[:50].rstrip() + "…"
        prev = tk.Label(card, text=plain or "Empty note", font=F["small"],
                        fg=C["muted"], bg=C["bg"], anchor="w", justify="left")
        prev.pack(fill="x")
        for w in (card, top, title, when, prev):
            w.bind("<Button-1>", lambda e: self.open(n))
        dele.bind("<Button-1>", lambda e: self.delete(n))
        bind_hover(card, lambda: dele.config(fg=C["muted"]), lambda: dele.config(fg=C["bg"]))

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
        sb.pack(side="right", fill="y")

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
            btn.config(bg=C["accent"] if state[k] else C["chip"], fg="#ffffff" if state[k] else C["text"])

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


def main():
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
