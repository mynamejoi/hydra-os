"""Health's meal log: what the person typed in "Log a meal", and how it was read. A meal keeps its time, and what its
words place: the meal, where it was eaten, any protein, vegetables and drinks, and heavy or light. A word it can't place is left out, never guessed. Observations only: no diet plan and no
calorie count.

store/meals.jsonl, one line a meal, 0600:

    {"id": "m-<12 hex>", "day": "2026-11-20", "at": "18:30", "meal": "Dinner", "where": "Home", "protein": "salmon",
     "veg": "greens", "drinks": "", "none": false, "size": "", "words": "<the line as typed>", "by": "page",
     "saved_at": "<ISO>"}

`day` is the day the meal was eaten: before 04:00, the day before. The typed line stays in this file only: it never goes
to Home, to another app, or into a prompt that has tools.

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import datetime as dt
import re

import common

MAX = 120
NAMED = re.compile(r"\b(breakfast|brunch|lunch|dinner|supper|snack)\b")
T1 = re.compile(r"\b(\d{1,2}):(\d{2})(?:\s*([ap])\.?m\b)?")
T2 = re.compile(r"\b(\d{1,2})()\s*([ap])\.?m\b")
T3 = re.compile(r"\bat\s+(\d{1,2})()()\b")
NONE = re.compile(r"\b(no|without|zero|skipped) (drinks?|alcohol|wine|beer)\b")
PROTEIN = re.compile(r"\b(salmon|chicken|eggs?|beef|steak|tofu|fish|tuna|turkey|pork|shrimp|lamb|lentils|chickpeas|yogurt|tempeh)\b")
VEG = re.compile(r"\b(greens|salad|broccoli|spinach|kale|vegetables|veggies|carrots|peppers|asparagus|green beans|tomatoes|"
                 r"zucchini|cabbage|peas|squash|mushrooms|cauliflower|sprouts)\b")
DRINKS = re.compile(r"\b(wine|beers?|cocktails?|whiskey|bourbon|margaritas?|cider|sake|champagne)\b")


def _words(s: str, rx) -> str:
    seen = []
    for w in rx.findall(s):
        if w not in seen:
            seen.append(w)
    return ", ".join(seen[:3])


def owners_day(now: dt.datetime) -> dt.date:
    """The day a person means by "today": before 04:00 it's still the day before."""
    t = now.astimezone()
    return (t - dt.timedelta(hours=4)).date()


def read_line(raw: str, now: dt.datetime) -> dict:
    """How a typed line reads, by its words alone: {"at", "meal", "where", "protein", "veg", "drinks", "none", "size"}."""
    s = " ".join(str(raw).split()).lower()
    named = (NAMED.search(s) or [None, ""])[1]
    t_now = now.astimezone()
    mins_now = t_now.hour * 60 + t_now.minute
    m = T1.search(s) or T2.search(s) or T3.search(s)
    t = 720 if re.search(r"\bnoon\b", s) else None
    if m and int(m.group(1)) < 24 and int(m.group(2) or 0) < 60:
        h, mm, half = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        a, p = h % 12 * 60 + mm, h % 12 * 60 + mm + 720
        if h > 12:
            t = h * 60 + mm
        elif half:
            t = p if half == "p" else a
        elif named in ("dinner", "supper"):
            t = p
        elif named == "breakfast":
            t = p if h == 12 else a
        elif named in ("lunch", "brunch"):
            t = a if 9 <= h < 12 else p
        else:   # no am or pm and no name: the latest such time that has already passed
            t = p if p <= mins_now else a
    if t is None:
        t = mins_now
    none = bool(NONE.search(s))
    meal = {"supper": "Dinner"}.get(named, named.capitalize()) if named else \
        "Breakfast" if t < 630 else "Lunch" if t < 900 else "Snack" if t < 990 else "Dinner"
    where = "Takeout" if re.search(r"\b(take ?-?out|delivery|delivered|ordered in|to go)\b", s) else \
        "Out" if re.search(r"\b(restaurant|ate out|dined out|eating out|went out|out)\b", s) else \
        "Home" if re.search(r"\b(home|cooked|homemade)\b", s) else ""
    drinks = "" if none else (_words(s, DRINKS) or ("drinks" if re.search(r"\bdrinks?\b", s) else ""))
    size = "Heavy" if re.search(r"\b(heavy|big|large|huge|stuffed)\b", s) else \
        "Light" if re.search(r"\b(light|small|little)\b", s) else ""
    return {"at": f"{t // 60:02d}:{t % 60:02d}", "meal": meal, "where": where, "protein": _words(s, PROTEIN),
            "veg": _words(s, VEG), "drinks": drinks, "none": none, "size": size}


TEXT = ("where", "protein", "veg", "drinks", "size", "words", "by", "saved_at")


def load(rec) -> list:
    """Every meal kept, oldest first, each with a sound day and time, and each field in its own type: a word that came
    back as something else reads as empty, and "none" is true only as true itself."""
    out = []
    for m in common.read_jsonl(rec / "store" / "meals.jsonl"):
        if not (isinstance(m.get("day"), str) and isinstance(m.get("id"), str) and isinstance(m.get("meal"), str)
                and re.fullmatch(r"\d\d:\d\d", str(m.get("at") or ""))):
            continue
        try:
            dt.date.fromisoformat(m["day"])
        except ValueError:
            continue
        out.append(dict(m, none=m.get("none") is True, **{k: m[k] if isinstance(m[k], str) else "" for k in TEXT if k in m}))
    return sorted(out, key=lambda m: (m["day"], m["at"]))
