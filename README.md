# DeskTodo

A to-do list, notes and "at a glance" dashboard that lives on your Windows desktop. No website, no account.

## To-do tab

- **Today is always at the top**, with the live time, followed by the next six days (each a shade darker).
  Click any day to open it.
- Type in **Add a new task...** and press **Enter**.
- Tick the box to finish a task: it turns orange and gets struck through.
- **Sub-tasks:** hover a task and click **+**, then type the sub-task (press Enter to add more, Esc to stop).
  Finishing a main task finishes its sub-tasks too.
- **Double-click** a task to edit it. Hover and click **×** to delete it.
- **Right-click** a task for more: move to the next day or to today, indent it under the task above, outdent a sub-task.
- At midnight, unfinished tasks move to the new day automatically (if the PC was off or asleep,
  this happens as soon as DeskTodo is running again).

## Notes tab

- **+ NEW** starts a note. Notes save as you type.
- Toolbar: **B** bold (or Ctrl+B), **H** heading, **•≡** bullet list.
- In a bullet list, Enter starts the next bullet. Enter on an empty bullet (or Backspace right after the bullet) ends the list.

## At a glance tab

- A big clock (12h / 24h toggle) with today's date and sunrise/sunset.
- Weather for two places (Glenwood Springs and Basalt, CO to start). Click **···** on a weather card
  to change the city, switch °F/°C, or refresh. Weather comes from open-meteo.com (free, no account).
- **Up next:** your upcoming Outlook meetings for the next week, with a one-line brief of today
  ("Today: 2 events · 3 tasks left").
  Click **+ CONNECT OUTLOOK** and follow the 3 steps: in Outlook on the web, *Settings → Calendar →
  Shared calendars → Publish a calendar*, then paste the **ICS** link. Refreshes every 10 minutes.
- **Today's tasks:** tick them off right from here; click **OPEN ›** to jump to the To-do tab.

## Everywhere

- DeskTodo looks like a desktop widget: no title bar. **Drag the top bar** (the empty space next to the tabs)
  to move it, drag the **bottom-right corner** to resize, and click **×** to close.
- **Right-click the top bar** for: keep on top, show/hide the normal window frame, close.
- Moon / sun icon: switch between light and dark themes.
- **PIN** keeps the window on top of other windows (Ctrl+T).
- Ctrl+1 / Ctrl+2 / Ctrl+3 switch between To-do, Notes and At a glance.
- Everything (tasks, notes, settings, last weather) is saved to `%APPDATA%\DeskTodo\data.json` as you go,
  so closing and reopening the app — or replacing the .exe with a new version — keeps all of it.

## Get it running

**Option A — the app (no install needed).**
Every push builds DeskTodo with GitHub Actions (and scans it with Microsoft Defender).
Open the repo's **Actions** tab → latest "Build DeskTodo for Windows" run → download **DeskTodo-windows**
under *Artifacts*. Right-click the zip → **Properties** → tick **Unblock** → OK, then unzip it.

You get a **DeskTodo** folder containing `DeskTodo.exe` and an `_internal` folder. Keep them together:
move the whole folder somewhere permanent (e.g. `C:\Users\<you>\Apps\DeskTodo`) and run `DeskTodo.exe`
from there. To update later, close DeskTodo and replace the whole folder.

If Microsoft Defender still removes it, open **Windows Security → Virus & threat protection →
Protection history**, choose the DeskTodo entry → **Actions → Restore**. You can also report it as a
false positive at https://www.microsoft.com/wdsi/filesubmission so Defender learns it is safe.

**Option B — with Python.**
Install Python from python.org (tick "Add to PATH"), then double-click `desktodo.pyw`.
Keep the `fonts` folder next to it.

## Start it with Windows

Press **Win+R**, type `shell:startup`, Enter. Right-click `DeskTodo.exe` inside the DeskTodo folder (or `desktodo.pyw`) →
*Show more options → Create shortcut*, and move the shortcut into that folder.

## Credits

Uses the [Barlow](https://github.com/jpt/barlow) typeface by The Barlow Project Authors,
licensed under the SIL Open Font License (see `fonts/OFL.txt`).

## Code signing (removing the warning for everyone)

Windows shows "Windows protected your PC / Unknown publisher" for any program that isn't digitally
signed by a verified publisher. Ways to get rid of it properly:

- **Azure Trusted Signing** (Microsoft's signing service, about $10/month). After identity verification,
  the build can sign `DeskTodo.exe` automatically.
- **Microsoft Store**: publishing there is free for individual developers, and Store installs don't warn.
- A traditional code-signing certificate from a certificate authority (usually a few hundred dollars a year).
