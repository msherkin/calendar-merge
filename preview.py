#!/usr/bin/env python3
"""Show what the merged calendars contain, as a web page.

Reads every .ics file in the "output" folder (made by merge.py) and writes
output/preview.html: the coming weeks, day by day, with a button per calendar
and an "All" view that shows everything together.

    .venv/bin/python preview.py [weeks]

Needs the icalendar and recurring-ical-events packages (in .venv).
"""

import datetime as dt
import glob
import html
import os
import sys
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "output")
TZ = ZoneInfo("America/Toronto")
COLORS = ["#2a78d6", "#d9534f", "#2e9d5b", "#d9a520", "#8e5bd6", "#e0782b"]


def local(value):
    """Return (local datetime, is_all_day) for a DTSTART/DTEND value."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ)
        return value.astimezone(TZ), False
    return dt.datetime.combine(value, dt.time(), TZ), True


def load(path, start, end):
    with open(path, "rb") as f:
        cal = icalendar.Calendar.from_ical(f.read())
    title = str(cal.get("X-WR-CALNAME") or os.path.basename(path))
    events = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        begin, all_day = local(ev["DTSTART"].dt)
        finish = local(ev["DTEND"].dt)[0] if ev.get("DTEND") else begin
        events.append({
            "begin": begin,
            "finish": finish,
            "all_day": all_day,
            "title": str(ev.get("SUMMARY") or "(no title)"),
            "where": str(ev.get("LOCATION") or ""),
        })
    return title, events


def time_label(ev):
    if ev["all_day"]:
        return "All day"
    fmt = lambda t: t.strftime("%-I:%M %p").replace(":00", "").lower()
    return fmt(ev["begin"]) + "–" + fmt(ev["finish"])


def main():
    weeks = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    today = dt.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + dt.timedelta(weeks=weeks)

    files = sorted(glob.glob(os.path.join(OUTPUT, "*.ics")))
    if not files:
        sys.exit("No merged calendars in the output folder yet. Run: python3 merge.py")

    calendars = []
    days = {}
    for i, path in enumerate(files):
        title, events = load(path, today, end)
        color = COLORS[i % len(COLORS)]
        calendars.append((i, title, color, len(events)))
        for ev in events:
            ev.update(cal=i, color=color)
            day = ev["begin"].date()
            if ev["all_day"] or day >= today.date():
                days.setdefault(max(day, today.date()), []).append(ev)

    buttons = ['<button class="on" data-cal="all">All</button>'] + [
        f'<button data-cal="{i}"><span class="dot" style="background:{c}"></span>'
        f'{html.escape(t)} <small>{n}</small></button>'
        for i, t, c, n in calendars
    ]
    sections = []
    for day in sorted(days):
        items = sorted(days[day], key=lambda e: (not e["all_day"], e["begin"], e["title"]))
        rows = "".join(
            f'<li data-cal="{e["cal"]}" style="--c:{e["color"]}">'
            f'<span class="time">{time_label(e)}</span>'
            f'<span class="what">{html.escape(e["title"])}'
            + (f'<small>{html.escape(e["where"])}</small>' if e["where"] else "")
            + "</span></li>"
            for e in items
        )
        label = "Today" if day == today.date() else day.strftime("%A, %B %-d")
        sections.append(f'<section><h2>{label}</h2><ul>{rows}</ul></section>')

    page = PAGE.format(
        weeks=weeks,
        made=dt.datetime.now(TZ).strftime("%B %-d at %-I:%M %p"),
        buttons="".join(buttons),
        sections="".join(sections) or "<p>No events in this period.</p>",
    )
    out = os.path.join(OUTPUT, "preview.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {out}")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Merged Calendars</title>
<style>
:root {{ --bg:#f7f7f5; --card:#fff; --text:#1d1d1f; --muted:#6b6b70; --line:#e4e4e0; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#18181a; --card:#232326; --text:#ececee; --muted:#9a9aa0; --line:#34343a; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:15px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ max-width:720px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:24px; margin:0 0 4px; }}
.sub {{ color:var(--muted); margin:0 0 16px; }}
nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px; position:sticky; top:0;
  background:var(--bg); padding:8px 0; }}
button {{ font:inherit; color:var(--text); background:var(--card); border:1px solid var(--line);
  border-radius:999px; padding:6px 14px; cursor:pointer; display:flex; align-items:center; gap:6px; }}
button.on {{ border-color:var(--text); font-weight:600; }}
button small {{ color:var(--muted); font-weight:400; }}
.dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted);
  margin:22px 0 8px; }}
ul {{ list-style:none; margin:0; padding:0; background:var(--card); border:1px solid var(--line);
  border-radius:12px; overflow:hidden; }}
li {{ display:flex; gap:14px; padding:10px 14px; border-top:1px solid var(--line);
  border-left:4px solid var(--c); }}
li:first-child {{ border-top:0; }}
.time {{ flex:0 0 110px; color:var(--muted); font-variant-numeric:tabular-nums; }}
.what small {{ display:block; color:var(--muted); }}
.hidden {{ display:none; }}
@media (max-width:480px) {{ li {{ flex-direction:column; gap:2px; }} .time {{ flex:none; }} }}
</style></head><body><main>
<h1>Merged calendars</h1>
<p class="sub">Next {weeks} weeks · made {made}</p>
<nav>{buttons}</nav>
{sections}
</main>
<script>
const buttons = document.querySelectorAll("nav button");
buttons.forEach(b => b.addEventListener("click", () => {{
  buttons.forEach(x => x.classList.toggle("on", x === b));
  const cal = b.dataset.cal;
  document.querySelectorAll("li").forEach(li =>
    li.classList.toggle("hidden", cal !== "all" && li.dataset.cal !== cal));
  document.querySelectorAll("section").forEach(s =>
    s.classList.toggle("hidden", !s.querySelector("li:not(.hidden)")));
}}));
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
