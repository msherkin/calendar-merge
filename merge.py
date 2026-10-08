#!/usr/bin/env python3
"""Merge groups of iCalendar feeds into one .ics file per group.

Each group is a list of calendars, one per line:  Name | URL
On the Mac, the lists are files named <group>_calendars.txt in this folder.
On GitHub, they come from secrets named <GROUP>_CALENDARS, so the private
calendar links never appear in the public repository.

    python3 merge.py

writes <group>.ics for every list into the "output" folder (on GitHub, into
the secret publish folder instead). Runs on plain Python 3, no extra packages.
"""

import datetime
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LIST_SUFFIX = "_calendars.txt"
SECRET_SUFFIX = "_CALENDARS"


def find_lists():
    """Return {group: list text} from local files and from GitHub secrets."""
    lists = {}
    for path in sorted(glob.glob(os.path.join(HERE, "*" + LIST_SUFFIX))):
        group = os.path.basename(path)[: -len(LIST_SUFFIX)]
        with open(path, encoding="utf-8") as f:
            lists[group] = f.read()
    secrets = json.loads(os.environ.get("CALENDAR_SECRETS") or "{}")
    for key, value in secrets.items():
        if key.endswith(SECRET_SUFFIX) and value.strip():
            lists[key[: -len(SECRET_SUFFIX)]] = value
    return {re.sub(r"[^a-z0-9_-]", "", g.lower()): text for g, text in lists.items()}


def parse_list(group, text):
    """Return (title, prefix_titles, history_days, [(name, url), ...]) for one list."""
    title = group.replace("_", " ").title()
    prefix = False
    history_days = 120
    feeds = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            setting, _, value = line[1:].partition(":")
            setting, value = setting.strip().lower(), value.strip()
            if setting == "title" and value:
                title = value
            elif setting == "prefix":
                prefix = value.lower() in ("yes", "true", "on")
            elif setting == "history days" and value.isdigit():
                history_days = int(value)
            continue
        if not line:
            continue
        name, _, rest = line.partition("|")
        name, url = name.strip(), rest.split("|")[0].strip()
        if not url:
            name, url = "Calendar", name
        feeds.append((name, url))
    return title, prefix, history_days, feeds


def fetch(url, attempts=3):
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "calendar-merge/1.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(10)


def describe_error(exc):
    # Never include the URL: GitHub logs for a public repo are public.
    if isinstance(exc, urllib.error.HTTPError):
        return f"the calendar site answered HTTP {exc.code}"
    return f"could not download it ({type(exc).__name__})"


def extract_blocks(ics_text, component):
    """Return each BEGIN:<component>...END:<component> block as a list of lines."""
    blocks = []
    current = None
    for line in ics_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        # Keep trailing spaces: a long line folded right after a space needs it.
        marker = line.strip()
        if marker == f"BEGIN:{component}":
            current = [marker]
        elif marker == f"END:{component}" and current is not None:
            current.append(marker)
            blocks.append(current)
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def property_value(block_lines, prop):
    """First value of a property in a block, e.g. UID or TZID (handles UID;PARAM: too)."""
    for line in block_lines:
        if line.startswith(prop + ":") or line.startswith(prop + ";"):
            return line.split(":", 1)[1] if ":" in line else ""
    return None


def event_key(block_lines):
    uid = property_value(block_lines, "UID")
    recurrence_id = property_value(block_lines, "RECURRENCE-ID") or ""
    if uid:
        return uid + "//" + recurrence_id
    return hashlib.sha1("\n".join(block_lines).encode()).hexdigest()


def prefix_summary(block_lines, name):
    for i, line in enumerate(block_lines):
        if line.startswith("SUMMARY:") or line.startswith("SUMMARY;"):
            prop, _, value = line.partition(":")
            block_lines[i] = f"{prop}:[{name}] {value}"
            break
    return block_lines


def merge_group(group, text):
    """Return (ics text, [failure messages]) for one list."""
    title, prefix, history_days, feeds = parse_list(group, text)
    if not feeds:
        return None, [f"{group}: the list has no calendar links"]
    cutoff = (datetime.date.today() - datetime.timedelta(days=history_days)).strftime("%Y%m%d")

    timezones = {}   # TZID -> block lines
    events = {}      # event key -> block lines
    failures = []
    for name, url in feeds:
        try:
            ics = fetch(url)
        except Exception as exc:
            failures.append(f"{group} / {name}: {describe_error(exc)}")
            continue
        for tz_block in extract_blocks(ics, "VTIMEZONE"):
            tzid = property_value(tz_block, "TZID")
            if tzid and tzid not in timezones:
                timezones[tzid] = tz_block
        count = 0
        for ev_block in extract_blocks(ics, "VEVENT"):
            start = (property_value(ev_block, "DTSTART") or "")[:8]
            if property_value(ev_block, "RRULE") is None and start.isdigit() and start < cutoff:
                continue
            if prefix:
                ev_block = prefix_summary(ev_block, name)
            events[event_key(ev_block)] = ev_block
            count += 1
        print(f"  {name}: {count} events")

    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//calendar-merge//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{title}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for tz_block in timezones.values():
        out.extend(tz_block)
    for ev_block in events.values():
        out.extend(ev_block)
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n", failures


def output_folder():
    folder = os.environ.get("PUBLISH_FOLDER", "").strip()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if len(folder) < 16:
            sys.exit("The PUBLISH_FOLDER secret is missing or too short; "
                     "refusing to publish calendars at a guessable address.")
        return os.path.join(HERE, "site", folder)
    return os.path.join(HERE, "output")


def main():
    lists = find_lists()
    if not lists:
        sys.exit(f"No calendar lists found (files named *{LIST_SUFFIX} "
                 f"or GitHub secrets named *{SECRET_SUFFIX}).")

    folder = output_folder()
    os.makedirs(folder, exist_ok=True)
    all_failures = []
    for group, text in lists.items():
        print(f"{group}:")
        ics, failures = merge_group(group, text)
        all_failures += failures
        if ics and not failures:
            with open(os.path.join(folder, group + ".ics"), "w", encoding="utf-8", newline="") as f:
                f.write(ics)
            print(f"  -> wrote {group}.ics")

    if all_failures:
        # Failing the run keeps the last good calendars online, and GitHub
        # emails a failure notice, instead of events silently disappearing.
        sys.exit("Not publishing, because some calendars could not be read:\n  "
                 + "\n  ".join(all_failures))


if __name__ == "__main__":
    main()
