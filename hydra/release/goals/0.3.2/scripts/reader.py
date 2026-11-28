"""How a goal's typed line is read, in code and never by a model: a date, a count,
a sum or a rate. Which app counts it is that app's to say. What can't
be read is left out, and the page says what's missing, so Claude can ask for it and the save path can fill it in after
a yes.

    read("Swim twice a week by Aug 1", today)  ->  {"by": date, "rate": {"n": 2, "per": "week"}, "unit": "swims"}

The same line and the same day always read the same way. Nothing here is saved by itself.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re

# Which page counts a goal isn't read from its words: each page's `fits` and its own check say so
# (scripts/pages.py), so no page is named here.

MONTH = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?"
         r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
MONTH_DAY = re.compile(rf"\b(?:by|before|until|till|through|in|on|of)\s+(?:the\s+)?(?:end\s+of\s+)?{MONTH}\b\.?"
                       r"(?:\s+(\d{1,2})(?:st|nd|rd|th)?(?![\d:]))?(?:,?\s+(20\d\d))?")
ISO_DAY = re.compile(r"\b(?:by|before|until|till|on)\s+(20\d\d)-(\d\d)-(\d\d)\b")
IN_SPAN = re.compile(r"\bin\s+(\d{1,3}|an?|one|two|three|four|five|six)\s+(day|week|month)s?\b")
SEASON = re.compile(r"\b(by|before|until|till|in|next)\s+(spring|summer|fall|autumn|winter)\b")
SEASONS = {"spring": (3, 20), "summer": (6, 21), "fall": (9, 22), "autumn": (9, 22), "winter": (12, 21)}
NUMBERS = {"a": 1, "an": 1, "one": 1, "once": 1, "two": 2, "twice": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9, "ten": 10}
RATE = re.compile(r"(?<![\w.:])([$€£]?)(\d[\d,]*(?:\.\d+)?|an?|one|two|three|four|five|six|seven|eight|nine|ten|once"
                  r"|twice)\s+((?:[a-z][a-z-]*\s+){0,2}?)(?:a|per|each|every)\s+(day|week|month)\b")
EVERY = re.compile(r"\b(?:every|each)\s+(day|week|month|morning|night|evening)\b|\b(dai|week|month|night)ly\b")
MONEY = re.compile(r"([$€£])\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m)?\b")
# a distance: a 5k or a 10k, 21.1 km, 5 miles, a mile, a half marathon (21.1 km) or a marathon (42.2 km)
DISTANCE = re.compile(r"\b(half[- ]marathon|marathon|(\d[\d,]*(?:\.\d+)?)\s?(k|km|kms|kilomet(?:er|re)s?|miles?|mi)"
                      r"|(?:a|one)\s+(mile|km|kilomet(?:er|re)))\b")
DISTANCES = ("km", "miles")  # what a distance is kept in. Wellbeing counts sessions, not distances
IN_KM = {"k", "km", "kms", "kilometer", "kilometers", "kilometre", "kilometres"}
IN_MILES = {"mi", "mis", "mile", "miles"}
MOVING = re.compile(r"\b(run|race|walk|jog|swim|ride|bike|cycle|row|hike)\w*\b|marathon")
COUNT = re.compile(r"(?<![\w.$:])(\d[\d,]*(?:\.\d+)?)\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")
STOP = {"this", "by", "a", "an", "per", "in", "on", "of", "to", "before", "until", "through", "without", "every",
        "each", "next", "and", "or", "the", "for", "with", "from", "at", "day", "days", "week", "weeks", "month",
        "months", "year", "years", "am", "pm", "percent", "times", "time", "x"}
# What a rate counts when its line names no thing: the line's first word, as the thing it does
DOING = {"swim": "swims", "run": "runs", "jog": "runs", "walk": "walks", "ride": "rides", "bike": "rides",
         "cycle": "rides", "lift": "lifts", "row": "rows", "hike": "hikes", "climb": "climbs", "stretch": "stretches",
         "meditate": "sessions", "practice": "sessions", "train": "sessions", "exercise": "sessions",
         "post": "posts", "publish": "posts", "call": "calls", "cook": "meals", "write": "sessions",
         "read": "sessions", "study": "sessions"}


def read(line: str, today: dt.date) -> dict:
    """What the line gives, of "by" (a day), "target", "unit" and "rate". Only what it says."""
    s = " ".join(str(line).lower().split())
    out = {}
    by, s_rest = _date(s, today)
    if by is not None:
        out["by"] = by
    out.update(_measure(s_rest, s))
    return out


def distance_unit(unit) -> str:
    """A unit in the words that name a distance, as Goals keeps it: "km" or "miles". Any other unit as it is."""
    u = str(unit or "").strip().lower()
    return "km" if u in IN_KM else "miles" if u in IN_MILES else unit


# ---- the date -----------------------------------------------------------------------------------------------------

def _next(month: int, day: int, today: dt.date) -> dt.date:
    """That day of that month, this year when it's still ahead, else next year's."""
    for year in (today.year, today.year + 1):
        d = dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if d >= today:
            return d
    return d


def _month_end(year: int, month: int) -> dt.date:
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _date(s: str, today: dt.date):
    """(the day the line names, the line without those words). (None, the line) when it names none."""
    m = ISO_DAY.search(s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), s[:m.start()] + s[m.end():]
        except ValueError:
            pass
    m = MONTH_DAY.search(s)
    if m:
        month = next(i for i, name in enumerate(calendar.month_abbr) if i and m.group(1).startswith(name.lower()))
        day, year = int(m.group(2) or 0), int(m.group(3) or 0)
        if year:
            last = calendar.monthrange(year, month)[1]
            d = dt.date(year, month, min(day or last, last))
        else:
            d = _next(month, day or 31, today)
        return d, s[:m.start()] + s[m.end():]
    m = IN_SPAN.search(s)
    if m:
        n = NUMBERS.get(m.group(1)) or int(m.group(1))
        d = _add_months(today, n) if m.group(2) == "month" else today + dt.timedelta(days=n * (7 if m.group(2) == "week" else 1))
        return d, s[:m.start()] + s[m.end():]
    for rx, give in (
            (r"\bthis year\b|\bend of (?:the )?year\b|\byear.?end\b", lambda: dt.date(today.year, 12, 31)),
            (r"\bnext year\b", lambda: dt.date(today.year + 1, 12, 31)),
            (r"\bthis summer\b", lambda: _next(8, 31, today)),
            (r"\bthis (?:fall|autumn)\b", lambda: _next(11, 30, today)),
            (r"\bthis spring\b", lambda: _next(5, 31, today)),
            (r"\bthis month\b", lambda: _month_end(today.year, today.month)),
            (r"\bnext month\b", lambda: (lambda d: _month_end(d.year, d.month))(_add_months(today.replace(day=1), 1))),
            (r"\bthis week\b", lambda: today + dt.timedelta(days=6 - today.weekday()))):
        m = re.search(rx, s)
        if m:
            return give(), s[:m.start()] + s[m.end():]
    m = SEASON.search(s)
    if m:
        month, day = SEASONS[m.group(2)]
        return _next(month, day, today), s[:m.start()] + s[m.end():]
    return None, s


# ---- the count, the sum or the rate ------------------------------------------------------------------------------

def _num(text: str) -> float:
    n = float(text.replace(",", ""))
    return int(n) if n == int(n) else n


def _plural(word: str) -> str:
    if word.endswith("s"):
        return word
    if re.search(r"(?:x|z|ch|sh)$", word):
        return word + "es"
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    return word + "s"


def _unit(words: str) -> str:
    """The thing counted, plural, in at most 16 characters: both words when they fit, else the last."""
    words = " ".join(w for w in words.split() if w not in ("x", "time", "times"))
    if not words:
        return ""
    whole = " ".join(words.split()[:-1] + [_plural(words.split()[-1])])
    return whole if len(whole) <= 16 else _plural(words.split()[-1])[:16]


def _measure(s: str, whole: str) -> dict:
    """What the line counts, from the line without its date (s); `whole` is the line as typed, for its first word."""
    m = RATE.search(s)
    if m:
        sign, n, what, per = m.groups()
        n = NUMBERS.get(n) or _num(n)
        if n > 0:
            unit = sign or distance_unit(_unit(what)) or DOING.get(whole.split()[0] if whole.split() else "", "times")
            return {"rate": {"n": n, "per": per}, "unit": unit}
    m = EVERY.search(s)
    if m:
        per = m.group(1) or {"dai": "day", "week": "week", "month": "month", "night": "day"}[m.group(2)]
        per = {"morning": "day", "night": "day", "evening": "day"}.get(per, per)
        return {"rate": {"n": 1, "per": per}, "unit": DOING.get(whole.split()[0] if whole.split() else "", "times")}
    m = MONEY.search(s)
    if m:
        n = _num(m.group(2)) * {"k": 1000, "m": 1000000}.get(m.group(3) or "", 1)
        if n > 0:
            return {"target": int(n) if n == int(n) else n, "unit": m.group(1)}
    m = DISTANCE.search(s)
    if m and MOVING.search(s):
        if m.group(2):
            return {"target": _num(m.group(2)), "unit": distance_unit(m.group(3))}
        if m.group(4):
            return {"target": 1, "unit": distance_unit(m.group(4))}
        return {"target": 21.1 if "half" in m.group(1) else 42.2, "unit": "km"}
    for m in COUNT.finditer(s):
        first, second = m.group(2), m.group(3)
        if first in STOP or re.fullmatch(MONTH, first):
            continue
        n = _num(m.group(1))
        if n > 0:
            unit = _unit(first if not second or second in STOP or re.fullmatch(MONTH, second) else f"{first} {second}")
            return {"target": n, "unit": unit}
    return {}
