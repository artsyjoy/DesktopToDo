"""
DeskTodo core: storage, midnight roll-over, weather (open-meteo.com) and calendar (ICS: Google, Outlook) parsing.
No user interface here - the window is drawn by desktodo.pyw with WebView2.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from html import escape

APP_NAME = "DeskTodo"
APP_VERSION = "1.5.8"   # shown in the top-bar right-click menu; bump with each release
BULLET = "\u2022  "

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


# =========================================================================== online services
# Weather: open-meteo.com (free, no key). Calendar: an Outlook "published calendar" ICS link.

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

USER_AGENT = "DeskTodo/1.0 (desktop to-do widget)"


def http_get(url, timeout=20, attempts=3):
    """GET a URL as text. Retries brief network glitches (dropped connections, timeouts)."""
    import time
    import urllib.error
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == attempts - 1:
                raise  # a real answer from the server (e.g. bad link): don't retry
        except (urllib.error.URLError, OSError):
            if attempt == attempts - 1:
                raise
        time.sleep(1.5 * (attempt + 1))


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
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2, "wind_speed_unit": "mph",
        "current": "temperature_2m,apparent_temperature,weather_code,is_day,relative_humidity_2m,"
                   "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "hourly": "temperature_2m,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,precipitation_probability_max",
    })
    j = json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))
    cur, d, hr = j["current"], j["daily"], j.get("hourly", {})
    now_hour = cur.get("time", "")[:13]
    hourly = []
    for i, t in enumerate(hr.get("time", [])):
        if t[:13] > now_hour and len(hourly) < 6:
            hourly.append({"t": t, "temp": hr["temperature_2m"][i], "code": hr["weather_code"][i],
                           "is_day": (hr.get("is_day") or [1] * (i + 1))[i]})

    def first(key):
        return (d.get(key) or [None])[0]
    return {"temp": cur["temperature_2m"], "feels": cur.get("apparent_temperature"), "code": cur["weather_code"],
            "is_day": cur.get("is_day", 1), "hi": d["temperature_2m_max"][0], "lo": d["temperature_2m_min"][0],
            "sunrise": d["sunrise"][0], "sunset": d["sunset"][0],
            "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"),
            "gust": cur.get("wind_gusts_10m"), "wind_dir": cur.get("wind_direction_10m"),
            "uv": first("uv_index_max"), "pop": first("precipitation_probability_max"), "hourly": hourly,
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


def fetch_calendar(url):
    """One ICS link -> (calendar name or "", events)."""
    url = url.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    text = http_get(url, timeout=30)
    if "BEGIN:VCALENDAR" not in text[:2000].upper():
        raise ValueError("That link didn't return a calendar (ICS) file.")
    m = re.search(r"^X-WR-CALNAME:(.*)$", text[:20000], re.M | re.I)
    name = m.group(1).strip().replace("\\,", ",").replace("\\;", ";") if m else ""
    today0 = datetime.combine(date.today(), datetime.min.time())
    # a window wide enough for the month calendar as well as "Up next"
    return name, parse_ics(text, today0 - timedelta(days=35), today0 + timedelta(days=100))


def fetch_events(url):
    return fetch_calendar(url)[1]


def fetch_calendars(urls):
    """Several ICS links fetched side by side and merged into one list.

    Returns (events, names, errors): events are tagged with their calendar's position ("cal"), the same
    meeting found in two calendars is shown once, and errors maps a position to what went wrong."""
    from concurrent.futures import ThreadPoolExecutor
    results = [None] * len(urls)

    def one(i):
        try:
            results[i] = fetch_calendar(urls[i])
        except Exception as exc:
            results[i] = exc

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(urls)))) as pool:
        list(pool.map(one, range(len(urls))))
    events, names, errors, seen = [], [], {}, set()
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            names.append("")
            errors[i] = str(r) or type(r).__name__
            continue
        names.append(r[0])
        for e in r[1]:
            key = (e["start"], e["end"], e["title"].strip().lower())
            if key not in seen:
                seen.add(key)
                events.append(dict(e, cal=i))
    events.sort(key=lambda e: (e["start"], not e["all_day"]))
    return events, names, errors




# =========================================================================== notes: old format -> HTML


def runs_to_html(runs):
    """Convert notes saved by the earlier version ([[text, [tags]], ...]) into simple HTML."""
    chars = []
    for text, tags in runs or []:
        for ch in text:
            chars.append((ch, set(tags)))
    lines, cur = [], []
    for ch, tags in chars:
        if ch == "\n":
            lines.append(cur)
            cur = []
        else:
            cur.append((ch, tags))
    lines.append(cur)

    def inline(segment):
        out, bold = [], False
        for ch, tags in segment:
            b = "b" in tags
            if b != bold:
                out.append("<b>" if b else "</b>")
                bold = b
            out.append(escape(ch))
        if bold:
            out.append("</b>")
        return "".join(out)

    html, in_list = [], False
    for line in lines:
        text = "".join(c for c, _ in line)
        is_bullet = text.startswith(BULLET)
        if is_bullet:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{inline(line[len(BULLET):])}</li>")
            continue
        if in_list:
            html.append("</ul>")
            in_list = False
        if text:  # headings from the old version become normal lines (notes have no headings)
            html.append(f"<div>{inline(line)}</div>")
        else:
            html.append("<div><br></div>")
    if in_list:
        html.append("</ul>")
    return "".join(html)


def upgrade_notes(data):
    for n in data.get("notes", []):
        if "html" not in n:
            n["html"] = runs_to_html(n.get("content"))


# =========================================================================== self-test


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
    except OSError as exc:
        # The weather service dropping a connection is outside our control: warn, don't fail the build.
        print("WARN network unavailable, live weather not checked:", exc)
    except Exception as exc:  # the service answered but we couldn't read it: that is a real failure
        print("FAIL weather data:", repr(exc))
        ok = False
    print("SELFTEST", "OK" if ok else "FAILED")
    return ok


