# DeskTodo

A small to-do list that lives on your Windows desktop. No website, no account, no internet.

- Type a task and press **Enter** to add it
- Click the circle to tick it off; **Clear completed** removes finished ones
- **Double-click** a task to edit it (Enter saves, Esc cancels)
- Hover a task to **star** it (starred tasks stay at the top) or **✕** delete it
- **On top** keeps the window above other windows (Ctrl+T)
- Filter by All / Active / Done
- Remembers its size and position

Tasks are saved automatically to `%APPDATA%\DeskTodo\tasks.json`.

## Get it running

**Option A — the .exe (no install needed).**
Every push builds `DeskTodo.exe` with GitHub Actions. Open the repo's **Actions** tab →
latest "Build DeskTodo for Windows" run → download **DeskTodo-windows** under *Artifacts*,
unzip it, and run `DeskTodo.exe`. Windows SmartScreen may warn because the exe isn't signed:
click *More info → Run anyway*.

**Option B — with Python.**
Install Python from python.org (tick "Add to PATH"), then double-click `desktodo.pyw`.

## Start it with Windows

Press **Win+R**, type `shell:startup`, Enter. Right-click `DeskTodo.exe` (or `desktodo.pyw`) →
*Show more options → Create shortcut*, and move the shortcut into that folder.
