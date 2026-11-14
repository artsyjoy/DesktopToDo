# DeskTodo

A weekly to-do list and notes app that lives on your Windows desktop. No website, no account, no internet.

## To-do tab

- The week is laid out Monday to Sunday with big day headings. Today opens automatically; click any day to open it.
- Type in **Add a new task...** and press **Enter**.
- Tick the box to finish a task: it turns orange and gets struck through.
- **Sub-tasks:** hover a task and click **+**, then type the sub-task (press Enter to add more, Esc to stop).
  Finishing a main task finishes its sub-tasks too.
- **Double-click** a task to edit it. Hover and click **×** to delete it.
- **Right-click** a task for more: move to the next day or to today, indent it under the task above, outdent a sub-task.
- Unfinished tasks from earlier days move to today automatically.
- Use the **‹ ›** arrows to look at other weeks. Click the week label to jump back to this week.

## Notes tab

- **+ NEW** starts a note. Notes save as you type.
- Toolbar: **B** bold (or Ctrl+B), **H** heading, **•≡** bullet list.
- In a bullet list, Enter starts the next bullet. Enter on an empty bullet (or Backspace right after the bullet) ends the list.

## Everywhere

- Moon / sun icon: switch between light and dark themes.
- **PIN** keeps the window on top of other windows (Ctrl+T).
- Ctrl+1 / Ctrl+2 switch between To-do and Notes.
- Everything is saved to `%APPDATA%\DeskTodo\data.json`. Tasks from the first version of DeskTodo are imported automatically.

## Get it running

**Option A — the .exe (no install needed).**
Every push builds `DeskTodo.exe` with GitHub Actions. Open the repo's **Actions** tab →
latest "Build DeskTodo for Windows" run → download **DeskTodo-windows** under *Artifacts*,
unzip it, and run `DeskTodo.exe`. Windows SmartScreen may warn because the exe isn't signed:
click *More info → Run anyway*.

**Option B — with Python.**
Install Python from python.org (tick "Add to PATH"), then double-click `desktodo.pyw`.
Keep the `fonts` folder next to it.

## Start it with Windows

Press **Win+R**, type `shell:startup`, Enter. Right-click `DeskTodo.exe` (or `desktodo.pyw`) →
*Show more options → Create shortcut*, and move the shortcut into that folder.

## Credits

Uses the [Barlow](https://github.com/jpt/barlow) typeface by The Barlow Project Authors,
licensed under the SIL Open Font License (see `fonts/OFL.txt`).
