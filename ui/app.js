/* DeskTodo interface. Data lives in Python (core.py); this file draws the UI and animates it.
   All motion uses transform / opacity (GPU-composited), so it stays smooth in WebView2. */
"use strict";
// report interface errors to Python (written to the log in test mode)
window.addEventListener("error", e => { try { window.pywebview && window.pywebview.api.log(`${e.message} @ ${e.filename}:${e.lineno}`); } catch (_) {} });
window.addEventListener("unhandledrejection", e => { try { window.pywebview && window.pywebview.api.log(`Promise: ${e.reason}`); } catch (_) {} });

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
  gear: '<svg viewBox="0 0 14 14"><circle cx="7" cy="7" r="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7 1.2l1 1.6 1.8-.5.5 1.8 1.6 1-1 1.6 1 1.6-1.6 1-.5 1.8-1.8-.5-1 1.6-1-1.6-1.8.5-.5-1.8-1.6-1 1-1.6-1-1.6 1.6-1 .5-1.8 1.8.5z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
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
const ACCENTS = [["#f26b1d", "Orange"], ["#f5a524", "Amber"], ["#f2c230", "Yellow"], ["#e5484d", "Red"], ["#e93d82", "Pink"],
  ["#8e4ec6", "Violet"], ["#3e63dd", "Blue"], ["#0d9bb5", "Teal"], ["#30a46c", "Green"], ["#8b8d98", "Graphite"]];
function applyAccent() {
  const c = /^#[0-9a-f]{6}$/i.test(S.accent || "") ? S.accent : ACCENTS[0][0];
  const [r, gg, b] = [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  const lum = .2126 * r + .7152 * gg + .0722 * b;            // light accents get dark text on top of them
  const st = document.documentElement.style;
  st.setProperty("--accent", c);
  st.setProperty("--on-accent", lum > .45 ? "#141414" : "#ffffff");
  st.setProperty("--accent-shade", lum > .45 ? "58%" : lum > .28 ? "74%" : "86%");   // keeps accent text readable on light grey
}
function applyTheme() {
  document.documentElement.classList.toggle("dark", S.theme !== "light");
  applyAccent();
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
function openSettings() {
  const cur = () => (S.accent || ACCENTS[0][0]).toLowerCase();
  const custom = () => !ACCENTS.some(([c]) => c === cur());
  const s = openSheet(`<h2>Settings</h2>
    <div class="set-label">Accent color</div>
    <div class="swatches" data-sw>${ACCENTS.map(([c, n]) => `<button class="sw" style="--c:${c}" data-c="${c}" title="${n}" aria-label="${n}"></button>`).join("")}
      <label class="sw custom" title="Pick any color" aria-label="Pick any color"><input type="color" data-pick></label></div>
    <div class="set-label">Clock</div>
    <div class="set-row">${segHTML("set-face", [["digital", "Digital"], ["analog", "Analog"]], S.clock_face === "analog" ? "analog" : "digital", "small")}
      ${segHTML("set-24", [["12", "12h"], ["24", "24h"]], h24() ? "24" : "12", "small")}</div>
    <div class="actions"><button class="btn" data-done>Done</button><button class="btn ghost" data-reset>Reset color</button></div>`);
  const sw = $("[data-sw]", s.el), pick = $("[data-pick]", s.el);
  const mark = () => {
    $$(".sw[data-c]", sw).forEach(b => b.classList.toggle("on", b.dataset.c === cur()));
    const cu = $(".sw.custom", sw); cu.classList.toggle("on", custom()); cu.style.setProperty("--c", custom() ? cur() : "transparent");
    pick.value = cur();
  };
  const set = c => { S.accent = c; applyAccent(); mark(); save(); };
  sw.addEventListener("click", e => { const b = e.target.closest("[data-c]"); if (b) set(b.dataset.c); });
  pick.addEventListener("input", () => set(pick.value.toLowerCase()));
  $('[data-seg="set-face"]', s.el).addEventListener("click", e => {
    const b = e.target.closest("button"); if (b) { setSeg(b.parentElement, b.dataset.v); setClockFace(b.dataset.v); } });
  $('[data-seg="set-24"]', s.el).addEventListener("click", e => {
    const b = e.target.closest("button"); if (b) { setSeg(b.parentElement, b.dataset.v); set24(b.dataset.v === "24"); } });
  $("[data-done]", s.el).onclick = s.close;
  $("[data-reset]", s.el).onclick = () => { delete S.accent; applyAccent(); mark(); save(); };
  mark();
  requestAnimationFrame(() => $$(".seg", s.el).forEach(x => placePill(x, false)));
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
    <div class="clock-wrap" data-g="clockWrap">
      <div class="clock" data-g="clock"><div class="hh"><span data-g="hh"></span><span class="ampm" data-g="ampm"></span></div><div><span data-g="mm"></span></div></div>
      <div class="analog" data-g="analog">${analogHTML()}</div>
    </div>
    <div class="info"><span class="label" data-g="sun"></span><div class="segs">
      ${segHTML("face", [["digital", "Digital"], ["analog", "Analog"]], faceAnalog() ? "analog" : "digital", "small")}
      ${segHTML("clock", [["12", "12h"], ["24", "24h"]], h24() ? "24" : "12", "small")}</div></div>
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
  page.classList.toggle("is-analog", faceAnalog());
  renderClock(); renderTiles(); renderWeather(); calRender(0); renderWeek();

  $('[data-seg="clock"]', page).addEventListener("click", e => {
    const b = e.target.closest("button"); if (b) set24(b.dataset.v === "24");
  });
  $('[data-seg="face"]', page).addEventListener("click", e => {
    const b = e.target.closest("button"); if (b) setClockFace(b.dataset.v);
  });
  $(".cal-nav", page).addEventListener("click", e => {
    const b = e.target.closest("[data-cal]"); if (!b) return;
    if (b.dataset.cal === "today") calToday(); else calShift(+b.dataset.cal);
  });
  wireCalendarSwipe(g.calVp);
  wireTasks(g.tiles, () => {});
  g.tiles.addEventListener("click", e => {
    const t = e.target.closest("[data-tile]"); if (!t) return;
    if (t.dataset.tile === "tasks") showTab("todo"); else if (!hasCal()) connectCalendar();
  });
  return page;
}
function afterGlanceMount() {
  placePill($('[data-seg="clock"]', g.page), false);
  placePill($('[data-seg="face"]', g.page), false);
  const ws = $('[data-seg="city"]', g.page); if (ws) placePill(ws, false);
  fitClock();
  new ResizeObserver(() => fitClock()).observe(g.page);
  refreshOnline();
}

const faceAnalog = () => S.clock_face === "analog";
function set24(on) {
  S.clock24 = on; save();
  if (g.page) { const sg = $('[data-seg="clock"]', g.page); setSeg(sg, on ? "24" : "12"); }
  renderClock(); fitClock(); renderTiles(); renderWeatherHours(); renderCalDetail(); renderWeek();
}
function setClockFace(face) {
  S.clock_face = face === "analog" ? "analog" : "digital"; save();
  if (!g.page) return;
  setSeg($('[data-seg="face"]', g.page), S.clock_face);
  g.page.classList.toggle("is-analog", faceAnalog());
  renderClock(); fitClock();
  g.clockWrap.animate([{ opacity: 0, transform: "scale(.97)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: EASE });
}
function analogHTML() {
  const P = (r, deg) => { const a = deg * Math.PI / 180; return [(100 + r * Math.sin(a)).toFixed(2), (100 - r * Math.cos(a)).toFixed(2)]; };
  let ticks = "", nums = "";
  for (let i = 0; i < 60; i++) {
    if (i % 5 === 0) continue;
    const [x1, y1] = P(87.4, i * 6), [x2, y2] = P(91.15, i * 6);   // short marks, centred on the numerals
    ticks += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
  }
  // the numerals sit in the ring of minute marks, taking the place of the hour marks
  for (let hr = 1; hr <= 12; hr++) { const [x, y] = P(89.3, hr * 30); nums += `<text x="${x}" y="${y}">${hr}</text>`; }
  const hand = (cls, body) => `<svg class="hand ${cls}" viewBox="0 0 200 200" aria-hidden="true">${body}</svg>`;
  return `<svg class="face" viewBox="0 0 200 200" role="img" aria-label="Analog clock">
      <g class="ticks">${ticks}</g><g class="nums">${nums}</g></svg>
    ${hand("h", '<line x1="100" y1="100" x2="100" y2="47"/><line class="lume" x1="100" y1="58" x2="100" y2="49"/>')}
    ${hand("m", '<line x1="100" y1="100" x2="100" y2="17"/><line class="lume" x1="100" y1="30" x2="100" y2="19.5"/>')}
    ${hand("s", '<line class="needle" x1="100" y1="100" x2="100" y2="13"/><line class="tail" x1="100" y1="100" x2="100" y2="117"/><circle cx="100" cy="100" r="5"/><circle class="pin" cx="100" cy="100" r="2"/>')}`;
}
function syncAnalog() {
  // the hands turn with CSS animations (smooth, on the GPU); this lines them up with the real time
  if (!g.analog || !faceAnalog()) return;
  const n = new Date(); const s = n.getSeconds() + n.getMilliseconds() / 1000;
  const m = n.getMinutes() * 60 + s, hr = (n.getHours() % 12) * 3600 + m;
  for (const [cls, t] of [["s", s], ["m", m], ["h", hr]]) $(`.hand.${cls}`, g.analog).style.animationDelay = `-${t.toFixed(3)}s`;
}
function renderClock() {
  if (!g.clock) return;
  const now = new Date();
  const hh = pad2(h24() ? now.getHours() : (now.getHours() % 12 || 12));
  g.hh.textContent = hh; g.mm.textContent = pad2(now.getMinutes());
  g.ampm.textContent = h24() ? "" : (now.getHours() < 12 ? "AM" : "PM");
  if (faceAnalog() && (!g.analogSynced || now.getSeconds() === 0)) { syncAnalog(); g.analogSynced = true; }
  g.date.textContent = longDate(now);
  const w = wxFor(selCity()[1]);
  if (w && w.sunrise) {
    const sr = parseLocal(w.sunrise), ss = parseLocal(w.sunset); const mins = Math.round((ss - sr) / 60000);
    const t = d => `${h24() ? pad2(d.getHours()) : d.getHours() % 12 || 12}:${pad2(d.getMinutes())}`;
    g.sun.textContent = `Sun  ${t(sr)} – ${t(ss)}  (${Math.floor(mins / 60)}h ${pad2(mins % 60)}m)`;
  } else g.sun.textContent = "";
}
function fitClock() {
  if (!g.clock || faceAnalog()) return;
  // two stacked lines, hours over minutes, about half the card wide
  const avail = g.clockWrap.clientWidth;
  g.clock.style.fontSize = "100px";
  const w = Math.max(g.hh.getBoundingClientRect().width, g.mm.getBoundingClientRect().width) || 1;
  g.clock.style.fontSize = Math.max(60, Math.min(168, Math.floor(100 * avail * 0.46 / w))) + "px";
}

function nextEvent() {
  if (!hasCal()) return ["Connect calendar", "See your meetings here"];
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
const calendars = () => S.calendars || (S.calendars = []);
const hasCal = () => calendars().length > 0;
const calLabel = (c, i) => c.name || c.auto || `Calendar ${i + 1}`;
function eventsOn(d) {
  if (!hasCal()) return [];
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
  const evs = eventsOn(d);
  g.calDetail.innerHTML = `<div class="detail-day">${longDate(d)}${iso === todayIso() ? " · Today" : ""}</div>
    ${evs.map(e => { const s = parseLocal(e.start); return `<div class="ev"><div class="t">${e.all_day || !sameDay(s, d) ? "All day" : fmtTime(s)}</div><div class="grow">${esc(e.title)}${e.location ? `<div class="loc">${esc(e.location)}</div>` : ""}</div></div>`; }).join("")}
    ${!evs.length ? `<div class="label">${hasCal() ? "No events." : "Connect a calendar to see your events here."}</div>` : ""}`;
  if (animate) g.calDetail.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 240, easing: EASE });
}
function renderWeek() {
  if (!g.week) return;
  const now = new Date(); const url = hasCal();
  const evs = url ? (cache().events || []).filter(e => parseLocal(e.end) > now && parseLocal(e.start) < addDays(now, 7)) : [];
  const todayN = evs.filter(e => sameDay(parseLocal(e.start), now)).length;
  const tasksLeft = (D.days[todayIso()] || []).filter(t => !t.done).length;
  const brief = (url ? `Today: ${todayN} event${todayN === 1 ? "" : "s"} · ` : "Today: ") + `${tasksLeft} task${tasksLeft === 1 ? "" : "s"} left`;
  let body = "";
  if (!url) body = `<div>See your upcoming meetings from Google Calendar or Outlook here.</div><button class="btn" style="margin-top:12px" data-connect>Connect calendar</button>`;
  else {
    if (cache().events_error) body += `<div class="label" style="color:var(--accent-text)">${esc(cache().events_error)}</div>`;
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
    ["Refresh calendars", () => refreshOnline(true)], ["Calendars…", connectCalendar]]); };
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
  if (hasCal() && (force || stale(cache().events_fetched, 10))) refreshCalendars();
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
let calBusy = null;
function refreshCalendars() {
  if (calBusy) return calBusy;
  const list = calendars().slice();
  calBusy = call("calendars", list.map(c => c.url)).then(r => {
    calBusy = null;
    if (!r || list.length !== calendars().length) return r;   // the list changed meanwhile: next refresh
    const failed = Object.keys(r.errors || {}).map(Number);
    cache().calendar_errors = r.errors || {};
    (r.names || []).forEach((n, i) => { if (n && calendars()[i]) calendars()[i].auto = n; });
    if (r.ok) {
      cache().events = r.events;
      if (failed.length) cache().events_error = failed.length === 1
        ? `Couldn't refresh “${calLabel(calendars()[failed[0]], failed[0])}”.`
        : `Couldn't refresh ${failed.length} calendars.`;
      else delete cache().events_error;
    } else cache().events_error = "Couldn't refresh your calendars — showing the last saved events.";
    const n = new Date(); cache().events_fetched = `${isoOf(n)}T${pad2(n.getHours())}:${pad2(n.getMinutes())}:00`;
    save(); renderTiles(); renderWeek(); renderCalDetail();
    return r;
  }, () => { calBusy = null; });
  return calBusy;
}
function connectCalendar() {
  const s = openSheet(`<h2>Calendars</h2>
    <div class="muted">Add one link per calendar. They're combined into one view.</div>
    <div class="cal-list" data-list></div>
    <div class="field"><input placeholder="Paste a calendar link (ICS)" data-url-in></div>
    <div class="muted" data-status></div>
    <div class="actions"><button class="btn" data-go>Add</button><button class="btn ghost" data-cancel>Done</button></div>
    <details class="howto"><summary>Google Calendar: where to find the link</summary>
      <div class="muted">1. Open <a data-url="https://calendar.google.com/calendar/r/settings">Google Calendar settings ↗</a></div>
      <div class="muted">2. On the left, under “Settings for my calendars”, click a calendar.</div>
      <div class="muted">3. Scroll to “Integrate calendar” and copy the <b>Secret address in iCal format</b>.</div>
      <div class="muted">Google gives each calendar its own link, so repeat this for every calendar you want. For holidays and other shared calendars, use “Public address in iCal format”.</div>
    </details>
    <details class="howto"><summary>Outlook: where to find the link</summary>
      <div class="muted">1. Open <a data-url="https://outlook.office.com/calendar/options/calendar/SharedCalendars">work or school ↗</a> or <a data-url="https://outlook.live.com/calendar/0/options/calendar/SharedCalendars">personal ↗</a> calendar settings.</div>
      <div class="muted">2. Under “Publish a calendar”, choose a calendar and “Can view all details”, then Publish.</div>
      <div class="muted">3. Copy the ICS link.</div>
    </details>
    <div class="muted" style="margin-top:10px">Links are saved only on this PC. Anyone who has one can see that calendar, so keep them private.</div>`);
  $$("[data-url]", s.el).forEach(a => a.onclick = () => call("open_url", a.dataset.url));
  const input = $("[data-url-in]", s.el), status = $("[data-status]", s.el), listEl = $("[data-list]", s.el);
  const say = (t, bad) => { status.textContent = t; status.style.color = bad ? "var(--accent-text)" : ""; };
  const changed = () => { save(); renderTiles(); renderWeek(); renderCalDetail(); };
  const draw = () => {
    const errs = cache().calendar_errors || {};
    listEl.innerHTML = calendars().map((c, i) => `<div class="cal-row" data-i="${i}">
      <div class="grow name">${esc(calLabel(c, i))}${errs[i] ? '<span class="muted"> · not loading</span>' : ""}</div>
      <button class="link" data-rename>Rename</button><button class="link" data-remove>Remove</button></div>`).join("")
      || `<div class="muted">No calendars yet.</div>`;
  };
  listEl.addEventListener("click", e => {
    const row = e.target.closest("[data-i]"); if (!row) return; const i = +row.dataset.i;
    if (e.target.closest("[data-remove]")) {
      calendars().splice(i, 1); delete cache().calendar_errors;
      if (!hasCal()) { delete cache().events; delete cache().events_fetched; delete cache().events_error; }
      else cache().events = (cache().events || []).filter(ev => ev.cal !== i).map(ev => ev.cal > i ? { ...ev, cal: ev.cal - 1 } : ev);
      changed(); draw(); say("Removed.");
    } else if (e.target.closest("[data-rename]")) {
      const nameEl = $(".name", row); const c = calendars()[i];
      nameEl.innerHTML = `<input class="rename" value="${esc(calLabel(c, i))}">`;
      const inp = $("input", nameEl); inp.focus(); inp.select();
      const done = keep => { if (keep) { c.name = inp.value.trim(); changed(); } draw(); };
      inp.addEventListener("keydown", ev => { if (ev.key === "Enter") done(true); if (ev.key === "Escape") done(false); });
      inp.addEventListener("blur", () => done(true));
    }
  });
  const go = () => {
    const url = input.value.trim();
    if (!url) return;
    if (!/^(https?|webcal):\/\//i.test(url)) return say("Paste the full link (it starts with https://).", true);
    if (calendars().some(c => c.url === url)) return say("That calendar is already added.", true);
    say("Checking the link…");
    call("events", url).then(r => {
      if (!r || !r.ok) return say(`That didn't work: ${r ? r.error : "no connection"}`, true);
      calendars().push({ url, auto: r.name || "" });
      const i = calendars().length - 1;
      input.value = ""; say(`Added “${calLabel(calendars()[i], i)}”. Paste another link to add more.`);
      draw(); changed(); refreshCalendars().then(() => draw());
    });
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  $("[data-go]", s.el).onclick = go; $("[data-cancel]", s.el).onclick = s.close;
  draw();
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
    html += `<div class="band ${iso === ui.todoOpen ? "open" : ""} ${i === 0 ? "today" : ""}" data-iso="${iso}">
      <button class="band-head"><span class="dayname">${DAYS[d.getDay()]}</span><span class="count"></span></button>
      <div class="acc"><div><div class="acc-body"></div></div></div></div>`;
  }
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
  wireTaskDrag(inner, { list: row => row.closest(".acc-body"), bands: true, refresh: iso => renderBand(iso, inner) });
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
const plain = html => { const d = document.createElement("div"); d.innerHTML = (html || "").replace(/<\/(div|h[1-6]|li|p)>|<br\s*\/?>/gi, " "); return d.textContent.replace(/\s+/g, " ").trim(); };
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
      <button class="tool" data-cmd="bold" title="Bold (Ctrl+B)">B</button>
      <button class="tool" data-cmd="list" title="Bullet list">•≡</button></div>
    <input class="note-title-input" placeholder="Title" value="${esc(n.title)}">
    <div class="note-body" contenteditable="true">${n.html || ""}</div>`;
  const title = $(".note-title-input", page), body = $(".note-body", page);
  // Notes have no headings: turn any (saved earlier, or pasted in) into normal body-text lines.
  const flattenHeadings = () => {
    let found = false;
    body.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach(hd => {
      const div = document.createElement("div"); div.innerHTML = hd.innerHTML || "<br>"; hd.replaceWith(div); found = true;
    });
    return found;
  };
  if (flattenHeadings()) n.html = body.innerHTML;
  const changed = () => { flattenHeadings(); n.title = title.value.trim(); n.html = body.innerHTML; n.updated = stamp(); clearTimeout(noteTimer); noteTimer = setTimeout(() => { noteTimer = null; save(true); }, 400); };
  title.addEventListener("input", changed);
  title.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); body.focus(); } });
  body.addEventListener("input", changed);
  const block = () => {               // the line or bullet the caret is in
    const sel = getSelection(); if (!sel.rangeCount) return null;
    let n = sel.anchorNode; if (n && n.nodeType === 3) n = n.parentNode;
    while (n && n !== body && !/^(DIV|LI|P)$/.test(n.tagName)) n = n.parentNode;
    return n && n !== body && body.contains(n) ? n : null;
  };
  const tools = () => {
    const b = block();
    $$(".tool", page).forEach(t => {
      const c = t.dataset.cmd;
      const on = c === "bold" ? document.queryCommandState("bold") : !!(b && b.closest("li"));
      t.classList.toggle("on", on && document.activeElement === body);
    });
  };
  body.addEventListener("keydown", e => {   // Tab nests a bullet, Shift+Tab un-nests it
    if (e.key !== "Tab") return;
    e.preventDefault();                     // keep focus inside the note
    const b = block();
    if (b && b.closest("li")) document.execCommand(e.shiftKey ? "outdent" : "indent");
    else if (!e.shiftKey) document.execCommand("insertText", false, " ");
    changed(); tools();
  });
  document.addEventListener("selectionchange", tools);
  $(".editor-bar", page).addEventListener("mousedown", e => { if (e.target.closest(".tool")) e.preventDefault(); });
  $(".editor-bar", page).addEventListener("click", e => {
    if (e.target.closest("[data-back]")) { closeNote(); return; }
    const t = e.target.closest(".tool"); if (!t) return;
    body.focus();
    if (t.dataset.cmd === "bold") document.execCommand("bold");
    if (t.dataset.cmd === "list") document.execCommand("insertUnorderedList");
    changed(); tools();
  });
  wireNoteDrag(page, body, changed);
  setTimeout(() => { if (focusTitle) title.focus(); }, 380);
  return page;
}

// ---------------------------------------------------------------- drag to rearrange
const GRIP = '<svg width="8" height="14" viewBox="0 0 8 14"><g fill="currentColor"><circle cx="2" cy="2" r="1.3"/><circle cx="6" cy="2" r="1.3"/><circle cx="2" cy="7" r="1.3"/><circle cx="6" cy="7" r="1.3"/><circle cx="2" cy="12" r="1.3"/><circle cx="6" cy="12" r="1.3"/></g></svg>';
const STEP = 26;   // pixels of sideways drag per nesting level

/* Shared drag mechanics: a floating copy follows the pointer, a line shows where it will land,
   and the page scrolls when the pointer nears its top or bottom edge. */
function startDrag(srcEl, ev, scroller) {
  document.documentElement.classList.add("dragging-now");
  const r = srcEl.getBoundingClientRect();
  const ghost = srcEl.cloneNode(true);
  ghost.classList.add("drag-ghost"); ghost.classList.remove("dragging");
  ghost.querySelectorAll("ul, .acts").forEach(n => n.remove());
  Object.assign(ghost.style, { left: r.left + "px", top: r.top + "px", width: Math.min(r.width, 340) + "px" });
  document.body.appendChild(ghost);
  const line = h('<div class="drop-line" hidden></div>'); document.body.appendChild(line);
  const off = { x: ev.clientX - r.left, y: ev.clientY - r.top };
  let y = ev.clientY, raf = 0;
  const tick = () => {
    if (scroller) {
      const s = scroller.getBoundingClientRect();
      if (y < s.top + 48) scroller.scrollTop -= Math.ceil((s.top + 48 - y) / 6);
      else if (y > s.bottom - 48) scroller.scrollTop += Math.ceil((y - (s.bottom - 48)) / 6);
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return {
    move(e) { y = e.clientY; ghost.style.left = e.clientX - off.x + "px"; ghost.style.top = e.clientY - off.y + "px"; },
    showLine(top, left, width) { line.hidden = false; Object.assign(line.style, { top: top + "px", left: left + "px", width: Math.max(40, width) + "px" }); },
    hideLine() { line.hidden = true; },
    end() { cancelAnimationFrame(raf); ghost.remove(); line.remove(); document.documentElement.classList.remove("dragging-now"); },
  };
}
function onDragGesture(el, start) {
  // start a drag only after the pointer moves a few pixels, so clicks and double-clicks still work
  el.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    const ctx = start(e); if (!ctx) return;
    const sx = e.clientX, sy = e.clientY; let d = null;
    const move = ev => {
      if (!d) { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return; d = ctx.begin(ev); getSelection().removeAllRanges(); }
      d.move(ev);
    };
    const up = ev => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); if (d) d.drop(ev); };
    addEventListener("pointermove", move); addEventListener("pointerup", up);
  });
}
function flash(el) {   // brief highlight where something landed (removed again so it isn't saved into notes)
  if (!el) return;
  el.classList.remove("landed"); void el.offsetWidth; el.classList.add("landed");
  setTimeout(() => { el.classList.remove("landed"); if (!el.classList.length) el.removeAttribute("class"); }, 950);
}

/* Tasks: drag up/down to reorder, sideways to nest or un-nest, or onto another day's name to move it there. */
function wireTaskDrag(container, opts) {
  onDragGesture(container, e => {
    const row = e.target.closest(".task[data-id]");
    if (!row || e.target.closest(".chk, .acts, input")) return null;
    return { begin(ev) { return taskDrag(row, ev, container, opts); } };
  });
}
function taskDrag(row, ev0, container, opts) {
  const id = row.dataset.id; const src = findTask(id); if (!src.t) return { move() {}, drop() {} };
  const moving = [row];
  if (!src.parent) { let n = row.nextElementSibling; while (n && n.classList.contains("sub")) { moving.push(n); n = n.nextElementSibling; } }
  moving.forEach(m => m.classList.add("dragging"));
  const list = opts.list(row);
  const d = startDrag(row, ev0, container.closest(".page"));
  const baseDepth = src.parent ? 1 : 0;
  let target = null;

  const compute = e => {
    $$(".band-head.drop-target").forEach(x => x.classList.remove("drop-target"));
    if (opts.bands) {
      const head = document.elementFromPoint(e.clientX, e.clientY)?.closest(".band-head");
      if (head && !head.parentElement.classList.contains("open")) {
        head.classList.add("drop-target"); d.hideLine();
        return { day: head.parentElement.dataset.iso };
      }
    }
    const rows = $$(".task[data-id]", list).filter(r => !moving.includes(r));
    let idx = rows.length;
    for (let i = 0; i < rows.length; i++) { const r = rows[i].getBoundingClientRect(); if (e.clientY < r.top + r.height / 2) { idx = i; break; } }
    let depth = Math.round((e.clientX - ev0.clientX) / STEP) + baseDepth;
    depth = idx === 0 ? 0 : Math.max(0, Math.min(1, depth));
    const lr = list.getBoundingClientRect();
    const pad = parseFloat(getComputedStyle(list).paddingLeft) || 0;
    let y;
    if (rows[idx]) y = rows[idx].getBoundingClientRect().top - 1;
    else if (rows.length) y = rows[rows.length - 1].getBoundingClientRect().bottom + 1;
    else y = row.getBoundingClientRect().top;
    const left = lr.left + pad + depth * 26;
    d.showLine(y, left, lr.right - pad - left);
    return { idx, depth, before: rows[idx] ? rows[idx].dataset.id : null };
  };

  return {
    move(e) { d.move(e); target = compute(e); },
    drop() {
      d.end(); moving.forEach(m => m.classList.remove("dragging"));
      $$(".band-head.drop-target").forEach(x => x.classList.remove("drop-target"));
      if (!target) return;
      const srcIso = src.iso;
      const flat = [];   // the day as a flat list of {task, depth}, minus what is being moved
      for (const t of D.days[srcIso] || []) {
        if (t.id !== id) flat.push({ t, d: 0 });
        for (const c of t.children || []) if (c.id !== id && t.id !== id) flat.push({ t: c, d: 1 });
      }
      const block = [{ t: src.t, d: 0 }].concat(src.parent ? [] : (src.t.children || []).map(c => ({ t: c, d: 1 })));
      const rebuild = items => {
        const out = []; let cur = null;
        for (const { t, d: dep } of items) {
          if (dep === 0 || !cur) { cur = { id: t.id, text: t.text, done: t.done, children: [] }; out.push(cur); }
          else cur.children.push({ id: t.id, text: t.text, done: t.done });
        }
        return out;
      };
      if (target.day) {                                   // dropped on another day's name
        D.days[srcIso] = rebuild(flat);
        D.days[target.day] = rebuild((D.days[target.day] || []).flatMap(t => [{ t, d: 0 }].concat((t.children || []).map(c => ({ t: c, d: 1 })))).concat(block));
        if (!D.days[srcIso].length) delete D.days[srcIso];
        save(); opts.refresh(srcIso); opts.refresh(target.day);
        toast(`Moved to ${DAYS[parseIso(target.day).getDay()]}`);
        return;
      }
      block[0].d = target.depth;
      if (target.depth === 1) block.forEach(b => b.d = 1);
      let at = target.before ? flat.findIndex(f => f.t.id === target.before) : flat.length;
      if (at < 0) at = flat.length;
      flat.splice(at, 0, ...block);
      D.days[srcIso] = rebuild(flat);
      save(); opts.refresh(srcIso);
      flash(document.querySelector(`.task[data-id="${id}"]`));
    },
  };
}

/* Notes: a handle beside each line; drag a line (or a bullet with what's nested under it) to a new spot.
   Sideways movement changes nesting: right makes it a bullet / nests it, left un-nests it. */
function noteLines(body) {
  // flat list of lines: {el, depth (0 = normal line, 1+ = bullet level), top, bottom}
  for (const n of [...body.childNodes]) {      // wrap loose text into its own line first
    if (n.nodeType === 3 ? n.textContent.trim() : (n.nodeType === 1 && !/^(DIV|P|UL|OL)$/.test(n.tagName))) {
      const div = document.createElement("div"); n.replaceWith(div); div.appendChild(n);
    }
  }
  const out = [];
  const walkList = (list, depth) => {
    for (const li of list.children) {
      if (li.tagName !== "LI") continue;
      const sub = [...li.children].find(c => /^(UL|OL)$/.test(c.tagName));
      const r = li.getBoundingClientRect();
      out.push({ el: li, depth, top: r.top, bottom: sub ? sub.getBoundingClientRect().top : r.bottom });
      [...li.children].filter(c => /^(UL|OL)$/.test(c.tagName)).forEach(l => walkList(l, depth + 1));
    }
  };
  for (const el of body.children) {
    if (/^(UL|OL)$/.test(el.tagName)) walkList(el, 1);
    else { const r = el.getBoundingClientRect(); out.push({ el, depth: 0, top: r.top, bottom: r.bottom }); }
  }
  return out;
}
function lineHTML(el) {
  if (el.tagName !== "LI") return el.innerHTML;
  const c = el.cloneNode(true); c.querySelectorAll(":scope > ul, :scope > ol").forEach(n => n.remove());
  return c.innerHTML;
}
function buildNote(lines) {
  // rebuild the note's HTML from a flat list of {html, depth}
  const frag = document.createDocumentFragment(); const stack = [];
  for (const ln of lines) {
    while (stack.length > ln.depth) stack.pop();
    if (ln.depth === 0) { const div = document.createElement("div"); div.innerHTML = ln.html || "<br>"; frag.appendChild(div); continue; }
    while (stack.length < ln.depth) {
      const ul = document.createElement("ul");
      if (!stack.length) frag.appendChild(ul);
      else {
        const top = stack[stack.length - 1];
        if (!top.li) { top.li = document.createElement("li"); top.ul.appendChild(top.li); }
        top.li.appendChild(ul);
      }
      stack.push({ ul, li: null });
    }
    const li = document.createElement("li"); li.innerHTML = ln.html || "<br>";
    const top = stack[stack.length - 1]; top.ul.appendChild(li); top.li = li;
  }
  return frag;
}
function wireNoteDrag(page, body, changed) {
  $$(".note-grip").forEach(old => old.remove());          // one handle at a time
  const grip = h(`<div class="note-grip" title="Drag to move this line">${GRIP}</div>`);
  document.body.appendChild(grip);                         // outside the sliding panel, so its position is exact
  new MutationObserver((_, obs) => { if (!page.isConnected) { grip.remove(); obs.disconnect(); } })
    .observe(document.getElementById("views"), { childList: true });
  let hover = null, hideTimer = 0;
  const place = ln => {
    hover = ln; const b = body.getBoundingClientRect();
    const lineH = Math.min(26, ln.bottom - ln.top);
    grip.style.left = b.left - 20 + "px"; grip.style.top = ln.top + (lineH - 22) / 2 + "px";
    grip.classList.add("on");
  };
  const hide = () => { clearTimeout(hideTimer); hideTimer = setTimeout(() => grip.classList.remove("on"), 250); };
  body.addEventListener("mousemove", e => {
    if (document.documentElement.classList.contains("dragging-now")) return;
    const ln = noteLines(body).find(l => e.clientY >= l.top && e.clientY < l.bottom && (l.el.textContent.trim() || l.el.querySelector("br")));
    if (ln) { clearTimeout(hideTimer); place(ln); } else hide();
  });
  body.addEventListener("mouseleave", hide);
  grip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  grip.addEventListener("mouseleave", hide);
  page.addEventListener("scroll", () => grip.classList.remove("on"), { passive: true });

  onDragGesture(grip, e => {
    if (!hover) return null;
    e.preventDefault();
    const dragEl = hover.el;
    return {
      begin(ev0) {
        const lines = noteLines(body);
        const i0 = lines.findIndex(l => l.el === dragEl);
        if (i0 < 0) return { move() {}, drop() {} };
        let j = i0 + 1; while (j < lines.length && lines[j].depth > lines[i0].depth) j++;
        const block = lines.slice(i0, j);                // the line plus anything nested under it
        const rest = lines.filter(l => !block.includes(l));
        block.forEach(l => l.el.classList.add("dragging"));
        grip.classList.remove("on");
        const d = startDrag(dragEl, ev0, page);
        let target = null;
        return {
          move(e) {
            d.move(e);
            const live = rest.map(l => ({ ...l, ...(r => ({ top: r.top, bottom: l.el.tagName === "LI" && l.el.querySelector(":scope > ul, :scope > ol") ? l.el.querySelector(":scope > ul, :scope > ol").getBoundingClientRect().top : r.bottom }))(l.el.getBoundingClientRect()) }));
            let idx = live.length;
            for (let i = 0; i < live.length; i++) if (e.clientY < (live[i].top + live[i].bottom) / 2) { idx = i; break; }
            const prevDepth = idx > 0 ? live[idx - 1].depth : -1;
            let depth = block[0].depth + Math.round((e.clientX - ev0.clientX) / STEP);
            depth = Math.max(0, Math.min(prevDepth + 1, depth));
            const b = body.getBoundingClientRect();
            const y = live[idx] ? live[idx].top - 1 : (live.length ? live[live.length - 1].bottom + 1 : b.top);
            const left = b.left + depth * 22;
            d.showLine(y, left, b.right - left);
            target = { idx, depth };
          },
          drop() {
            d.end(); block.forEach(l => l.el.classList.remove("dragging"));
            if (!target) return;
            const shift = target.depth - block[0].depth;
            const flat = rest.map(l => ({ html: lineHTML(l.el), depth: l.depth }));
            const moved = block.map(l => ({ html: lineHTML(l.el), depth: Math.max(target.depth, l.depth + shift) }));
            moved[0].depth = target.depth;
            flat.splice(target.idx, 0, ...moved);
            body.replaceChildren(buildNote(flat));
            changed();
            flash(noteLines(body)[target.idx]?.el);
          },
        };
      },
    };
  });
}

// ---------------------------------------------------------------- window chrome
function wireChrome() {
  $("#tabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b && b.dataset.tab !== ui.tab) showTab(b.dataset.tab); });
  $("#theme").onclick = toggleTheme;
  $("#settings").innerHTML = ICON.gear; $("#settings").onclick = openSettings;
  // where the widget lives: on top of apps, on the desktop behind them, or a normal window
  const setLayer = layer => {
    S.layer = layer; S.on_top = layer === "top";
    $("#pin").classList.toggle("on", layer === "top");
    $("#pin").title = layer === "top" ? "Staying on top (Ctrl+T to put it back on the desktop)" : "Keep on top (Ctrl+T)";
    call("set_layer", layer); save();
    toast(layer === "top" ? "Staying on top of other apps" : layer === "desktop" ? "Living on the desktop, behind your apps" : "Normal window");
  };
  $("#pin").onclick = () => setLayer(S.layer === "top" ? "desktop" : "top");
  $("#close").onclick = async () => { flushNote(); await save(true); call("close"); };
  $(".topbar").addEventListener("contextmenu", e => {
    e.preventDefault();
    showMenu(e.clientX, e.clientY, [
      [(S.layer === "desktop" ? "✓ " : "") + "Stay on desktop (behind apps)", () => setLayer("desktop")],
      [(S.layer === "top" ? "✓ " : "") + "Stay on top of apps", () => setLayer("top")],
      [(S.layer === "normal" ? "✓ " : "") + "Normal window", () => setLayer("normal")],
      "-",
      [S.theme === "light" ? "Dark mode" : "Light mode", toggleTheme],
      "-", ["Export backup…", async () => { await save(true); const r = await call("export_backup"); if (r && r.ok) toast("Backup saved"); else if (r && r.error) toast(r.error); }],
      ["Import backup…", async () => {
        const r = await call("import_backup"); if (!r || !r.ok) { if (r && r.error) toast(r.error); return; }
        const n = Object.values(r.data.days).reduce((a, l) => a + l.length, 0);
        confirmSheet("Import backup?", `Replace your current tasks and notes with this backup (${n} tasks, ${r.data.notes.length} notes)?`, "Replace", () => {
          r.data.settings.window = S.window; D = r.data; S = D.settings; save(true); applyTheme(); ui.noteId = null; showTab(ui.tab, false); toast("Backup imported");
        });
      }],
      ["Settings…", openSettings],
      "-", ["Close DeskTodo", () => $("#close").click()],
      "-", [`DeskTodo ${ui.version || ""}`.trim(), () => toast(`You're running DeskTodo ${ui.version || ""}`.trim())],
    ]);
  });
  document.addEventListener("keydown", e => {
    if (!e.ctrlKey) return;
    if (["1", "2", "3"].includes(e.key)) { e.preventDefault(); const t = TABS[+e.key - 1]; if (t !== ui.tab) showTab(t); }
    if (e.key.toLowerCase() === "t") { e.preventDefault(); $("#pin").click(); }
  });
  document.addEventListener("contextmenu", e => { if (!e.target.closest("input, [contenteditable]")) e.preventDefault(); });

  // resize from the handle on the bottom edge (height only). One message starts it; Python then follows
  // the mouse natively until the button is released, so nothing queues up and the window never stalls.
  const grip = $("#grip");
  grip.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    e.preventDefault();
    call("begin_resize");
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

document.addEventListener("visibilitychange", () => { if (!document.hidden) syncAnalog(); });

// ---------------------------------------------------------------- start
async function start() {
  const st = await call("get_state");
  D = st.data; S = D.settings = D.settings || {};
  D.days = D.days || {}; D.notes = D.notes || [];
  ui.smoke = !!st.smoke;
  ui.version = st.version || "";
  if (rollOver()) save();
  ui.noteId = S.open_note && D.notes.some(n => n.id === S.open_note) ? S.open_note : null;
  applyTheme();
  S.layer = S.layer || (S.on_top ? "top" : "desktop");
  if (S.ics_url) { calendars().unshift({ url: S.ics_url, auto: "" }); delete S.ics_url; save(); }   // 1.5.7 and older: one link
  $("#pin").classList.toggle("on", S.layer === "top");
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
    ok: !!$(".clock span").textContent && typeof wireTaskDrag === "function" && typeof wireNoteDrag === "function",
    version: ui.version, dragReady: typeof wireTaskDrag === "function", ua: navigator.userAgent,
    viewTransitions: !!document.startViewTransition, colorMix: CSS.supports("color", "color-mix(in srgb, red, blue)"),
  }), 1500);
}
if (api()) start(); else window.addEventListener("pywebviewready", start, { once: true });
