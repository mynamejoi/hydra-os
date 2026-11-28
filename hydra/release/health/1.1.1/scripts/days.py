"""The shape Health reads (column.json's shape, "days" v1): one row a day, named by what it is, never by the service.

    day             YYYY-MM-DD, the morning the row is for
    readiness       the source's own morning score, 0 to 100
    readiness_name  that score in the source's own word: Recovery, Readiness or Body Battery
    sleep_hours     hours asleep in the night that ended that morning
    bed_hours       hours in bed that night, kept only when no sleep was recorded (an iPhone with no watch)
    resting_heart   beats a minute
    hrv             heart rate variability, in ms, the day's mean
    lights_out      HH:MM, when that night began, in the Mac's own time
    woke            HH:MM, when it ended
    sports          the day's sessions by kind, such as "swim, run"
    workout_minutes the day's sessions' minutes, all together
    weight          as the source gives it

Only day is required. store/days.jsonl keeps the rows, one line a day, written whole each run from what the chosen
sources gave. The workouts the person logged through Claude (act.py log-workout) are kept apart, in
store/workouts.jsonl, and join each day's sessions and minutes only as the rows are read, never in days.jsonl. Nothing
here prints a value.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import common

NUMBERS = {"readiness": (0, 100), "sleep_hours": (0, 24), "bed_hours": (0, 24), "resting_heart": (20, 220), "hrv": (1, 300), "workout_minutes": (0, 1440), "weight": (1, 1000)}
TIMES = ("lights_out", "woke")
NAMES = ("Recovery", "Readiness", "Body Battery")
KINDS = {  # a session's kind in one plain word, so a goal's unit ("swims") finds it
    "swim": ("swim", "swimming", "pool", "open water"), "run": ("run", "running", "jog", "jogging", "trail running"),
    "ride": ("ride", "cycling", "cycle", "bike", "biking", "spin", "spinning", "mountain biking"),
    "walk": ("walk", "walking", "hike", "hiking"), "lift": ("lift", "lifting", "weightlifting", "weights", "strength",
                                                               "powerlifting", "functional fitness", "strength trainer"),
    "yoga": ("yoga", "pilates", "stretching"), "row": ("row", "rowing"),
}
_KIND = {w: k for k, ws in KINDS.items() for w in ws}
_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?m?\.?\s*$", re.I)


def minutes(text) -> int | None:
    """Minutes after midnight for "21:05", "9:05 pm" or "9pm"; None when it isn't a time."""
    m = _TIME.match(str(text)) if isinstance(text, str) else None
    if not m:
        return None
    h, mm, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if m.group(2) is None and not half:   # a bare "9" could be either half of the day
        return None
    if mm > 59 or h > 23 or (half and not 1 <= h <= 12):
        return None
    if half:
        h = h % 12 + (12 if half == "p" else 0)
    return h * 60 + mm


def hhmm(mins: int) -> str:
    mins = int(mins) % 1440
    return f"{mins // 60:02d}:{mins % 60:02d}"


def evening(text) -> int | None:
    """A night's start as minutes after noon, so 00:30 sorts after 23:10."""
    m = minutes(text)
    return None if m is None else (m - 720) % 1440


def clock12(text) -> tuple:
    """("9:05", "pm") for "21:05"; ("", "") when it isn't a time."""
    m = minutes(text)
    if m is None:
        return "", ""
    h = m // 60
    return f"{h % 12 or 12}:{m % 60:02d}", "am" if h < 12 else "pm"


def kind_of(sport) -> str:
    """A session's kind in one plain word: "Swimming" is "swim". An unknown sport keeps its own name, lower case."""
    s = re.sub(r"[-_]+", " ", str(sport or "")).strip().lower()
    return _KIND.get(s, s)[:24]


def kinds(text) -> list:
    return [k for k in (kind_of(p) for p in str(text or "").split(",")) if k]


def _number(x, lo, hi):
    if isinstance(x, bool):
        return None
    if isinstance(x, str):
        try:
            x = float(x.strip().rstrip("%"))
        except ValueError:
            return None
    if not isinstance(x, (int, float)) or x != x or not lo <= x <= hi:
        return None
    return round(float(x), 2)


def clean(row, source: str = "") -> dict | None:
    """One row in the shape, or None when it has no sound day. A value that isn't sound is left out, never guessed."""
    if not isinstance(row, dict):
        return None
    try:
        day = dt.date.fromisoformat(str(row.get("day")).strip()[:10]).isoformat()
    except ValueError:
        return None
    out = {"day": day}
    for k, (lo, hi) in NUMBERS.items():
        v = _number(row.get(k), lo, hi)
        if v is not None:
            out[k] = v
    for k in TIMES:
        m = minutes(row.get(k))
        if m is not None:
            out[k] = hhmm(m)
    got = kinds(row.get("sports"))
    if got:
        out["sports"] = ", ".join(got)
    name = str(row.get("readiness_name") or "").strip()
    if "readiness" in out:
        out["readiness_name"] = name if name in NAMES else "Readiness"
    if source:
        out["source"] = source
    return out


def merge(*lists) -> dict:
    """{day: row}: for each day, the row from the first list that has it, each through clean() again, so a value of
    another type, or an item that isn't a row, never reaches the working-out."""
    out = {}
    for rows in lists:
        for r in rows:
            r = clean(r, str(r.get("source") or "")) if isinstance(r, dict) else None
            if r and r["day"] not in out:
                out[r["day"]] = r
    return out


def logged(rec) -> list:
    """The workouts the person logged through Claude, store/workouts.jsonl, each sound: {"id", "day", "kind",
    "minutes" or None, "saved_at"}. A line that isn't one is left out."""
    out = []
    for w in common.read_jsonl(rec / "store" / "workouts.jsonl"):
        if not isinstance(w, dict):
            continue
        try:
            day = dt.date.fromisoformat(str(w.get("day")).strip()[:10]).isoformat()
        except ValueError:
            continue
        kind = kind_of(str(w.get("kind") or ""))
        if kind:
            out.append({"id": str(w.get("id") or ""), "day": day, "kind": kind,
                        "minutes": _number(w.get("minutes"), 1, 1440), "saved_at": str(w.get("saved_at") or "")})
    return out


def with_logged(rows: dict, sessions: list) -> dict:
    """The rows with each logged workout in its day's sessions, and its minutes in the day's minutes. A day with no
    row gets one that holds only that."""
    out = {d: dict(r) for d, r in rows.items()}
    for w in sessions:
        r = out.setdefault(w["day"], {"day": w["day"], "source": "logged"})
        r["sports"] = ", ".join(([r["sports"]] if r.get("sports") else []) + [w["kind"]])
        if w.get("minutes"):
            r["workout_minutes"] = round(float(r.get("workout_minutes") or 0) + w["minutes"], 2)
    return out


def load(rec, with_log: bool = True) -> dict:
    """store/days.jsonl's rows by day, each as clean() has it, with the workouts logged through Claude in them."""
    rows = merge(common.read_jsonl(rec / "store" / "days.jsonl"))
    return with_logged(rows, logged(rec)) if with_log else rows


def save(rec, rows: dict) -> None:
    common.folder(rec / "store")
    text = "".join(json.dumps(rows[d], ensure_ascii=False, sort_keys=True) + "\n" for d in sorted(rows))
    common.write_atomic(rec / "store" / "days.jsonl", text)
