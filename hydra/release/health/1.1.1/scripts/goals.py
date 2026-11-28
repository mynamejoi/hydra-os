"""Health's progress toward each goal it measures.

Health reads <root>/yours/goals.json for the goals that name it, are active and are read (a start, a target and a
date), and never writes that file. For each, it works the progress out in code and hands it to say.json's `goals`:
the value, the pace by Goals' rule, the day it lands or the value it reaches, one line of why, each change so far,
and how Health counts it.

How Health counts is its own. It counts sessions by kind: a goal whose unit or words name a kind of
session ("swims", "runs", "rides", "walks", "workouts") is the number of those since its start day, from the sessions
its source gave. A distance, in km or miles or in words such as a 10k or a marathon, is never counted as sessions:
Goals keeps it by hand until Health can read distances. A sleep or lights-out goal ("Sleep 7
hours a night", "Lights out by 10:30"), with a unit of nights or none, is the number of nights that met it: sleep of at
least those hours, or lights out at that time or earlier. A goal it
can't count yet says so, with pace `unknown`, and never a guess.

Each goal is paced to the last day read, never to today: an export is a snapshot, so the days after it aren't missed
sessions. Each entry carries that day as `to`, YYYY-MM-DD, so Goals can say "Counted to Mon Jun 16.".

The goal's own words are the person's, and stay in goals.json: nothing here copies them into a line Health writes.
Never a goal about a diagnosis, a medicine, a supplement or a dose (words.py): such a goal is left unmeasured.

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

import common
import days as D
import words

PACE_DAYS = 28
ANY = ("workout", "session", "training", "train", "gym", "exercise")
STEPS = re.compile(r"\bsteps?\b")
UNITS = {k + "s": k for k in D.KINDS}          # "swims": "swim"
UNITS.update({"workouts": "", "sessions": "", "trainings": ""})
DISTANCES = {"km", "kms", "kilometer", "kilometers", "kilometre", "kilometres", "mi", "mile", "miles"}
DISTANCE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:k|km|kms|mi)\b|\b(?:km|kms|kilomet(?:er|re)s?|miles?|marathons?)\b")
PER = {"day": 1, "week": 7, "month": 30.44}
DATA = "your iPhone's Health data"   # what Wellbeing reads, in the onboarding's words
# A sleep or lights-out goal is counted in nights: its unit is
# nights, or it has none, and its words give the hours or the time.
NIGHTS = {"", "night", "nights"}
SLEEP = re.compile(r"\bsleep(?:s|ing)?\b")
HOURS = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:h|hrs?|hours?)\b")
LIGHTS = re.compile(r"\blights?[ -]?out\b|\bin bed\b|\bto bed\b|\bbed ?time\b|\basleep\b")
# a sum of money, by its sign or its word: never a session or a night, whatever it's for
MONEY = re.compile(r"[$€£¥]\s?\d|\b\d[\d,.]*\s?(?:dollars?|euros?|bucks|usd|eur|gbp)\b")
MONEY_UNITS = {"$", "€", "£", "¥", "usd", "eur", "gbp", "dollar", "dollars", "euro", "euros", "bucks"}
BY_TIME = re.compile(r"\b(?:by|before)\s+(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s?m?\.?(?![\w:])")


def _day(text):
    try:
        return dt.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def mine(root) -> list:
    """The goals Health measures: active, naming Health, and read (a start, a target and a date)."""
    doc = common.load_json(root / "yours" / "goals.json", {})
    out = []
    for g in (doc.get("goals") or []) if isinstance(doc, dict) and doc.get("contract") == "goals/v1" else []:
        if not (isinstance(g, dict) and isinstance(g.get("id"), str) and g.get("status") == "active"
                and isinstance(g.get("measured_by"), dict) and g["measured_by"].get("app") == common.ID):
            continue
        start = g.get("start") if isinstance(g.get("start"), dict) else {}
        s_on, by = _day(start.get("on")), _day(g.get("by"))
        nums = [x for x in (start.get("value"), g.get("target")) if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if s_on and by and by > s_on and len(nums) == 2 and nums[0] != nums[1]:
            out.append(g)
    return out


def counts_as(goal: dict):
    """The kind of session a goal counts ("swim"), "" for any session, or None when Health can't count it yet. A unit
    that names a session is counted as it says. A distance never is, by its unit or its words alone: Health counts
    sessions, not distances, so a 10k is never 10 runs."""
    unit = str(goal.get("unit") or "").strip().lower()
    if unit in UNITS:
        return UNITS[unit]
    text = str(goal.get("text") or "").lower()
    if unit in DISTANCES or DISTANCE.search(text):
        return None
    for kind, names in D.KINDS.items():
        if any(re.search(rf"\b{re.escape(n)}s?\b", text) for n in names):
            return kind
    if any(re.search(rf"\b{w}s?\b", text) for w in ANY):
        return ""
    return None


def kinds(root) -> set:
    """The kinds of session the person's goals count ("swim", or "" for any), whose days the Workouts card lights."""
    return {k for k in (counts_as(g) for g in mine(root) if not night_rule(g)) if k is not None}


def _sessions(rows: dict, kind: str, since: dt.date, to: dt.date) -> list:
    """[(day, how many)] for each day with a session of this kind, oldest first."""
    out = []
    for day in sorted(rows):
        d = _day(day)
        if d is None or not since <= d <= to:
            continue
        got = D.kinds(rows[day].get("sports"))
        n = len(got) if kind == "" else got.count(kind)
        if n:
            out.append((d, n))
    return out


def _lights_at(text: str):
    """The latest lights out a goal's words give, as minutes after noon (days.evening), or None. A time with no am or
    pm is the evening's: "by 10:30" is 10:30 pm, "by 12" midnight and "by 1" 1 am."""
    m = BY_TIME.search(text)
    if not m:
        return None
    h, mm, half = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if h > 23 or mm > 59 or (half and not 1 <= h <= 12):
        return None
    if half:
        h = h % 12 + (12 if half == "p" else 0)
    elif 6 <= h <= 11:
        h += 12
    elif h == 12:
        h = 0
    return D.evening(f"{h:02d}:{mm:02d}")


def night_rule(goal: dict):
    """How a sleep or lights-out goal is counted, in nights: ("sleep", hours) for "Sleep 7 hours a night", ("out",
    minutes after noon) for "Lights out by 10:30", or None for a goal that isn't one."""
    unit = str(goal.get("unit") or "").strip().lower()
    text = str(goal.get("text") or "").lower()
    if unit not in NIGHTS:
        return None
    if LIGHTS.search(text):
        at = _lights_at(text)
        if at is not None:
            return ("out", at)
    if SLEEP.search(text):
        m = HOURS.search(text)
        if m and 3 <= float(m.group(1)) <= 12:
            return ("sleep", float(m.group(1)))
    return None


def _nights(rows: dict, rule: tuple, since: dt.date, to: dt.date) -> list:
    """[(day, 1)] for each night that meets the rule, oldest first: its sleep at least the hours, or its lights out at
    the time or earlier."""
    what, at = rule
    out = []
    for day in sorted(rows):
        d = _day(day)
        if d is None or not since <= d <= to:
            continue
        if what == "sleep":   # with no sleep recorded that night, its time in bed (an iPhone with no watch)
            v = rows[day].get("sleep_hours") if rows[day].get("sleep_hours") is not None else rows[day].get("bed_hours")
            met = isinstance(v, (int, float)) and not isinstance(v, bool) and v >= at
        else:
            e = D.evening(rows[day].get("lights_out"))
            met = e is not None and e <= at
        if met:
            out.append((d, 1))
    return out


def _named(text: str):
    """The kind of session a goal's own words name ("swim"), "" for any session, or None."""
    for kind, names in D.KINDS.items():
        if any(re.search(rf"\b{re.escape(n)}s?\b", text) for n in names):
            return kind
    if any(re.search(rf"\b{w}s?\b", text) for w in ANY):
        return ""
    return None


def _night_words(rule: tuple) -> tuple:
    """(the condition a night meets, as a why says it; the counting line) for a night rule."""
    if rule[0] == "sleep":
        return f" of {_n(rule[1])} hours or more", f"Nights of {_n(rule[1])} hours or more in your Health data"
    t, half = D.clock12(D.hhmm(rule[1] + 720))
    return f" with lights out by {t} {half}", f"Nights with lights out by {t} {half} in your Health data"


def check(goal: dict) -> dict:
    """Whether Wellbeing counts a goal, and as what: the one answer Goals' read-back asks before the save, so nothing
    claims a count this doesn't give. It goes by the goal's own
    words, never by its unit alone, and says the unit it's counted in, which is the one to save.

    {"counts": True, "as": "nights" or "sessions", "unit", "kind", "counting"}, or {"counts": False, "why"}."""
    text = str(goal.get("text") or "").lower()
    unit = str(goal.get("unit") or "").strip().lower()
    cant = {"counts": False, "why": f"{common.TITLE} can't tell how to count this yet."}
    if words.care(text):
        return cant
    if unit in MONEY_UNITS or MONEY.search(text):
        return {"counts": False, "why": f"{common.TITLE} doesn't count money."}
    rule = night_rule({"text": goal.get("text"), "unit": ""})   # the words decide, and the unit follows
    if rule:
        return {"counts": True, "as": "nights", "unit": "nights", "kind": None, "counting": _night_words(rule)[1]}
    if STEPS.search(text):
        return {"counts": False, "why": f"{common.TITLE} doesn't read steps yet."}
    if UNITS.get(unit):   # a unit that names a kind of session ("swims") is counted as it says, whatever else the words hold
        kind = UNITS[unit]
        return {"counts": True, "as": "sessions", "unit": unit, "kind": kind, "counting": f"Any {kind} in {DATA}"}
    if unit in DISTANCES or DISTANCE.search(text):
        return cant
    if SLEEP.search(text) or LIGHTS.search(text):
        return {"counts": False, "why": f"{common.TITLE} counts nights once the goal says the hours or the time."}
    kind = _named(text)
    if kind is None:
        return cant
    return {"counts": True, "as": "sessions", "unit": "workouts" if kind == "" else f"{kind}s", "kind": kind,
            "counting": f"Any {'session' if kind == '' else kind} in {DATA}"}


def last_day(rows: dict, today: dt.date, came=None):
    """The last day read, never after today: the day the newest file came in, or a later day with a reading. Days
    with nothing in them leave no row, so the last row alone could be days before the export was made. An export is a
    snapshot, so each goal is paced to that day."""
    got = [d for d in (_day(k) for k in rows) if d is not None and d <= today]
    if got and all(isinstance(r, dict) and r.get("source") == "logged" for r in rows.values()):
        return today   # workouts logged as they go, with no file: a day with none logged had none, so it's today
    c = _day(came) if came else None
    if c is not None:
        got.append(min(c, today))   # a file can't have come in after today
    return max(got) if got else None


def _on(d: dt.date) -> str:
    return f"{d:%a %b} {d.day}"


def progress(goal: dict, rows: dict, today: dt.date, as_of: str, read: bool, came=None) -> dict:
    """One entry for say.json's `goals`, paced to the last day read rather than today, so an old export never reads as
    falling behind for the days after it. `to` is that day."""
    gid = goal["id"]
    start, target, by = goal["start"], float(goal["target"]), _day(goal["by"])
    s_on, s_val = _day(start["on"]), float(start["value"])
    c = check(goal)   # one answer, the one Goals' read-back asks
    if not c["counts"] or target < s_val:
        return {"id": gid, "value": None, "as_of": as_of, "pace": "unknown",
                "why": c.get("why") or f"{common.TITLE} can't tell how to count this yet."}
    if c["as"] == "nights" and str(goal.get("unit") or "").strip().lower() not in NIGHTS:   # its target isn't nights
        return {"id": gid, "value": None, "as_of": as_of, "pace": "unknown",
                "why": f"{common.TITLE} counts this in nights, so it can be set again in nights.",
                # one button on the goal, through Goals' own measure save, with its Undo (goals.md's measure)
                "then": {"words": "Count it in nights", "act": "measure",
                         "fields": {"goal": gid, "app": common.ID, "unit": "nights"}}}
    rule = night_rule({"text": goal.get("text"), "unit": ""}) if c["as"] == "nights" else None
    kind = c["kind"]
    if rule:
        what, (cond, counting) = "night", _night_words(rule)
    else:
        what, cond, counting = ("session" if kind == "" else kind), "", c["counting"]
    to = (last_day(rows, today, came) or today) if read else None
    if to is None:
        return {"id": gid, "value": None, "as_of": as_of, "pace": "unknown", "counting": counting,
                "why": f"{common.TITLE} needs {DATA}."}
    if to < s_on <= today:   # begun, with nothing read since: a goal that starts later is paced, and read as not started
        return {"id": gid, "value": None, "as_of": as_of, "to": to.isoformat(), "pace": "unknown", "counting": counting,
                "why": f"What {common.TITLE} has read ends {_on(to)}, before this goal began."}
    got = _nights(rows, rule, s_on, to) if rule else _sessions(rows, kind, s_on, to)
    total, points = s_val, []
    reached = None
    for d, n in got:
        total += n
        points.append([d.isoformat(), _n(total)])
        if reached is None and total >= target:
            reached = d
    since = max(s_on, to - dt.timedelta(days=PACE_DAYS))
    span = max(1, (to - since).days)
    recent = sum(n for d, n in got if d >= since)
    rate = recent / span
    out = {"id": gid, "value": _n(total), "as_of": as_of, "to": to.isoformat(), "counting": counting, "points": points[-366:]}
    if reached is not None:
        out["lands"] = reached.isoformat()
    else:
        left = (by - to).days
        need = target - total
        lands = to + dt.timedelta(days=int(-(-need // rate))) if rate > 0 else None   # the first day it's there
        if lands is not None and (lands <= by or not goal.get("rate")):
            out["lands"] = lands.isoformat()
        else:
            out["reaches"] = round(total + rate * max(0, left), 1)
    landed = _day(out.get("lands"))
    out["pace"] = "behind" if landed is None or landed > by else "ahead" if (by - landed).days >= 14 else "on"
    r = goal.get("rate") if isinstance(goal.get("rate"), dict) else None
    span_ = "day" if span == 1 else f"{span} days"   # plurals are right everywhere
    when = f"in the last {span_}" if to >= today - dt.timedelta(days=1) else f"in the {span_} to {_on(to)}"
    seen = f"{_count(recent, what)}{cond} {when}"
    if r and r.get("per") in PER and isinstance(r.get("n"), (int, float)):
        out["why"] = f"{seen}, against {_n(r['n'])} a {r['per']}."
    else:
        out["why"] = f"{seen}, with {_n(max(0, target - total))} to go by {by:%b} {by.day}."
    out["why"] = out["why"][0].upper() + out["why"][1:]
    return out


def _n(x):
    return int(x) if float(x) == int(x) else round(float(x), 1)


def _count(n, what: str) -> str:
    n = _n(n)
    word = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, str(n))
    return f"{word} {what}{'' if n == 1 else 's'}"


def count_now(rec, now=None) -> dict:
    """A goal set while the data is already in is counted at once (Goals calls it after
    its save): say.json's `goals` worked out again for yours/goals.json as it stands, from the days already read. No
    source is read and no model is called. say.json is written whole, every other part as it was, `data_to` too.
    {"ok": True, "goals": n}, or {"ok": False, "why"} with nothing written."""
    import days   # noqa: PLC0415
    import meals  # noqa: PLC0415
    import say as say_file  # noqa: PLC0415
    import upload  # noqa: PLC0415
    doc = common.load_json(rec / "say.json", None)
    if not (isinstance(doc, dict) and doc.get("contract") == "say/v1" and doc.get("as_of")):
        return {"ok": False, "why": f"{common.TITLE} hasn't read anything yet."}
    rows = days.load(rec)
    today = meals.owners_day(now or common.now())
    root = common.root_of(rec)
    doc["goals"] = build(root, rows, today, doc["as_of"], read=bool(rows), came=upload.came(rec))
    say_file.write(rec, doc)
    return {"ok": True, "goals": len(doc["goals"])}


def main(argv=None) -> int:
    """The check, as Goals' read-back calls it: python3 goals.py --check '{"text": ..., "unit": ...}'; and the count, as
    Goals calls it after a save: python3 goals.py --count. Each prints one JSON line."""
    ap = argparse.ArgumentParser(description=f"Whether {common.TITLE} counts a goal, and as what, or count the goals now.")
    how = ap.add_mutually_exclusive_group(required=True)
    how.add_argument("--check", help='the goal, as JSON: {"text": ..., "unit": ...}')
    how.add_argument("--count", action="store_true", help="work out the goals' entries now, from the days already read")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    if a.count:
        try:
            got = count_now(common.record_dir(a.record), common.now(a.now) if a.now else None)
        except (OSError, ValueError, KeyError) as e:
            got = {"ok": False, "why": f"{common.TITLE} couldn't count them: {type(e).__name__}."}
        print(json.dumps(got, ensure_ascii=False))
        return 0 if got["ok"] else 1
    try:
        goal = json.loads(a.check)
    except ValueError:
        goal = None
    if not isinstance(goal, dict):
        print(json.dumps({"counts": False, "why": "That isn't a goal."}))
        return 2
    print(json.dumps(check(goal), ensure_ascii=False))
    return 0


def build(root, rows: dict, today: dt.date, as_of: str, read: bool, came=None) -> list:
    """say.json's `goals`: one entry for each goal Health measures, [] when it measures none. came: the day the newest
    file came in (upload.read)."""
    return [progress(g, rows, today, as_of, read, came) for g in mine(root)]


if __name__ == "__main__":
    sys.exit(main())
