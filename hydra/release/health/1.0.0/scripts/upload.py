"""Health's upload source (column.json, id "upload"): the files the person drops on Health's page, which Hydra-OS's
server puts in their Health folder's inbox/. It's the way in for Apple Health's own export and for a file of days, a
spreadsheet saved as CSV with a row for each day, and it's read only when the person chose it in <root>/yours/sources.json.
Another tracker's own export is read only when its columns carry the names below.

Apple Health's export is its export.zip, or the export.xml inside it, read streamed at any size by apple.py. Any other
file is a .csv with a header row, or a .json holding a list of rows (or {"days": [...]}), at most 2 MB. The columns are
the shape's own names (days.py), and a few plain ones a person's export is likely to use:

    day | date
    readiness | recovery | body_battery        the source's own morning score, 0 to 100
    sleep_hours | sleep
    resting_heart | resting_heart_rate | rhr
    lights_out | bedtime | bed
    woke | wake
    sports | workouts | sessions
    weight

Files are read oldest first, by when each came in, and a newer file's day wins, so a newer export corrects an older
one. A file that can't be read is counted, never guessed at. Health never changes or removes what the person put there.

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json

import common
import days

SOURCE = "upload"
EXPORTS = "exports.json"   # in store/: what each export gave, by its name, size and time, so a big one is read once
MAX_BYTES, MAX_ROWS = 2_000_000, 5000
ALIASES = {
    "day": "day", "date": "day",
    "readiness": "readiness", "recovery": "readiness", "body_battery": "readiness",
    "sleep_hours": "sleep_hours", "sleep": "sleep_hours",
    "resting_heart": "resting_heart", "resting_heart_rate": "resting_heart", "rhr": "resting_heart",
    "lights_out": "lights_out", "bedtime": "lights_out", "bed": "lights_out",
    "woke": "woke", "wake": "woke",
    "sports": "sports", "workouts": "sports", "sessions": "sports",
    "weight": "weight", "readiness_name": "readiness_name", "workout_minutes": "workout_minutes", "bed_hours": "bed_hours",
}
SCORE_NAMES = {"recovery": "Recovery", "readiness": "Readiness", "body_battery": "Body Battery"}


def _key(name) -> str:
    return str(name or "").strip().lower().replace(" ", "_").replace("-", "_")


def _row(raw: dict):
    out, name = {}, ""
    for k, v in raw.items():
        key = _key(k)
        field = ALIASES.get(key)
        if field is None or v is None or (isinstance(v, str) and not v.strip()):
            continue
        out.setdefault(field, v)
        if key in SCORE_NAMES and not name:
            name = SCORE_NAMES[key]
    if name:
        out.setdefault("readiness_name", name)
    return days.clean(out, SOURCE)


def _rows_of(path):
    """(the rows of one file, or None when it can't be read as days; the day Apple made it, or None). Apple Health's
    export (.zip, or its .xml) goes to its own streamed reader (apple.py), at any size."""
    if path.suffix.lower() in (".zip", ".xml"):
        import apple  # noqa: PLC0415
        info = {}
        try:
            return apple.read(path, info) or None, info.get("made")
        except (apple.NotAnExport, OSError):
            return None, None
    return _days_of(path), None


def _days_of(path):
    """A file of days' rows, or None."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    if path.suffix.lower() == ".json":
        try:
            doc = json.loads(text)
        except ValueError:
            return None
        raw = doc.get("days") if isinstance(doc, dict) else doc
        if not isinstance(raw, list):
            return None
        raw = [r for r in raw if isinstance(r, dict)]
    else:
        try:
            raw = list(csv.DictReader(io.StringIO(text)))
        except csv.Error:
            return None
    rows = [r for r in (_row(x) for x in raw[:MAX_ROWS]) if r]
    return rows or None


def _end(p, made) -> str:
    """A file's last day: Apple's own export date when it gave one, else the day it came in."""
    return made or dt.date.fromtimestamp(p.stat().st_mtime).isoformat()


def came(rec):
    """The last day the inbox's files cover, YYYY-MM-DD, or None, as read() works it out: for a page drawn on its own."""
    box = rec / "inbox"
    seen = common.load_json(rec / "store" / EXPORTS, {}) or {}
    seen = seen if isinstance(seen, dict) else {}
    best = None
    for p in (box.iterdir() if box.is_dir() else []):
        if not p.is_file() or p.suffix.lower() not in (".csv", ".json", ".zip", ".xml") or p.name.startswith("."):
            continue
        st, got = p.stat(), seen.get(p.name)
        made = got.get("made") if isinstance(got, dict) and got.get("mark") == [st.st_size, st.st_mtime_ns] else None
        best = max(best, _end(p, made)) if best else _end(p, made)
    return best


def waiting(rec) -> bool:
    """Whether a file in the inbox came in after the last run began, so it's being read now. No file is no wait."""
    box = rec / "inbox"
    got = [p.stat().st_mtime for p in box.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".json", ".zip", ".xml")
           and not p.name.startswith(".")] if box.is_dir() else []
    if not got:
        return False
    runs = [r for r in common.read_jsonl(rec / "runs.jsonl") if r.get("started_at")]
    last = common.parse_time(runs[-1]["started_at"]) if runs else None
    return last is None or max(got) > last.timestamp()


def read(rec) -> tuple:
    """(the rows, newest file first so its day wins, and counts): {"files", "unread", "rows", "came"}, where "came" is
    the last day the files that could be read cover, YYYY-MM-DD, or None: Apple's own export date, or the day a file
    of days came in. No inbox is no rows."""
    box = rec / "inbox"
    files = sorted((p for p in box.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".json", ".zip", ".xml")
                    and not p.name.startswith(".")), key=lambda p: (p.stat().st_mtime, p.name)) if box.is_dir() else []
    seen = common.load_json(rec / "store" / EXPORTS, {}) or {}
    seen = seen if isinstance(seen, dict) else {}
    kept, lists, unread, came = {}, [], 0, None
    for p in files:
        if p.suffix.lower() in (".zip", ".xml"):   # an export of gigabytes is read once, then by what it gave
            st = p.stat()
            mark, got = [st.st_size, st.st_mtime_ns], seen.get(p.name)
            if isinstance(got, dict) and got.get("mark") == mark and "made" in got:
                rows, made = got["rows"], got["made"]
            else:   # read once, then by what it gave; a cache from an older version is read once more for its date
                rows, made = _rows_of(p)
            kept[p.name] = {"mark": mark, "rows": rows, "made": made}
        else:
            rows, made = _rows_of(p)
        if rows is None:
            unread += 1
        else:
            lists.append(rows)
            came = max(came, _end(p, made)) if came else _end(p, made)
    if kept != seen and (kept or seen):
        common.folder(rec / "store")
        common.write_atomic(rec / "store" / EXPORTS, json.dumps(kept, ensure_ascii=False, sort_keys=True) + "\n")
    merged = days.merge(*reversed(lists))
    return [merged[d] for d in sorted(merged)], {"files": len(files), "unread": unread, "rows": len(merged),
                                                 "came": came}
