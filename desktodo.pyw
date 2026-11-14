"""
DeskTodo - a small, always-there to-do list for your Windows desktop.

Pure Python standard library (tkinter), no internet, no accounts.
Tasks are saved to %APPDATA%\\DeskTodo\\tasks.json automatically.

Shortcuts
  Enter          add the task typed in the box
  Ctrl+N         jump to the "add a task" box
  Double-click   edit a task (Enter saves, Esc cancels)
  Ctrl+T         toggle "always on top"
"""

import json
import os
import sys
import tkinter as tk
import uuid
from datetime import datetime
from tkinter import font as tkfont

APP_NAME = "DeskTodo"

# --------------------------------------------------------------------------- storage


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


DATA_FILE = os.path.join(data_dir(), "tasks.json")


def load_state():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if isinstance(state, dict) and isinstance(state.get("tasks"), list):
            return state
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        # Keep a copy of an unreadable file instead of silently overwriting it.
        try:
            os.replace(DATA_FILE, DATA_FILE + ".broken")
        except OSError:
            pass
    return {"tasks": [], "settings": {}}


def save_state(state):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)  # atomic: never leaves a half-written file


# --------------------------------------------------------------------------- look

C = {
    "bg": "#16171d",
    "panel": "#1f2029",
    "row": "#23252f",
    "row_hover": "#2b2d39",
    "border": "#30323f",
    "text": "#e8e9ef",
    "muted": "#8b8ea0",
    "faint": "#5d6072",
    "accent": "#7c9cff",
    "accent_dim": "#3a4a80",
    "star": "#f5c451",
    "danger": "#ff6b7a",
    "done_text": "#6b6e80",
}

UI_FAMILY = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


# --------------------------------------------------------------------------- app


class DeskTodo:
    FILTERS = ("All", "Active", "Done")

    def __init__(self, root):
        self.root = root
        self.state = load_state()
        self.settings = self.state.setdefault("settings", {})
        self.filter = self.settings.get("filter", "All")
        self.editing_id = None

        self.f_title = tkfont.Font(family=UI_FAMILY, size=17, weight="bold")
        self.f_sub = tkfont.Font(family=UI_FAMILY, size=9)
        self.f_body = tkfont.Font(family=UI_FAMILY, size=11)
        self.f_done = tkfont.Font(family=UI_FAMILY, size=11, overstrike=True)
        self.f_small = tkfont.Font(family=UI_FAMILY, size=9)
        self.f_icon = tkfont.Font(family=UI_FAMILY, size=12)

        root.title(APP_NAME)
        root.configure(bg=C["bg"])
        root.minsize(300, 360)
        root.geometry(self.settings.get("geometry", "380x560"))
        root.attributes("-topmost", bool(self.settings.get("on_top", False)))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_header()
        self.build_input()
        self.build_filters()
        self.build_list()
        self.build_footer()

        root.bind("<Control-n>", lambda e: self.entry.focus_set())
        root.bind("<Control-t>", lambda e: self.toggle_on_top())

        self.render()
        self.entry.focus_set()

    # ---- layout --------------------------------------------------------------

    def build_header(self):
        head = tk.Frame(self.root, bg=C["bg"])
        head.pack(fill="x", padx=18, pady=(16, 6))

        left = tk.Frame(head, bg=C["bg"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="My Tasks", font=self.f_title, fg=C["text"], bg=C["bg"]).pack(anchor="w")
        today = datetime.now()
        tk.Label(left, text=f"{today:%A}, {today:%B} {today.day}", font=self.f_sub,
                 fg=C["muted"], bg=C["bg"]).pack(anchor="w")

        self.pin_btn = tk.Label(head, font=self.f_small, bg=C["bg"], cursor="hand2", padx=8, pady=3)
        self.pin_btn.pack(side="right", anchor="n")
        self.pin_btn.bind("<Button-1>", lambda e: self.toggle_on_top())
        self.update_pin()

    def build_input(self):
        box = tk.Frame(self.root, bg=C["panel"], highlightthickness=1,
                       highlightbackground=C["border"], highlightcolor=C["accent"])
        box.pack(fill="x", padx=18, pady=(8, 10))

        self.entry = tk.Entry(box, font=self.f_body, bg=C["panel"], fg=C["text"],
                              insertbackground=C["text"], relief="flat", bd=0, highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=10)
        self.entry.bind("<Return>", lambda e: self.add_task())
        self.entry.bind("<FocusIn>", lambda e: box.config(highlightbackground=C["accent"]))
        self.entry.bind("<FocusOut>", lambda e: box.config(highlightbackground=C["border"]))

        self.placeholder = "Add a task and press Enter"
        self._show_placeholder()
        self.entry.bind("<FocusIn>", self._clear_placeholder, add="+")
        self.entry.bind("<FocusOut>", lambda e: self._show_placeholder(), add="+")

        add = tk.Label(box, text="+", font=tkfont.Font(family=UI_FAMILY, size=16, weight="bold"),
                       fg=C["accent"], bg=C["panel"], cursor="hand2", padx=12)
        add.pack(side="right")
        add.bind("<Button-1>", lambda e: self.add_task())

    def _show_placeholder(self):
        if not self.entry.get():
            self.entry.insert(0, self.placeholder)
            self.entry.config(fg=C["faint"])
            self._placeholder_on = True

    def _clear_placeholder(self, _e=None):
        if getattr(self, "_placeholder_on", False):
            self.entry.delete(0, "end")
            self.entry.config(fg=C["text"])
            self._placeholder_on = False

    def build_filters(self):
        bar = tk.Frame(self.root, bg=C["bg"])
        bar.pack(fill="x", padx=18, pady=(0, 6))
        self.filter_labels = {}
        for name in self.FILTERS:
            lbl = tk.Label(bar, text=name, font=self.f_small, cursor="hand2", padx=10, pady=3)
            lbl.pack(side="left", padx=(0, 4))
            lbl.bind("<Button-1>", lambda e, n=name: self.set_filter(n))
            self.filter_labels[name] = lbl

    def build_list(self):
        wrap = tk.Frame(self.root, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=(18, 8))

        self.canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0, bd=0)
        self.scroll = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview, width=10)
        self.canvas.configure(yscrollcommand=self._autoscroll)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.list_frame = tk.Frame(self.canvas, bg=C["bg"])
        self.list_win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Mouse wheel (Windows/macOS send <MouseWheel>, X11 sends Button-4/5)
        self.root.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units"))
        self.root.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.root.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def _autoscroll(self, first, last):
        # Only show the scrollbar when the list doesn't fit.
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scroll.pack_forget()
        elif not self.scroll.winfo_ismapped():
            self.scroll.pack(side="right", fill="y", before=self.canvas)
        self.scroll.set(first, last)

    def _on_canvas_resize(self, event):
        self.canvas.itemconfigure(self.list_win, width=event.width - 6)
        wrap = max(120, event.width - 110)
        for child in self.list_frame.winfo_children():
            for lbl in getattr(child, "_wrap_labels", []):
                lbl.config(wraplength=wrap)

    def build_footer(self):
        foot = tk.Frame(self.root, bg=C["bg"])
        foot.pack(fill="x", padx=18, pady=(6, 12))
        self.count_lbl = tk.Label(foot, font=self.f_small, fg=C["muted"], bg=C["bg"])
        self.count_lbl.pack(side="left")
        clear = tk.Label(foot, text="Clear completed", font=self.f_small, fg=C["muted"],
                         bg=C["bg"], cursor="hand2")
        clear.pack(side="right")
        clear.bind("<Button-1>", lambda e: self.clear_done())
        clear.bind("<Enter>", lambda e: clear.config(fg=C["danger"]))
        clear.bind("<Leave>", lambda e: clear.config(fg=C["muted"]))

    # ---- rendering -----------------------------------------------------------

    def visible_tasks(self):
        tasks = self.state["tasks"]
        if self.filter == "Active":
            tasks = [t for t in tasks if not t["done"]]
        elif self.filter == "Done":
            tasks = [t for t in tasks if t["done"]]
        # Starred first, then open before done, otherwise keep the order they were added.
        return sorted(tasks, key=lambda t: (t["done"], not t.get("star", False)))

    def render(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

        for name, lbl in self.filter_labels.items():
            on = name == self.filter
            lbl.config(bg=C["accent_dim"] if on else C["bg"], fg=C["text"] if on else C["muted"])

        tasks = self.visible_tasks()
        if not tasks:
            msg = {"All": "Nothing here yet.\nType a task above to get started.",
                   "Active": "All caught up! 🎉",
                   "Done": "No completed tasks yet."}[self.filter]
            tk.Label(self.list_frame, text=msg, font=self.f_body, fg=C["faint"], bg=C["bg"],
                     justify="center").pack(pady=40, fill="x")
        for task in tasks:
            self.render_row(task)

        left = sum(1 for t in self.state["tasks"] if not t["done"])
        self.count_lbl.config(text=f"{left} task{'s' if left != 1 else ''} left")
        self.canvas.yview_moveto(0)
        self.root.after_idle(lambda: self._on_canvas_resize(
            type("E", (), {"width": self.canvas.winfo_width()})()))

    def render_row(self, task):
        row = tk.Frame(self.list_frame, bg=C["row"], padx=10, pady=8)
        row.pack(fill="x", pady=3)

        # checkbox
        chk = tk.Canvas(row, width=20, height=20, bg=C["row"], highlightthickness=0, cursor="hand2")
        chk.pack(side="left", padx=(0, 10), anchor="n", pady=2)
        if task["done"]:
            chk.create_oval(2, 2, 18, 18, fill=C["accent"], outline=C["accent"])
            chk.create_line(6, 10, 9, 13, 14, 7, fill=C["bg"], width=2)
        else:
            chk.create_oval(2, 2, 18, 18, outline=C["faint"], width=2)
        chk.bind("<Button-1>", lambda e, t=task: self.toggle_done(t))

        # delete (hidden until hover)
        dele = tk.Label(row, text="✕", font=self.f_small, fg=C["row"], bg=C["row"], cursor="hand2", padx=4)
        dele.pack(side="right", anchor="n")
        dele.bind("<Button-1>", lambda e, t=task: self.delete_task(t))
        dele.bind("<Enter>", lambda e: dele.config(fg=C["danger"]))

        # star
        star_on = task.get("star", False)
        star = tk.Label(row, text="★" if star_on else "☆", font=self.f_icon,
                        fg=C["star"] if star_on else C["row"], bg=C["row"], cursor="hand2", padx=2)
        star.pack(side="right", anchor="n")
        star.bind("<Button-1>", lambda e, t=task: self.toggle_star(t))

        if self.editing_id == task["id"]:
            ed = tk.Entry(row, font=self.f_body, bg=C["row_hover"], fg=C["text"],
                          insertbackground=C["text"], relief="flat", bd=0, highlightthickness=0)
            ed.insert(0, task["text"])
            ed.pack(side="left", fill="x", expand=True)
            ed.focus_set()
            ed.select_range(0, "end")
            ed.bind("<Return>", lambda e, t=task: self.finish_edit(t, ed.get()))
            ed.bind("<Escape>", lambda e: self.cancel_edit())
            ed.bind("<FocusOut>", lambda e, t=task: self.finish_edit(t, ed.get()))
            row._wrap_labels = []
            return

        txt = tk.Label(row, text=task["text"], font=self.f_done if task["done"] else self.f_body,
                       fg=C["done_text"] if task["done"] else C["text"], bg=C["row"],
                       anchor="w", justify="left", wraplength=240)
        txt.pack(side="left", fill="x", expand=True)
        row._wrap_labels = [txt]

        widgets = (row, txt, chk, star, dele)

        def hover(on, t=task):
            bg = C["row_hover"] if on else C["row"]
            for w in widgets:
                w.config(bg=bg)
            dele.config(fg=C["faint"] if on else bg)
            if not t.get("star"):
                star.config(fg=C["faint"] if on else bg)

        for w in widgets:
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e: hover(False), add="+")
        for w in (row, txt):
            w.bind("<Double-Button-1>", lambda e, t=task: self.start_edit(t))

    # ---- actions -------------------------------------------------------------

    def persist(self):
        try:
            save_state(self.state)
        except OSError as exc:
            self.count_lbl.config(text=f"Couldn't save: {exc}", fg=C["danger"])

    def add_task(self):
        if getattr(self, "_placeholder_on", False):
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.state["tasks"].append({
            "id": uuid.uuid4().hex, "text": text, "done": False, "star": False,
            "created": datetime.now().isoformat(timespec="seconds"),
        })
        self.entry.delete(0, "end")
        if self.filter == "Done":
            self.filter = "All"
        self.persist()
        self.render()

    def toggle_done(self, task):
        task["done"] = not task["done"]
        task["completed"] = datetime.now().isoformat(timespec="seconds") if task["done"] else None
        self.persist()
        self.render()

    def toggle_star(self, task):
        task["star"] = not task.get("star", False)
        self.persist()
        self.render()

    def delete_task(self, task):
        self.state["tasks"] = [t for t in self.state["tasks"] if t["id"] != task["id"]]
        self.persist()
        self.render()

    def clear_done(self):
        self.state["tasks"] = [t for t in self.state["tasks"] if not t["done"]]
        self.persist()
        self.render()

    def start_edit(self, task):
        self.editing_id = task["id"]
        self.render()

    def finish_edit(self, task, text):
        if self.editing_id != task["id"]:
            return  # already handled (Enter followed by FocusOut)
        self.editing_id = None
        text = text.strip()
        if text:
            task["text"] = text
            self.persist()
        self.root.after_idle(self.render)

    def cancel_edit(self):
        self.editing_id = None
        self.render()

    def set_filter(self, name):
        self.filter = name
        self.render()

    def toggle_on_top(self):
        on = not bool(self.settings.get("on_top", False))
        self.settings["on_top"] = on
        self.root.attributes("-topmost", on)
        self.update_pin()
        self.persist()

    def update_pin(self):
        on = bool(self.settings.get("on_top", False))
        self.pin_btn.config(text="● On top" if on else "○ On top",
                            fg=C["text"] if on else C["muted"],
                            bg=C["accent_dim"] if on else C["bg"])

    def on_close(self):
        self.settings["geometry"] = self.root.geometry()
        self.settings["filter"] = self.filter
        self.persist()
        self.root.destroy()


def main():
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    DeskTodo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
