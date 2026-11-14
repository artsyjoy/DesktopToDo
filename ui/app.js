/* DeskTodo interface. Data lives in Python (core.py); this file draws the UI and animates it.
   All motion uses transform / opacity (GPU-composited), so it stays smooth in WebView2. */
"use strict";

// ---------------------------------------------------------------- helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const h = html => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const EASE = "cubic-bezier(.22,.8,.24,1)";
const api = () => (window.pywebview && window.pywebview.api) || window.__mockApi || null;
const call = (name, ...args) => { const a = api(); return a && a[name] ? Promise.resolve(a[name](...args)) : Promise.resolve(null); };
const newId = () => Math.random().toString(16).slice(2, 14);

const pad2 = n => String(n).padStart(2, "0");
const isoOf = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const todayIso = () => isoOf(new Date());
const parseIso = s => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const parseLocal = s => { const [a, b = "00:00:00"] = s.split("T"); const [y, m, d] = a.split("-").map(Number); const [hh, mi] = b.split(":").map(Number); return new Date(y, m - 1, d, hh || 0, mi || 0); };
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const longDate = d => `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;

// ---------------------------------------------------------------- state
let D = null;          // all saved data (days, notes, settings, cache)
let S = null;          // D.settings
const ui = { tab: "glance", todoOpen: null, cal: null, noteId: null, smoke: false };
const g = {};          // live elements of the current glance page

const DEFAULT_CITIES = [
  { name: "Glenwood Springs", region: "Colorado", lat: 39.5505, lon: -107.3248 },
  { name: "Basalt", region: "Colorado", lat: 39.3689, lon: -107.0328 },
];
const h24 = () => S.clock24 !== false;
const fmtTime = d => h24() ? `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  : `${d.getHours() % 12 || 12}:${pad2(d.getMinutes())}${d.getHours() < 12 ? "am" : "pm"}`;

let saveTimer = null;
function save(now = false) {
  clearTimeout(saveTimer);
  if (now) return call("save", D);
  saveTimer = setTimeout(() => call("save", D), 250);
}

function rollOver() {
  const t = todayIso(); const moved = [];
  for (const day of Object.keys(D.days).sort()) {
    if (day >= t) continue;
    const keep = [];
    for (const task of D.days[day]) (task.done ? keep : moved).push(task);
    D.days[day] = keep;
  }
  if (moved.length) D.days[t] = moved.concat(D.days[t] || []);
  for (const k of Object.keys(D.days)) if (!D.days[k].length) delete D.days[k];
  return moved.length > 0;
}

// ---------------------------------------------------------------- icons
const ICON = {
  check: '<svg viewBox="0 0 12 12"><path d="M2.5 6.2l2.4 2.4 4.6-5" fill="none" stroke="var(--on-accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  sun: '<svg viewBox="0 0 14 14"><circle cx="7" cy="7" r="2.6" fill="none" stroke="currentColor" stroke-width="1.5"/><g stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M7 .9v1.4M7 11.7v1.4M.9 7h1.4M11.7 7h1.4M2.7 2.7l1 1M10.3 10.3l1 1M2.7 11.3l1-1M10.3 3.7l1-1"/></g></svg>',
  moon: '<svg viewBox="0 0 14 14"><path d="M11.8 8.6A5.3 5.3 0 0 1 5.4 2.2a5.3 5.3 0 1 0 6.4 6.4z" fill="currentColor"/></svg>',
};
const CLOUD = '<path d="M14 36h21a8.5 8.5 0 0 0 0-17 11 11 0 0 0-21.3-2.3A9.6 9.6 0 0 0 14 36z" fill="currentColor"/>';
function wxIcon(kind, isDay) {
  const sun = (cx, cy, r) => isDay ? `<circle cx="${cx}" cy="${cy}" r="${r}" fill="var(--accent)"/>`
    : `<path d="M${cx + r * .9} ${cy + r * .35}A${r} ${r} 0 1 1 ${cx - r * .2} ${cy - r}a${r * .8} ${r * .8} 0 0 0 ${r * 1.1} ${r * 1.35}z" fill="currentColor"/>`;
  const wrap = inner => `<svg class="wx-icon" viewBox="0 0 48 48" style="color:var(--muted)">${inner}</svg>`;
  switch (kind) {
    case "clear": return wrap(sun(24, 24, 10));
    case "partly": return wrap(sun(18, 17, 8) + `<g transform="translate(4 6) scale(.9)">${CLOUD}</g>`);
    case "fog": return wrap('<g stroke="currentColor" stroke-width="3.2" stroke-linecap="round"><path d="M8 17h32M12 25h26M8 33h30"/></g>');
    case "rain": return wrap(`<g transform="translate(0 -4)">${CLOUD}</g><g stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M17 37l-2 5M25 37l-2 5M33 37l-2 5"/></g>`);
    case "snow": return wrap(`<g transform="translate(0 -4)">${CLOUD}</g><g fill="currentColor"><circle cx="16" cy="40" r="2"/><circle cx="24" cy="42" r="2"/><circle cx="32" cy="40" r="2"/></g>`);
    case "storm": return wrap(`<g transform="translate(0 -4)">${CLOUD}</g><path d="M25 33l-5 8h5l-3 6" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`);
    default: return wrap(CLOUD);
  }
}
const WX = {
  0: ["Clear", "clear"], 1: ["Mostly clear", "clear"], 2: ["Partly cloudy", "partly"], 3: ["Cloudy", "cloud"],
  45: ["Fog", "fog"], 48: ["Freezing fog", "fog"], 51: ["Light drizzle", "rain"], 53: ["Drizzle", "rain"], 55: ["Heavy drizzle", "rain"],
  56: ["Freezing drizzle", "rain"], 57: ["Freezing drizzle", "rain"], 61: ["Light rain", "rain"], 63: ["Rain", "rain"], 65: ["Heavy rain", "rain"],
  66: ["Freezing rain", "rain"], 67: ["Freezing rain", "rain"], 71: ["Light snow", "snow"], 73: ["Snow", "snow"], 75: ["Heavy snow", "snow"],
  77: ["Snow grains", "snow"], 80: ["Showers", "rain"], 81: ["Showers", "rain"], 82: ["Heavy showers", "rain"], 85: ["Snow showers", "snow"],
  86: ["Snow showers", "snow"], 95: ["Thunderstorm", "storm"], 96: ["Storm & hail", "storm"], 99: ["Storm & hail", "storm"],
};

// ---------------------------------------------------------------- segmented pills
function segHTML(name, items, active, cls = "") {
  return `<div class="seg ${cls}" data-seg="${name}"><span class="pill"></span>${items.map(([v, label]) =>
    `<button data-v="${esc(v)}" class="${v === active ? "on" : ""}">${esc(label)}</button>`).join("")}</div>`;
}
function placePill(seg, animate = true) {
  const on = seg.querySelector("button.on") || seg.querySelector("button");
  const pill = seg.querySelector(".pill");
  if (!on || !pill) return;
  if (!animate) pill.style.transition = "none";
  pill.style.width = on.offsetWidth + "px";
  pill.style.transform = `translateX(${on.offsetLeft}px)`;
  if (!animate) { void pill.offsetWidth; pill.style.transition = ""; }
}
function setSeg(seg, value) {
  $$("button", seg).forEach(b => b.classList.toggle("on", b.dataset.v === value || b.dataset.tab === value));
  placePill(seg, true);
}

// ---------------------------------------------------------------- page transitions
function swapPage(page, dir) {
  const views = $("#views");
  $$(".page.leaving", views).forEach(p => p.remove());
  const old = $(".page", views);
  views.appendChild(page);
  if (!old) return;
  if (!dir) { old.remove(); return; }
  old.classList.add("leaving");
  const o = { duration: 360, easing: EASE };
  old.animate([{ transform: "none", opacity: 1 }, { transform: `translateX(${-dir * 48}px)`, opacity: 0 }], { ...o, fill: "forwards" })
    .onfinish = () => old.remove();
  page.animate([{ transform: `translateX(${dir * 48}px)`, opacity: 0 }, { transform: "none", opacity: 1 }], o);
}
function newPage(cls) { return h(`<section class="page ${cls}"><div class="page-inner"></div></section>`); }

const TABS = ["glance", "todo", "notes"];
function showTab(tab, animate = true) {
  const dir = animate ? (TABS.indexOf(tab) > TABS.indexOf(ui.tab) ? 1 : -1) : 0;
  flushNote();
  ui.tab = tab; S.tab = tab;
  setSeg($("#tabs"), tab);
  const page = tab === "glance" ? buildGlance() : tab === "todo" ? buildTodo() : (ui.noteId ? buildEditor() : buildNotes());
  swapPage(page, dir);
  if (tab === "glance") afterGlanceMount();
}

// ---------------------------------------------------------------- theme
function applyTheme() {
  document.documentElement.classList.toggle("dark", S.theme !== "light");
  $("#theme").innerHTML = S.theme === "light" ? ICON.moon : ICON.sun;
}
function toggleTheme() {
  S.theme = S.theme === "light" ? "dark" : "light";
  save();
  if (document.startViewTransition) { document.startViewTransition(applyTheme); return; }
  const root = document.documentElement;
  root.classList.add("theme-fallback");
  applyTheme();
  setTimeout(() => root.classList.remove("theme-fallback"), 520);
}

// ---------------------------------------------------------------- menus, sheets, toasts
let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
function showMenu(x, y, items) {
  closeMenu();
  menuEl = h(`<div class="menu">${items.map((it, i) => it === "-" ? "<hr>" : `<button data-i="${i}">${esc(it[0])}</button>`).join("")}</div>`);
  document.body.appendChild(menuEl);
  const r = menuEl.getBoundingClientRect();
  menuEl.style.left = Math.min(x, innerWidth - r.width - 8) + "px";
  menuEl.style.top = Math.min(y, innerHeight - r.height - 8) + "px";
  menuEl.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; const fn = items[+b.dataset.i][1]; closeMenu(); fn(); });
}
document.addEventListener("pointerdown", e => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); }, true);

function openSheet(html) {
  const scrim = h(`<div class="scrim"><div class="sheet">${html}</div></div>`);
  document.body.appendChild(scrim);
  const close = () => {
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 160, easing: EASE }).onfinish = () => scrim.remove();
  };
  scrim.addEventListener("pointerdown", e => { if (e.target === scrim) close(); });
  scrim.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  return { el: scrim.firstElementChild, close };
}
function toast(text) {
  const t = h(`<div class="toast">${esc(text)}</div>`);
  document.body.appendChild(t);
  setTimeout(() => t.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 250 }).onfinish = () => t.remove(), 1800);
}
function confirmSheet(title, body, okLabel, onOk) {
  const s = openSheet(`<h2>${esc(title)}</h2><div class="muted">${esc(body)}</div>
    <div class="actions"><button class="btn" data-ok>${esc(okLabel)}</button><button class="btn ghost" data-cancel>Cancel</button></div>`);
  $("[data-ok]", s.el).onclick = () => { s.close(); onOk(); };
  $("[data-cancel]", s.el).onclick = s.close;
}

// ---------------------------------------------------------------- tasks (shared by To-do and the calendar)
function findTask(id) {
  for (const [iso, list] of Object.entries(D.days)) for (const t of list) {
    if (t.id === id) return { t, list, iso, parent: null };
    for (const c of t.children || []) if (c.id === id) return { t: c, list: t.children, iso, parent: t };
  }
  return {};
}
function taskHTML(t, sub = false) {
  return `<div class="task ${sub ? "sub" : ""} ${t.done ? "done" : ""}" data-id="${t.id}">
    <button class="chk" data-act="toggle">${ICON.check}</button><div class="txt" data-act="edit">${esc(t.text)}</div>
    <div class="acts">${sub ? "" : '<button data-act="sub" title="Add sub-task">+</button>'}<button data-act="del" title="Delete">&times;</button></div></div>`;
}
function tasksHTML(list) {
  return list.map(t => taskHTML(t) + (t.children || []).map(c => taskHTML(c, true)).join("")).join("");
}
function toggleTask(id) {
  const { t, parent } = findTask(id); if (!t) return;
  t.done = !t.done;
  if (t.done) (t.children || []).forEach(c => c.done = true);
  else if (parent && parent.done) parent.done = false;
  save();
}
function deleteTask(id) { const { t, list } = findTask(id); if (t) { list.splice(list.indexOf(t), 1); save(); } }
function addTask(iso, text) { (D.days[iso] = D.days[iso] || []).push({ id: newId(), text, done: false, children: [] }); save(); }

/* One delegated handler for task rows anywhere. `refresh(iso)` redraws what changed. */
function wireTasks(container, refresh) {
  container.addEventListener("click", e => {
    const act = e.target.closest("[data-act]"); const row = e.target.closest(".task");
    if (!act || !row || row.querySelector("input.edit")) return;
    const id = row.dataset.id; const { iso } = findTask(id);
    if (act.dataset.act === "toggle") { row.classList.toggle("done"); toggleTask(id); setTimeout(() => refresh(iso), 180); }
    else if (act.dataset.act === "del") { row.animate([{ opacity: 1 }, { opacity: 0, transform: "translateX(12px)" }], { duration: 180, easing: EASE }).onfinish = () => { deleteTask(id); refresh(iso); }; }
    else if (act.dataset.act === "sub") subEntry(row, id, refresh);
  });
  container.addEventListener("dblclick", e => { const row = e.target.closest(".task"); if (row && e.target.closest(".txt")) editTask(row, refresh); });
  container.addEventListener("contextmenu", e => {
    const row = e.target.closest(".task"); if (!row) return;
    e.preventDefault();
    const id = row.dataset.id; const { t, list, iso, parent } = findTask(id); if (!t) return;
    const next = isoOf(addDays(parseIso(iso), 1));
    const items = [["Edit", () => editTask(row, refresh)]];
    if (!parent) {
      items.push(["Add sub-task", () => subEntry(row, id, refresh)]);
      if (list.indexOf(t) > 0) items.push(["Indent under task above", () => {
        const above = list[list.indexOf(t) - 1]; list.splice(list.indexOf(t), 1);
        (above.children = above.children || []).push({ id: t.id, text: t.text, done: t.done }, ...(t.children || []));
        save(); refresh(iso);
      }]);
      items.push("-", ["Move to next day", () => { list.splice(list.indexOf(t), 1); (D.days[next] = D.days[next] || []).push(t); save(); refresh(iso); refresh(next); }]);
      if (iso !== todayIso()) items.push(["Move to today", () => { const td = todayIso(); list.splice(list.indexOf(t), 1); (D.days[td] = D.days[td] || []).push(t); save(); refresh(iso); refresh(td); }]);
    } else {
      items.push(["Make it a main task", () => { list.splice(list.indexOf(t), 1); const day = D.days[iso]; day.splice(day.indexOf(parent) + 1, 0, { ...t, children: [] }); save(); refresh(iso); }]);
    }
    items.push("-", ["Delete", () => { deleteTask(id); refresh(iso); }]);
    showMenu(e.clientX, e.clientY, items);
  });
}
function editTask(row, refresh) {
  const { t, iso } = findTask(row.dataset.id); if (!t) return;
  const txt = $(".txt", row);
  const input = h(`<input class="edit" value="${esc(t.text)}">`);
  txt.replaceWith(input); input.focus(); input.select();
  let done = false;
  const finish = ok => { if (done) return; done = true; if (ok && input.value.trim()) { t.text = input.value.trim(); save(); } refresh(iso); };
  input.addEventListener("keydown", e => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
  input.addEventListener("blur", () => finish(true));
}
function subEntry(row, id, refresh) {
  const { t, iso } = findTask(id); if (!t) return;
  let after = row; while (after.nextElementSibling && after.nextElementSibling.classList.contains("sub")) after = after.nextElementSibling;
  const box = h(`<div class="task sub"><span class="label">↳</span><input placeholder="Add a sub-task..."></div>`);
  after.after(box);
  const input = $("input", box); input.focus();
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && input.value.trim()) {
      (t.children = t.children || []).push({ id: newId(), text: input.value.trim(), done: false }); t.done = false; save();
      refresh(iso);
      const again = document.querySelector(`.task[data-id="${id}"]`); if (again) subEntry(again, id, refresh);
    }
    if (e.key === "Escape") box.remove();
  });
  input.addEventListener("blur", () => setTimeout(() => { if (!input.value.trim()) box.remove(); }, 120));
}

// ---------------------------------------------------------------- AT A GLANCE
function cityKey(c) { return `${c.lat.toFixed(3)},${c.lon.toFixed(3)}`; }
function cities() { if (!S.cities || !S.cities.length) S.cities = DEFAULT_CITIES.map(c => ({ ...c })); return S.cities.slice(0, 2); }
function selCity() { const cs = cities(); const i = Math.min(+S.wx_city || 0, cs.length - 1); return [i, cs[i]]; }
const units = () => S.units || "F";
const toUnit = c => c == null ? "–" : `${Math.round(units() === "F" ? c * 9 / 5 + 32 : c)}°`;
const speed = mph => mph == null ? "–" : units() === "F" ? `${Math.round(mph)} mph` : `${Math.round(mph * 1.609)} km/h`;
const cache = () => (D.cache = D.cache || {});
const wxFor = c => ((cache().weather || {})[cityKey(c)]);

function buildGlance() {
  const page = newPage("glance");
  const now = new Date();
  ui.cal = ui.cal || { y: now.getFullYear(), m: now.getMonth(), sel: isoOf(now) };
  $(".page-inner", page).innerHTML = `
    <div class="date" data-g="date"></div>
    <div class="clock"><span data-g="clock"></span><span class="ampm" data-g="ampm"></span></div>
    <div class="info"><span class="label" data-g="sun"></span>${segHTML("clock", [["12", "12h"], ["24", "24h"]], h24() ? "24" : "12", "small")}</div>
    <div class="tiles" data-g="tiles"></div>
    <div class="card" data-g="weather"></div>
    <div class="card" data-g="calendar">
      <div class="cal-head"><div class="cal-title" data-g="calTitle"></div>
        <div class="cal-nav"><button class="btn ghost" data-cal="today">Today</button><button class="chev" data-cal="-1">‹</button><button class="chev" data-cal="1">›</button></div></div>
      <div class="line" style="margin:12px 0 10px"></div>
      <div class="cal-viewport" data-g="calVp"></div>
      <div class="line"></div>
      <div data-g="calDetail"></div>
    </div>
    <div class="card" data-g="week"></div>`;
  for (const el of $$("[data-g]", page)) g[el.dataset.g] = el;
  g.page = page;
  renderClock(); renderTiles(); renderWeather(); calRender(0); renderWeek();

  $('[data-seg="clock"]', page).addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    S.clock24 = b.dataset.v === "24"; save(); setSeg(b.parentElement, b.dataset.v);
    renderClock(); fitClock(); renderTiles(); renderWeatherHours(); renderCalDetail(); renderWeek();
  });
  $(".cal-nav", page).addEventListener("click", e => {
    const b = e.target.closest("[data-cal]"); if (!b) return;
    if (b.dataset.cal === "today") calToday(); else calShift(+b.dataset.cal);
  });
  wireCalendarSwipe(g.calVp);
  wireTasks(g.calDetail, () => { renderCalDetail(); renderTiles(); renderWeek(); markBusy(); });
  wireTasks(g.tiles, () => {});
  g.tiles.addEventListener("click", e => {
    const t = e.target.closest("[data-tile]"); if (!t) return;
    if (t.dataset.tile === "tasks") showTab("todo"); else if (!S.ics_url) connectCalendar();
  });
  return page;
}
function afterGlanceMount() {
  placePill($('[data-seg="clock"]', g.page), false);
  const ws = $('[data-seg="city"]', g.page); if (ws) placePill(ws, false);
  fitClock();
  new ResizeObserver(() => fitClock()).observe(g.page);
  refreshOnline();
}

function renderClock() {
  if (!g.clock) return;
  const now = new Date();
  const hh = h24() ? pad2(now.getHours()) : pad2(now.getHours() % 12 || 12);
  g.clock.textContent = `${hh}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`;
  g.ampm.textContent = h24() ? "" : (now.getHours() < 12 ? "AM" : "PM");
  g.date.textContent = longDate(now);
  const w = wxFor(selCity()[1]);
  if (w && w.sunrise) {
    const sr = parseLocal(w.sunrise), ss = parseLocal(w.sunset); const mins = Math.round((ss - sr) / 60000);
    g.sun.textContent = `Sun  ${fmtTime(sr)} – ${fmtTime(ss)}  (${Math.floor(mins / 60)}h ${pad2(mins % 60)}m)`;
  } else g.sun.textContent = "";
}
function fitClock() {
  if (!g.clock) return;
  const avail = g.clock.parentElement.clientWidth - (g.ampm.textContent ? g.ampm.offsetWidth + 8 : 0);
  g.clock.style.fontSize = "100px";
  const w = g.clock.getBoundingClientRect().width;
  g.clock.style.fontSize = Math.min(150, Math.floor(100 * avail / w * 0.995)) + "px";
}

function nextEvent() {
  if (!S.ics_url) return ["Connect Outlook", "See your meetings here"];
  if (!cache().events) return ["Loading…", "Fetching your calendar"];
  const now = new Date();
  const up = cache().events.filter(e => parseLocal(e.end) > now);
  const timed = up.filter(e => !e.all_day);
  if (!up.length) return ["All clear", "No meetings coming up"];
  const e = (timed.length ? timed : up)[0]; const s = parseLocal(e.start), en = parseLocal(e.end);
  let when;
  if (e.all_day) when = "All day";
  else if (s <= now) when = `Now · until ${fmtTime(en)}`;
  else if (sameDay(s, now)) { const m = Math.floor((s - now) / 60000); when = m < 60 ? `${fmtTime(s)} · in ${m} min` : `Today · ${fmtTime(s)}`; }
  else if (sameDay(s, addDays(now, 1))) when = `Tomorrow · ${fmtTime(s)}`;
  else when = `${DAYS[s.getDay()]} · ${fmtTime(s)}`;
  return [e.title, when];
}
function renderTiles() {
  if (!g.tiles) return;
  const [title, when] = nextEvent();
  const tasks = D.days[todayIso()] || []; const left = tasks.filter(t => !t.done).length;
  g.tiles.innerHTML = `
    <div class="card tile-orange" data-tile="next"><div class="label">Up next</div><div class="tile-title">${esc(title)}</div><div class="label">${esc(when)}</div></div>
    <div class="card tile-dark" data-tile="tasks"><div class="label">Tasks today</div><div class="big-num">${left}</div><div class="label">${tasks.length ? `left of ${tasks.length}` : "Nothing planned"}</div></div>`;
}

function renderWeather() {
  if (!g.weather) return;
  const [sel, city] = selCity(); const w = wxFor(city);
  const short = n => n.length <= 16 ? n : n.slice(0, 15) + "…";
  const head = `<div class="row">${segHTML("city", cities().map((c, i) => [String(i), short(c.name)]), String(sel), "small")}
    <div class="grow"></div><button class="more" data-wx="more">···</button></div>
    <div class="label" style="margin-top:16px">${esc([city.name, city.region].filter(Boolean).join(", "))}</div>`;
  let body;
  if (!w) body = `<div class="label" style="margin-top:10px">${cache().weather_error ? "Weather unavailable" : "Loading weather…"}</div>`;
  else {
    const [desc, kind] = WX[w.code] || ["", "cloud"];
    const uv = w.uv == null ? "–" : w.uv < 3 ? "Low" : w.uv < 6 ? "Mod." : w.uv < 8 ? "High" : w.uv < 11 ? "V. high" : "Extreme";
    const dir = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round((w.wind_dir || 0) / 45) % 8];
    body = `<div class="row"><div class="temp">${toUnit(w.temp)}<sup>${units()}</sup></div><div class="grow"></div>${wxIcon(kind, w.is_day)}</div>
      <div>${esc(desc)}</div>
      <div class="label">Feels like ${toUnit(w.feels)} &nbsp;·&nbsp; H ${toUnit(w.hi)} &nbsp;L ${toUnit(w.lo)}</div>
      ${w.humidity == null ? "" : `<div class="line"></div><div class="details">
        <div class="label">Humidity<b style="color:var(--text)">${Math.round(w.humidity)}%</b></div>
        <div class="label">Wind<b style="color:var(--text)">${speed(w.wind)} ${dir}</b></div>
        <div class="label">Rain<b style="color:var(--text)">${Math.round(w.pop || 0)}%</b></div>
        <div class="label">UV<b style="color:var(--text)">${uv}</b></div></div>`}
      <div data-g2="hours"></div>`;
  }
  g.weather.innerHTML = head + `<div data-g2="wxbody">${body}</div>`;
  placePill($('[data-seg="city"]', g.weather), false);
  renderWeatherHours();
  $('[data-seg="city"]', g.weather).addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b || b.classList.contains("on")) return;
    S.wx_city = +b.dataset.v; save(); setSeg(b.parentElement, b.dataset.v);
    const bodyEl = $('[data-g2="wxbody"]', g.weather);
    bodyEl.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, easing: EASE }).onfinish = () => {
      setTimeout(() => { renderWeather(); renderClock(); const nb = $('[data-g2="wxbody"]', g.weather); nb.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 260, easing: EASE }); }, 0);
    };
    refreshOnline();
  });
  $('[data-wx="more"]', g.weather).onclick = e => {
    const r = e.target.getBoundingClientRect();
    showMenu(r.left - 150, r.bottom + 4, [
      ["Change city…", () => changeCity(selCity()[0])],
      [`Show °${units() === "F" ? "C" : "F"}`, () => { S.units = units() === "F" ? "C" : "F"; save(); renderWeather(); }],
      "-", ["Refresh weather", () => refreshOnline(true)],
    ]);
  };
}
function renderWeatherHours() {
  const box = g.weather && $('[data-g2="hours"]', g.weather); if (!box) return;
  const w = wxFor(selCity()[1]); const hours = (w && w.hourly) || [];
  box.innerHTML = hours.length ? `<div class="line"></div><div class="hours">${hours.slice(0, 6).map(x => {
    const t = parseLocal(x.t); const lbl = h24() ? `${pad2(t.getHours())}:00` : `${t.getHours() % 12 || 12}${t.getHours() < 12 ? "am" : "pm"}`;
    return `<div><div class="label">${lbl}</div>${wxIcon((WX[x.code] || ["", "cloud"])[1], x.is_day)}<b>${toUnit(x.temp)}</b></div>`;
  }).join("")}</div>` : "";
}

// calendar ---------------------------------------------------------------------------
function eventsOn(d) {
  if (!S.ics_url) return [];
  return (cache().events || []).filter(e => {
    const s = parseLocal(e.start), en = parseLocal(e.end);
    const sd = parseIso(e.start), ed = parseIso(e.end);
    return sameDay(s, d) || (sd < d && d < ed) || (sd < d && sameDay(ed, d) && (en.getHours() || en.getMinutes()));
  });
}
function calTitleHTML(y, m) {
  const now = new Date(); const cur = y === now.getFullYear() && m === now.getMonth();
  return `<div class="${cur ? "current" : ""}"><div class="month">${MONTHS[m].slice(0, 3)}</div><div class="year">${y}</div></div>`;
}
function calGridHTML(y, m) {
  const first = new Date(y, m, 1); const lead = (first.getDay() + 6) % 7; const n = new Date(y, m + 1, 0).getDate();
  const today = todayIso(); let cells = "";
  for (let i = 0; i < lead; i++) cells += "<span></span>";
  for (let d = 1; d <= n; d++) {
    const iso = `${y}-${pad2(m + 1)}-${pad2(d)}`;
    cells += `<button class="day ${iso === today ? "today" : ""} ${iso === ui.cal.sel ? "sel" : ""}" data-day="${iso}">${d}</button>`;
  }
  return `<div class="cal-grid">${"MTWTFSS".split("").map(c => `<div class="wd">${c}</div>`).join("")}${cells}</div>`;
}
function markBusy() {}
function slideIn(box, html, dir, dist) {
  // finish anything still moving, then slide the old content out and the new content in
  box.getAnimations({ subtree: true }).forEach(a => a.cancel());
  const keep = box.lastElementChild;
  [...box.children].forEach(c => { if (c !== keep) c.remove(); });
  if (keep) { keep.style.position = ""; keep.style.inset = ""; }
  box.style.height = "";
  const next = h(html);
  if (!dir || !keep) { box.replaceChildren(next); return; }
  const h0 = box.offsetHeight;
  box.style.height = h0 + "px";
  next.style.position = "absolute"; next.style.inset = "0 0 auto 0";
  box.appendChild(next);
  const h1 = next.offsetHeight;
  requestAnimationFrame(() => { box.style.height = h1 + "px"; });
  const o = { duration: 420, easing: EASE };
  keep.animate([{ transform: "none", opacity: 1 }, { transform: `translateX(${-dir * dist}px)`, opacity: 0 }], { ...o, fill: "forwards" })
    .onfinish = () => { keep.remove(); next.style.position = ""; next.style.inset = ""; box.style.height = ""; };
  next.animate([{ transform: `translateX(${dir * dist}px)`, opacity: 0 }, { transform: "none", opacity: 1 }], o);
}
function calRender(dir) {
  const { y, m } = ui.cal;
  slideIn(g.calTitle, calTitleHTML(y, m), dir, 36);
  slideIn(g.calVp, calGridHTML(y, m), dir, Math.max(120, g.calVp.offsetWidth * 0.55));
  renderCalDetail();
}
function calShift(delta) {
  let { y, m } = ui.cal; m += delta; if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; }
  ui.cal.y = y; ui.cal.m = m; calRender(delta);
}
function calToday() {
  const now = new Date(); const target = now.getFullYear() * 12 + now.getMonth(); const cur = ui.cal.y * 12 + ui.cal.m;
  ui.cal = { y: now.getFullYear(), m: now.getMonth(), sel: isoOf(now) };
  if (target === cur) { selectDay(ui.cal.sel); return; }
  calRender(target > cur ? 1 : -1);
}
function selectDay(iso) {
  ui.cal.sel = iso;
  $$(".day", g.calVp).forEach(b => b.classList.toggle("sel", b.dataset.day === iso));
  renderCalDetail(true);
}
function wireCalendarSwipe(vp) {
  let x0 = null, moved = false, wheelAcc = 0, wheelLock = 0;
  vp.addEventListener("pointerdown", e => { x0 = e.clientX; moved = false; });
  vp.addEventListener("pointermove", e => { if (x0 != null && Math.abs(e.clientX - x0) > 6) moved = true; });
  vp.addEventListener("pointerup", e => {
    const dx = x0 == null ? 0 : e.clientX - x0; x0 = null;
    if (dx > 40) calShift(-1); else if (dx < -40) calShift(1);
  });
  vp.addEventListener("click", e => { const b = e.target.closest(".day"); if (b && !moved) selectDay(b.dataset.day); });
  vp.addEventListener("wheel", e => {            // two-finger sideways swipe on a touchpad
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault(); wheelAcc += e.deltaX;
    if (Date.now() > wheelLock && Math.abs(wheelAcc) > 60) { calShift(wheelAcc > 0 ? 1 : -1); wheelAcc = 0; wheelLock = Date.now() + 450; }
  }, { passive: false });
}
function renderCalDetail(animate = false) {
  if (!g.calDetail) return;
  const d = parseIso(ui.cal.sel); const iso = ui.cal.sel;
  const evs = eventsOn(d); const tasks = D.days[iso] || [];
  g.calDetail.innerHTML = `<div class="detail-day">${longDate(d)}${iso === todayIso() ? " · Today" : ""}</div>
    ${evs.map(e => { const s = parseLocal(e.start); return `<div class="ev"><div class="t">${e.all_day || !sameDay(s, d) ? "All day" : fmtTime(s)}</div><div class="grow">${esc(e.title)}</div></div>`; }).join("")}
    ${tasksHTML(tasks)}
    ${!evs.length && !tasks.length ? '<div class="label">Nothing planned.</div>' : ""}
    <div class="add"><input placeholder="Add a task for this day…" data-add></div>`;
  $("[data-add]", g.calDetail).addEventListener("keydown", e => {
    if (e.key === "Enter" && e.target.value.trim()) { addTask(iso, e.target.value.trim()); renderCalDetail(); renderTiles(); renderWeek(); $("[data-add]", g.calDetail).focus(); }
  });
  if (animate) g.calDetail.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 240, easing: EASE });
}
function renderWeek() {
  if (!g.week) return;
  const now = new Date(); const url = S.ics_url;
  const evs = url ? (cache().events || []).filter(e => parseLocal(e.end) > now && parseLocal(e.start) < addDays(now, 7)) : [];
  const todayN = evs.filter(e => sameDay(parseLocal(e.start), now)).length;
  const tasksLeft = (D.days[todayIso()] || []).filter(t => !t.done).length;
  const brief = (url ? `Today: ${todayN} event${todayN === 1 ? "" : "s"} · ` : "Today: ") + `${tasksLeft} task${tasksLeft === 1 ? "" : "s"} left`;
  let body = "";
  if (!url) body = `<div>See your upcoming Outlook meetings here.</div><button class="btn" style="margin-top:12px" data-connect>Connect Outlook</button>`;
  else {
    if (cache().events_error) body += `<div class="label" style="color:var(--accent-text)">Couldn't refresh the calendar — showing the last saved events.</div>`;
    if (!evs.length) body += `<div class="label">${cache().events ? "Nothing scheduled for the next week." : "Loading calendar…"}</div>`;
    let shown = null;
    for (const e of evs.slice(0, 5)) {
      const s = parseLocal(e.start), en = parseLocal(e.end); const d = s > now ? s : now;
      const key = isoOf(d);
      if (key !== shown) { shown = key; body += `<div class="group">${sameDay(d, now) ? "Today" : sameDay(d, addDays(now, 1)) ? "Tomorrow" : `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}`}</div>`; }
      const live = s <= now && now < en;
      body += `<div class="ev"><div class="t ${live ? "now" : ""}">${e.all_day ? "All day" : live ? "Now" : fmtTime(s)}</div><div class="grow">${esc(e.title)}${e.location ? `<div class="loc">${esc(e.location)}</div>` : ""}</div></div>`;
    }
  }
  g.week.innerHTML = `<div class="row"><div class="card-title grow">This week</div>${url ? '<button class="more" data-cal-more>···</button>' : ""}</div>
    <div class="label" style="margin:2px 0 10px">${brief}</div>${body}`;
  const c = $("[data-connect]", g.week); if (c) c.onclick = connectCalendar;
  const m = $("[data-cal-more]", g.week);
  if (m) m.onclick = e => { const r = e.target.getBoundingClientRect(); showMenu(r.left - 160, r.bottom + 4, [
    ["Refresh calendar", () => refreshOnline(true)], ["Change calendar link…", connectCalendar],
    "-", ["Disconnect calendar", () => { delete S.ics_url; delete cache().events; delete cache().events_fetched; delete cache().events_error; save(); renderWeek(); renderTiles(); renderCalDetail(); }]]); };
}

// online refresh ---------------------------------------------------------------------
const stale = (stamp, min) => !stamp || (Date.now() - parseLocal(stamp)) > min * 60000;
function refreshOnline(force = false) {
  for (const c of cities()) {
    const k = cityKey(c); const w = (cache().weather || {})[k];
    if (force || !w || stale(w.fetched, 15) || !w.hourly) {
      call("weather", c.lat, c.lon).then(r => {
        if (!r) return;
        cache().weather = cache().weather || {};
        if (r.ok) { cache().weather[k] = r.weather; delete cache().weather_error; } else cache().weather_error = r.error;
        save(); renderWeather(); renderClock();
      });
    }
  }
  if (S.ics_url && (force || stale(cache().events_fetched, 10))) {
    call("events", S.ics_url).then(r => {
      if (!r) return;
      if (r.ok) { cache().events = r.events; delete cache().events_error; } else cache().events_error = r.error;
      const n = new Date(); cache().events_fetched = `${isoOf(n)}T${pad2(n.getHours())}:${pad2(n.getMinutes())}:00`;
      save(); renderTiles(); renderWeek(); renderCalDetail();
    });
  }
}

function changeCity(i) {
  const s = openSheet(`<h2>Change city</h2><div class="muted">Type a town or city, e.g. “Aspen, CO”</div>
    <div class="field"><input placeholder="City" data-q></div><div class="muted" data-status></div><div data-results></div>
    <div class="actions"><button class="btn" data-go>Search</button><button class="btn ghost" data-cancel>Cancel</button></div>`);
  const q = $("[data-q]", s.el), status = $("[data-status]", s.el), results = $("[data-results]", s.el);
  const search = () => {
    if (!q.value.trim()) return;
    status.textContent = "Searching…";
    call("geocode", q.value.trim()).then(r => {
      results.innerHTML = "";
      if (!r || !r.ok) { status.textContent = "Couldn't search. Are you online?"; return; }
      if (!r.places.length) { status.textContent = "No places found. Try another spelling."; return; }
      status.textContent = "Choose one:";
      r.places.slice(0, 6).forEach(p => {
        const where = [p.region, p.country].filter(x => x && x !== p.name).join(", ");
        const row = h(`<div class="result">${esc(p.name)} · <span class="muted">${esc(where)}</span></div>`);
        row.onclick = () => { S.cities[i] = { name: p.name, region: p.region, lat: p.lat, lon: p.lon }; save(); s.close(); renderWeather(); refreshOnline(true); };
        results.appendChild(row);
      });
    });
  };
  q.addEventListener("keydown", e => { if (e.key === "Enter") search(); });
  $("[data-go]", s.el).onclick = search; $("[data-cancel]", s.el).onclick = s.close;
  setTimeout(() => q.focus(), 50);
}
function connectCalendar() {
  const s = openSheet(`<h2>Connect Outlook calendar</h2>
    <div class="muted">1. Open your Outlook calendar settings in the browser:</div>
    <a data-url="https://outlook.office.com/calendar/options/calendar/SharedCalendars">Work or school account ↗</a>
    <a data-url="https://outlook.live.com/calendar/0/options/calendar/SharedCalendars">Personal account (Outlook.com / Hotmail) ↗</a>
    <div class="muted" style="margin-top:8px">2. Under “Publish a calendar”, choose your calendar and “Can view all details”, then click Publish.</div>
    <div class="muted" style="margin-top:8px">3. Copy the ICS link and paste it here:</div>
    <div class="field"><input placeholder="https://outlook.office365.com/owa/calendar/…/calendar.ics" data-url-in></div>
    <div class="muted" data-status></div>
    <div class="muted" style="margin-top:6px">The link is saved only on this PC. Anyone who has it can see your calendar, so keep it private.</div>
    <div class="actions"><button class="btn" data-go>Connect</button><button class="btn ghost" data-cancel>Cancel</button></div>`);
  $$("[data-url]", s.el).forEach(a => a.onclick = () => call("open_url", a.dataset.url));
  const input = $("[data-url-in]", s.el), status = $("[data-status]", s.el);
  input.value = S.ics_url || "";
  const go = () => {
    const url = input.value.trim();
    if (!/^(https?|webcal):\/\//i.test(url)) { status.textContent = "Paste the full link (it starts with https://)."; status.style.color = "var(--accent-text)"; return; }
    status.style.color = ""; status.textContent = "Checking the link…";
    call("events", url).then(r => {
      if (!r || !r.ok) { status.style.color = "var(--accent-text)"; status.textContent = `That didn't work: ${r ? r.error : "no connection"}`; return; }
      S.ics_url = url; cache().events = r.events; delete cache().events_error;
      const n = new Date(); cache().events_fetched = `${isoOf(n)}T${pad2(n.getHours())}:${pad2(n.getMinutes())}:00`;
      save(); s.close(); renderTiles(); renderWeek(); renderCalDetail(); toast("Calendar connected");
    });
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  $("[data-go]", s.el).onclick = go; $("[data-cancel]", s.el).onclick = s.close;
  setTimeout(() => input.focus(), 50);
}

// ---------------------------------------------------------------- TO-DO
function buildTodo() {
  const page = newPage("todo");
  const inner = $(".page-inner", page);
  const today = new Date();
  if (ui.todoOpen === null) ui.todoOpen = todayIso();
  let html = "";
  for (let i = 0; i < 7; i++) {
    const d = addDays(today, i); const iso = isoOf(d);
    html += `<div class="band ${iso === ui.todoOpen ? "open" : ""}" style="--i:${i}" data-iso="${iso}">
      <button class="band-head"><span class="dayname">${DAYS[d.getDay()]}</span><span class="count"></span></button>
      <div class="acc"><div><div class="acc-body"></div></div></div></div>`;
  }
  html += `<div class="band todo-fill" style="--i:6"></div>`;
  inner.innerHTML = html;
  $$(".band[data-iso]", inner).forEach(b => renderBand(b.dataset.iso, inner));
  inner.addEventListener("click", e => {
    const head = e.target.closest(".band-head"); if (!head) return;
    const band = head.parentElement; const iso = band.dataset.iso;
    const opening = !band.classList.contains("open");
    $$(".band.open", inner).forEach(b => b.classList.remove("open"));
    if (opening) band.classList.add("open");
    ui.todoOpen = opening ? iso : "";
  });
  wireTasks(inner, iso => renderBand(iso, inner));
  return page;
}
function renderBand(iso, root = document) {
  const band = $(`.band[data-iso="${iso}"]`, root); if (!band) return;
  const d = parseIso(iso); const i = Math.round((d - parseIso(todayIso())) / 86400000);
  const tasks = D.days[iso] || []; const left = tasks.filter(t => !t.done).length;
  $(".count", band).textContent = left || "";
  const sub = i === 0 ? `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()} — ${fmtTime(new Date())}`
    : `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}${i === 1 ? " — Tomorrow" : ""}`;
  const body = $(".acc-body", band);
  body.innerHTML = `<div class="band-sub" ${i === 0 ? "data-today-line" : ""}>${sub}</div>${tasksHTML(tasks)}
    <div class="add"><input placeholder="Add a new task…" data-add></div>`;
  $("[data-add]", body).addEventListener("keydown", e => {
    if (e.key === "Enter" && e.target.value.trim()) { addTask(iso, e.target.value.trim()); renderBand(iso, root); $(`.band[data-iso="${iso}"] [data-add]`, root).focus(); }
    if (e.key === "Escape") e.target.blur();
  });
}

// ---------------------------------------------------------------- NOTES
const plain = html => { const d = document.createElement("div"); d.innerHTML = (html || "").replace(/<\/(div|h3|li|p)>|<br\s*\/?>/gi, " "); return d.textContent.replace(/\s+/g, " ").trim(); };
function whenLabel(stamp) {
  if (!stamp) return ""; const d = parseLocal(stamp);
  return sameDay(d, new Date()) ? fmtTime(d) : `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}`;
}
function stamp() { const n = new Date(); return `${isoOf(n)}T${pad2(n.getHours())}:${pad2(n.getMinutes())}:${pad2(n.getSeconds())}`; }
function buildNotes() {
  const page = newPage("notes");
  const notes = [...D.notes].sort((a, b) => (b.updated || "").localeCompare(a.updated || ""));
  $(".page-inner", page).innerHTML = `<div class="notes-head"><div class="h1">NOTES</div><button class="btn" data-new>+ New</button></div>
    ${notes.length ? notes.map(n => `<div class="card note-card" data-note="${n.id}"><button class="x" data-del>&times;</button>
      <div class="row"><div class="note-title grow">${esc(n.title || "Untitled")}</div><div class="label" style="margin-right:22px">${whenLabel(n.updated)}</div></div>
      <div class="note-prev">${esc(plain(n.html) || "Empty note")}</div></div>`).join("") : '<div class="empty">No notes yet.<br>Click + New to write one.</div>'}`;
  page.addEventListener("click", e => {
    if (e.target.closest("[data-new]")) {
      const n = { id: newId(), title: "", html: "", updated: stamp() }; D.notes.push(n); save(); openNote(n.id, true); return;
    }
    const card = e.target.closest("[data-note]"); if (!card) return;
    const n = D.notes.find(x => x.id === card.dataset.note);
    if (e.target.closest("[data-del]")) {
      confirmSheet("Delete note?", `“${n.title || "Untitled"}” will be removed.`, "Delete", () => {
        D.notes.splice(D.notes.indexOf(n), 1); save();
        card.animate([{ opacity: 1 }, { opacity: 0, transform: "scale(.97)" }], { duration: 200, easing: EASE }).onfinish = () => card.remove();
      });
      return;
    }
    openNote(n.id);
  });
  return page;
}
function openNote(id, focusTitle = false) {
  ui.noteId = id; S.open_note = id;
  const page = buildEditor(focusTitle);
  swapPage(page, 1);
}
function closeNote() {
  flushNote();
  ui.noteId = null; S.open_note = null;
  swapPage(buildNotes(), -1);
}
let noteTimer = null;
function flushNote() { if (noteTimer) { clearTimeout(noteTimer); noteTimer = null; save(true); } }
function buildEditor(focusTitle = false) {
  const n = D.notes.find(x => x.id === ui.noteId);
  if (!n) { ui.noteId = null; return buildNotes(); }
  const page = newPage("editor");
  $(".page-inner", page).innerHTML = `<div class="editor-bar"><button class="back" data-back>‹ &nbsp;All notes</button>
      <button class="tool" data-cmd="bold" title="Bold (Ctrl+B)">B</button><button class="tool" data-cmd="h3" title="Heading">H</button>
      <button class="tool" data-cmd="list" title="Bullet list">•≡</button></div>
    <input class="note-title-input" placeholder="Title" value="${esc(n.title)}">
    <div class="note-body" contenteditable="true">${n.html || ""}</div>`;
  const title = $(".note-title-input", page), body = $(".note-body", page);
  const changed = () => { n.title = title.value.trim(); n.html = body.innerHTML; n.updated = stamp(); clearTimeout(noteTimer); noteTimer = setTimeout(() => { noteTimer = null; save(true); }, 400); };
  title.addEventListener("input", changed);
  title.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); body.focus(); } });
  body.addEventListener("input", changed);
  const tools = () => {
    $$(".tool", page).forEach(t => {
      const c = t.dataset.cmd;
      const on = c === "bold" ? document.queryCommandState("bold") : c === "list" ? document.queryCommandState("insertUnorderedList")
        : String(document.queryCommandValue("formatBlock")).toLowerCase() === "h3";
      t.classList.toggle("on", on && document.activeElement === body);
    });
  };
  document.addEventListener("selectionchange", tools);
  $(".editor-bar", page).addEventListener("mousedown", e => { if (e.target.closest(".tool")) e.preventDefault(); });
  $(".editor-bar", page).addEventListener("click", e => {
    if (e.target.closest("[data-back]")) { closeNote(); return; }
    const t = e.target.closest(".tool"); if (!t) return;
    body.focus();
    if (t.dataset.cmd === "bold") document.execCommand("bold");
    if (t.dataset.cmd === "list") document.execCommand("insertUnorderedList");
    if (t.dataset.cmd === "h3") document.execCommand("formatBlock", false, String(document.queryCommandValue("formatBlock")).toLowerCase() === "h3" ? "div" : "h3");
    changed(); tools();
  });
  setTimeout(() => { if (focusTitle) title.focus(); }, 380);
  return page;
}

// ---------------------------------------------------------------- window chrome
function wireChrome() {
  $("#tabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b && b.dataset.tab !== ui.tab) showTab(b.dataset.tab); });
  $("#theme").onclick = toggleTheme;
  $("#pin").onclick = () => { S.on_top = !S.on_top; $("#pin").classList.toggle("on", !!S.on_top); call("set_on_top", !!S.on_top); save(); };
  $("#close").onclick = async () => { flushNote(); await save(true); call("close"); };
  $(".topbar").addEventListener("contextmenu", e => {
    e.preventDefault();
    showMenu(e.clientX, e.clientY, [
      [(S.on_top ? "✓ " : "") + "Keep on top", () => $("#pin").click()],
      [S.theme === "light" ? "Dark mode" : "Light mode", toggleTheme],
      "-", ["Export backup…", async () => { await save(true); const r = await call("export_backup"); if (r && r.ok) toast("Backup saved"); else if (r && r.error) toast(r.error); }],
      ["Import backup…", async () => {
        const r = await call("import_backup"); if (!r || !r.ok) { if (r && r.error) toast(r.error); return; }
        const n = Object.values(r.data.days).reduce((a, l) => a + l.length, 0);
        confirmSheet("Import backup?", `Replace your current tasks and notes with this backup (${n} tasks, ${r.data.notes.length} notes)?`, "Replace", () => {
          r.data.settings.window = S.window; D = r.data; S = D.settings; save(true); applyTheme(); ui.noteId = null; showTab(ui.tab, false); toast("Backup imported");
        });
      }],
      "-", ["Close DeskTodo", () => $("#close").click()],
    ]);
  });
  document.addEventListener("keydown", e => {
    if (!e.ctrlKey) return;
    if (["1", "2", "3"].includes(e.key)) { e.preventDefault(); const t = TABS[+e.key - 1]; if (t !== ui.tab) showTab(t); }
    if (e.key.toLowerCase() === "t") { e.preventDefault(); $("#pin").click(); }
  });
  document.addEventListener("contextmenu", e => { if (!e.target.closest("input, [contenteditable]")) e.preventDefault(); });

  // resize from the corner grip
  const grip = $("#grip");
  grip.addEventListener("pointerdown", e => {
    grip.setPointerCapture(e.pointerId);
    const sx = e.screenX, sy = e.screenY, w0 = innerWidth, h0 = innerHeight; let raf = 0, last = null;
    call("report_size", innerWidth);
    const move = ev => { last = [w0 + ev.screenX - sx, h0 + ev.screenY - sy]; if (!raf) raf = requestAnimationFrame(() => { raf = 0; call("resize", ...last); }); };
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); };
    grip.addEventListener("pointermove", move); grip.addEventListener("pointerup", up);
  });
}

// ---------------------------------------------------------------- clock tick & day change
let lastDay = null;
function tick() {
  const today = todayIso();
  if (lastDay && today !== lastDay) {           // midnight (or waking from sleep on a new day)
    rollOver(); save(); ui.todoOpen = today; ui.cal = null; showTab(ui.tab, false);
  }
  lastDay = today;
  if (ui.tab === "glance") renderClock();
  const tl = $("[data-today-line]");
  if (tl) { const d = new Date(); tl.textContent = `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()} — ${fmtTime(d)}`; }
  setTimeout(tick, 1000 - (Date.now() % 1000) + 5);
}

// ---------------------------------------------------------------- start
async function start() {
  const st = await call("get_state");
  D = st.data; S = D.settings = D.settings || {};
  D.days = D.days || {}; D.notes = D.notes || [];
  ui.smoke = !!st.smoke;
  if (rollOver()) save();
  ui.noteId = S.open_note && D.notes.some(n => n.id === S.open_note) ? S.open_note : null;
  applyTheme();
  $("#pin").classList.toggle("on", !!S.on_top);
  wireChrome();
  ui.tab = "glance";
  setSeg($("#tabs"), "glance"); placePill($("#tabs"), false);
  showTab("glance", false);
  document.fonts.ready.then(() => { placePill($("#tabs"), false); fitClock(); });
  tick();
  setInterval(() => { if (ui.tab === "glance") refreshOnline(); }, 5 * 60000);
  window.addEventListener("resize", () => placePill($("#tabs"), false));
  call("report_size", innerWidth);
  if (ui.smoke) setTimeout(() => call("smoke", {
    ok: !!$(".clock span").textContent, ua: navigator.userAgent,
    viewTransitions: !!document.startViewTransition, colorMix: CSS.supports("color", "color-mix(in srgb, red, blue)"),
  }), 1500);
}
if (api()) start(); else window.addEventListener("pywebviewready", start, { once: true });
