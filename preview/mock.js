/* Preview stand-in for the Python side (desktodo.pyw), used only by the Claude preview page.
   Sample data is built relative to today; edits are kept in this browser only. */
(function () {
  const KEY = "desktodo-preview-v1";
  const p2 = n => String(n).padStart(2, "0");
  const iso = d => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
  const at = (d, h, m = 0) => `${iso(d)}T${p2(h)}:${p2(m)}:00`;
  const day = n => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return d; };
  const now = new Date();

  function events() {
    const out = [];
    const nextHour = Math.min(22, now.getHours() + 1);
    out.push({ start: at(day(0), nextHour), end: at(day(0), nextHour, 30), title: "Design review", location: "Teams", all_day: false });
    out.push({ start: at(day(1), 0), end: at(day(2), 0), title: "Office closed", location: "", all_day: true });
    for (let i = 2; i < 40; i++) {
      const d = day(i);
      if (d.getDay() === 0 || d.getDay() === 6) continue;
      out.push({ start: at(d, 9), end: at(d, 9, 15), title: "Team stand-up", location: "Teams", all_day: false });
      if (i % 7 === 3) out.push({ start: at(d, 14), end: at(d, 15), title: "Monthly review, Q&A", location: "Room 2B", all_day: false });
    }
    return out.sort((a, b) => a.start.localeCompare(b.start));
  }

  function weather(temp, code) {
    const hours = [];
    for (let h = 1; h <= 6; h++) {
      const t = new Date(now); t.setMinutes(0, 0, 0); t.setHours(t.getHours() + h);
      hours.push({ t: at(t, t.getHours()), temp: temp - h * 0.4, code: [2, 3, 71, 73, 3, 0][h - 1], is_day: t.getHours() >= 7 && t.getHours() < 17 ? 1 : 0 });
    }
    return { temp, feels: temp - 4, code, is_day: 1, hi: 6.1, lo: -6.3, sunrise: at(day(0), 6, 52), sunset: at(day(0), 16, 48),
      humidity: 83, wind: 4.2, gust: 9.1, wind_dir: 95, uv: 2.4, pop: 33, hourly: hours, fetched: at(now, now.getHours(), now.getMinutes()) };
  }

  function sample() {
    return {
      days: {
        [iso(day(0))]: [
          { id: "a", text: "Send invoice to Marco", done: false, children: [] },
          { id: "b", text: "Get groceries", done: false, children: [{ id: "b1", text: "Milk", done: true }, { id: "b2", text: "Eggs", done: false }] },
          { id: "c", text: "5km run", done: true, children: [] },
        ],
        [iso(day(2))]: [{ id: "d", text: "Dentist at 3pm", done: false, children: [] }],
      },
      notes: [{ id: "n1", title: "Packing list", updated: at(now, now.getHours(), 0),
        html: "<div>Boots, <b>gloves</b>, the good jacket.</div><h3>Gear</h3><ul><li>Skis</li><li>Poles<ul><li>Spare baskets</li></ul></li></ul>" }],
      settings: { theme: "dark", ics_url: "https://example.invalid/calendar.ics" },
      cache: {
        weather: { "39.550,-107.325": weather(3.2, 2), "39.369,-107.033": weather(1.5, 71) },
        events: events(), events_fetched: at(now, now.getHours(), now.getMinutes()),
      },
    };
  }

  function load() {
    try { const s = localStorage.getItem(KEY); if (s) return JSON.parse(s); } catch (e) { /* storage blocked */ }
    return sample();
  }

  window.__resetPreview = () => { try { localStorage.removeItem(KEY); } catch (e) { /* ignore */ } };
  window.__mockApi = {
    get_state: () => Promise.resolve({ data: load(), smoke: false }),
    save: d => { try { localStorage.setItem(KEY, JSON.stringify(d)); } catch (e) { /* ignore */ } return Promise.resolve(true); },
    weather: () => Promise.resolve({ ok: false, error: "Preview uses sample weather" }),
    events: () => Promise.resolve({ ok: true, events: events() }),
    geocode: q => Promise.resolve({ ok: true, places: [
      { name: q.split(",")[0].trim() || "Aspen", region: "Colorado", country: "United States", lat: 39.19, lon: -106.82 }] }),
    open_url: url => { window.open(url, "_blank", "noopener"); },
    report_size: () => null, resize: () => null, set_on_top: () => null, close: () => null,
    export_backup: () => Promise.resolve({ ok: false, error: "Backups work in the desktop app" }),
    import_backup: () => Promise.resolve({ ok: false, error: "Backups work in the desktop app" }),
    log: m => console.warn("DeskTodo:", m),
  };
})();
