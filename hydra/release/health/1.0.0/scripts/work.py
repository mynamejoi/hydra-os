"""The working-out, in code and with no model: the 14 days ending on the last day read, each reading against the person's usual, the
days that prove a finding, tonight's lights out, and one plain line for each reading.

- The window is the 14 days ending on the last day read, the same 14 as every tile on Home. An export is a snapshot,
  so an old one keeps the page full at its own day, and the lines name that day and its night rather than say
  today and last night, with no plan for tonight and no suggestion about today.
- Readings are by morning. Lights out is by night, so its last bar is tonight's, still open: the plan.
- Four readings: Sleep, Lights out, Resting heart, then the week's Workouts, how many in the 7 days to the last day
  read against the usual week, with each day's minutes as its bar. A source with its own morning score (Recovery,
  Readiness or Body Battery) shows that score in Workouts' place.
- A usual is the middle of the last 30 days, shown once 7 of them hold a value ("Your usual shows once your export holds 7 nights.").
- A day wears the app's colour only when it proves the finding: a morning after a night with drinks, a short night
  after a late one, a morning well over the usual resting heart, a night that ran late.
- Every line here is worked out from the person's own figures. A model may reword one (judge.py), and never changes a
  figure. Lines here stay when no model answers, so the page always fills.

Suggestions are about sleep, training load, recovery and meals only, each with its reason from the same figures. Never
a diagnosis, a medicine, a supplement or a dose; a reading that looks like a health problem says "worth asking a
doctor".

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import datetime as dt
import statistics

import days as D

N = 14
USUAL_DAYS, USUAL_MIN = 30, 7
LATE = 45            # minutes past the usual lights out that make a night a late one
LOW, OVER = 10, 5    # a morning this far under the usual score is a low one; a resting heart this far over is up
DOCTOR = (8, 3)      # this far over the usual resting heart, this many mornings running: worth asking a doctor
SCALE = {"rec": (0, 100), "workouts": (0, 60), "sleep": (4, 9.5), "heart": (44, 60), "out": (450, 690)}
COUNT = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "13", "14")


def _number(n: int) -> str:
    return str(COUNT[n] if 0 <= n < len(COUNT) else n)


def _plural(n: int, word: str) -> str:
    return f"{_number(n)} {word}{'' if n == 1 else 's'}"


def _capital(text: str) -> str:
    """A line as a person reads it starts with a capital, as every tile line does,
    the way Home's kit.capital() leaves one: a first word with a capital of its own, like "iPhone", stays as it is."""
    first = text.split(" ", 1)[0]
    if not text[:1].islower() or any(ch.isupper() for ch in first[1:]):
        return text
    return text[0].upper() + text[1:]


def _usual(values: list):
    got = [v for v in values if v is not None]
    return statistics.median(got) if len(got) >= USUAL_MIN else None


def _still(values: list) -> int:
    return max(1, USUAL_MIN - len([v for v in values if v is not None]))


def _after(n: int) -> str:
    """A short history's line: an export is a snapshot, so no count of days to wait."""
    return f"Your usual shows once your export holds {USUAL_MIN} nights."


def _hours(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".") if x != int(x) else str(int(x))


def _hrs(x: float) -> str:
    """Hours with their word, singular for one: "1 hour", "0.8 hours", "8.5 hours"."""
    return f"{_hours(x)} hour{'' if _hours(x) == '1' else 's'}"


def _clock(mins_after_noon) -> str:
    t, half = D.clock12(D.hhmm(int(mins_after_noon) + 720))
    return f"{t} {half}"


def _span(dates: list) -> str:
    a = dates[0]
    return f"{a:%b} {a.day}"


def _words(day: dt.date, now_day=None) -> dict:
    """How the lines name the last day read and the night before it: "this morning", "today" and "last night" while
    it's the person's own day, else their names, in the past tense ("on Monday", "Sunday night")."""
    if now_day is None or day >= now_day:
        return {"fresh": True, "is": "is", "on": "this morning", "day": "today", "night": "last night",
                "Night": "Last night", "Day": "Today", "to": "today"}
    eve = day - dt.timedelta(days=1)
    return {"fresh": False, "is": "was", "on": f"on {day:%A}", "day": f"on {day:%A}", "night": f"{eve:%A} night",
            "Night": f"{eve:%A} night", "Day": f"{day:%A}", "to": f"{day:%a %b} {day.day}"}


def build(rows: dict, meals: list, today: dt.date, now_day=None, kinds=None) -> dict:
    """Everything the page, Home and the judge are handed. rows: {day: row} (days.py). meals: meals.load(). today is
    the last day read (goals.last_day), which the 14 days end on; now_day is the person's own day, when that's later.
    kinds: the kinds of session the person's goals count ("swim", or "" for any), whose days the Workouts card lights."""
    w = _words(today, now_day)
    dates = [today - dt.timedelta(days=N - 1 - i) for i in range(N)]
    back = [today - dt.timedelta(days=k) for k in range(1, USUAL_DAYS + 1)]   # the 30 days before today

    def val(day, field):
        return (rows.get(day.isoformat()) or {}).get(field)

    def night(day):   # the evening of `day`: the lights out of the sleep that ended the next morning
        return D.evening(val(day + dt.timedelta(days=1), "lights_out"))

    rec = [val(d, "readiness") for d in dates]
    # sleep, or time in bed where no night in these days holds any sleep: an iPhone with no watch
    bed = not any(val(d, "sleep_hours") is not None for d in dates + back) and any(val(d, "bed_hours") is not None for d in dates + back)
    s_field = "bed_hours" if bed else "sleep_hours"
    slp = [val(d, s_field) for d in dates]
    rhr = [val(d, "resting_heart") for d in dates]
    out = [night(d) for d in dates[:-1]] + [None]                             # tonight's is the plan, below
    u_rec, u_slp, u_rhr = (_usual([val(d, f) for d in back]) for f in ("readiness", s_field, "resting_heart"))
    nights = [night(d) for d in back]
    u_out = _usual(nights)
    wakes = [D.minutes(val(d, "woke")) for d in [today] + back]
    u_wake = _usual(wakes[1:])
    name = next((r.get("readiness_name") for r in (rows.get(d.isoformat()) or {} for d in reversed(dates)) if r.get("readiness_name")),
                "Readiness")
    drinks = {m["day"] for m in meals if m.get("drinks")}
    after_drinks = [i for i, d in enumerate(dates) if (d - dt.timedelta(days=1)).isoformat() in drinks]
    late = [i for i, v in enumerate(out) if v is not None and u_out is not None and v >= u_out + LATE]

    # tonight's lights out: the usual wake time, less the usual night and a quarter hour to fall asleep, in 15s;
    # it needs both usuals, so it appears with them
    plan = None
    if w["fresh"] and u_wake is not None and u_slp is not None:   # a plan for tonight comes only from tonight's days
        plan = int((u_wake - u_slp * 60 - 15) // 15 * 15 - 720) % 1440
        if u_out is not None:
            plan = max(int(u_out) - 60, min(int(u_out) + 30, plan))
    out[-1] = plan

    back_rec = [val(d, "readiness") for d in back]
    if any(v is not None for v in rec + back_rec):   # the source's own morning score, in Workouts' place
        fourth = _rec(name, rec, u_rec, after_drinks, back_rec, dates, w)
    else:   # Apple Health's export, or a file of days with no score of its own
        fourth = _workouts(rows, dates, back, kinds, w)
    cards = [_sleep(slp, u_slp, out, late, [val(d, s_field) for d in back], dates, w, bed),
             _out(out, u_out, late, plan, nights, dates, w),
             _heart(rhr, u_rhr, [val(d, "resting_heart") for d in back], dates, w),
             fourth]
    by = {c["id"]: c for c in cards}
    food = _food(meals, dates, slp, u_slp, plan, w, bed)
    have = any(v is not None for c in cards for v in c["values"][:-1]) or any(c["today"] is not None for c in cards)

    suggestions = _suggest(by, plan) if w["fresh"] else []   # never advice about today from old days
    real = (now_day or today).isoformat()
    newest = max((k for k in rows if k <= real), default=None)   # the newest day with a reading
    old = newest is not None and today < (now_day or today) - dt.timedelta(days=1)   # the last day read
    return {"today": today.isoformat(), "fresh": w["fresh"], "newest": newest, "old": old, "days": [d.isoformat() for d in dates], "from": _span(dates), "have": have,
            "name": name, "cards": cards, "plan": D.hhmm(plan + 720) if plan is not None else None,
            "woke": D.hhmm(wakes[0]) if wakes[0] is not None else None,
            "suggestions": suggestions, "headline": _headline(by, have), "lead": _lead(by, have), "food": food,
            "counts": {"days": len(rows), "window": sum(1 for d in dates if d.isoformat() in rows)},
            "meals_after": any(str(m.get("day")) > today.isoformat() for m in meals)}   # logged past the last day read


def _card(cid, name, unit, values, usual, usual_text, lit, today_text, line, short, moved, why, label, still, **more):
    lo, hi = SCALE[cid]
    got = [v for v in values + ([usual] if usual is not None else []) if v is not None]
    if got:
        lo, hi = min(lo, int(min(got)) - (0 if cid == "rec" else 1)), max(hi, int(max(got)) + (0 if cid == "rec" else 1))
    c = {"id": cid, "name": name, "unit": unit, "values": [None if v is None else round(v, 2) for v in values],
         "scale": [lo, hi], "usual": None if usual is None else round(usual, 2),
         "key": f"Your usual {usual_text}" if usual is not None else _after(still),
         "lit": lit if usual is not None else [], "fig": today_text, "today": values[-1],
         "line": _capital(line), "short": _capital(short), "moved": moved, "why": why, "label": label}
    c.update(more)
    return c


def _rec(name, v, usual, after_drinks, back, dates, w):
    t = v[-1]
    lows = [i for i in after_drinks if v[i] is not None and usual is not None and v[i] <= usual - LOW]
    lit = [i for i in after_drinks if v[i] is not None] if after_drinks else \
        [i for i, x in enumerate(v) if x is not None and usual is not None and x <= usual - LOW - 5]
    cause = ""
    if lows and len(lows) == len([i for i in after_drinks if v[i] is not None]):
        cause = " The low followed drinks." if len(lows) == 1 else " Both lows followed drinks." if len(lows) == 2 \
            else f" All {COUNT[len(lows)]} lows followed drinks."
    if t is None:
        line = short = f"No reading {w['on']}."
        moved, why = "", f"{name} is the morning's read on how much today can take."
    elif usual is None:
        line = f"{round(t)}% {w['on']}. {_after(_still(back))}"
        short, moved, why = f"{name} {w['is']} {round(t)}% {w['on']}.", "", "Your usual is the middle of your last 30 days."
    else:
        d = round(t - usual)
        base = f"{d} over your usual." if d >= OVER else f"{-d} under your usual." if d <= -OVER else "In line with your usual."
        line = base + cause
        short = f"{name} {w['is']} {round(t)}%, {base[0].lower() + base[1:]}"
        moved = f"up {d}" if d >= OVER else f"down {-d}" if d <= -OVER else "steady"
        why = f"{round(t)}% against your usual of {round(usual)}%."
    label = (f"{name} each morning for the last 14 days, {_span(dates)} to {w['to']}"
             + (f", against your usual of {round(usual)}." if usual is not None else ".")
             + (f" {w['Day']} {w['is']} {round(t)}." if t is not None else ""))
    return _card("rec", name, "%", v, usual, f"{round(usual)}" if usual is not None else "", lit,
                 str(round(t)) if t is not None else "", line, short, moved, why, label, _still(back), lows=lows)


def _sleep(v, usual, out, late, back, dates, w, bed=False):
    """Hours of sleep each night, or with an iPhone and no watch, hours in bed, named so: "In bed"."""
    name, of = ("In bed", "in bed") if bed else ("Sleep", "of sleep")
    t = v[-1]
    lit = [i for i in range(1, N) if (i - 1) in late and v[i] is not None]
    short_nights = [i for i in lit if usual is not None and v[i] <= usual - 1]
    cause = ""
    if short_nights:
        i = min(short_nights, key=lambda k: v[k])
        cost = round((usual - v[i]) * 2) / 2
        cause = f" {dates[i - 1]:%A}'s {_clock(out[i - 1]).split()[0]} lights out cost {_hours(cost)} hour{'' if cost == 1 else 's'}."
    if t is None:
        line = short = f"No {'time in bed' if bed else 'sleep'} for {w['night']}."
        moved, why = "", "Sleep is the night behind this morning's reading."
    elif usual is None:
        line = f"{_hrs(round(t, 1))} {w['night']}. {_after(_still(back))}"
        short, moved, why = f"{name} was {_hrs(round(t, 1))} {w['night']}.", "", "Your usual is the middle of your last 30 nights."
    else:
        d = round(t - usual, 1)
        base = f"{_hrs(d)} over your usual." if d >= 0.5 else f"{_hrs(-d)} under your usual." if d <= -0.5 \
            else "In line with your usual."
        line = base + cause
        short = f"{name} was {_hrs(round(t, 1))}, {base[0].lower() + base[1:]}"
        moved = f"up {_hours(d)} h" if d >= 0.5 else f"down {_hours(-d)} h" if d <= -0.5 else "steady"
        why = f"{_hrs(round(t, 1))} against your usual of {_hours(round(usual, 1))}."
    label = (f"Hours {of} each night for the last 14 days, {_span(dates)} to {w['to']}"
             + (f", against your usual of {_hours(round(usual, 1))}." if usual is not None else ".")
             + (f" {w['Night']} was {_hours(round(t, 1))}." if t is not None else ""))
    return _card("sleep", name, "h", v, usual, f"{_hours(round(usual, 1))} h" if usual is not None else "", lit,
                 _hours(round(t, 1)) if t is not None else "", line, short, moved, why, label, _still(back))


def _workouts(rows, dates, back, kinds, w):
    """The week's workouts: how many sessions in the 7 days to the last day read,
    against the usual week, with each day's minutes as its bar and the days of a goal's kind lit. The usual week is
    the sessions in the 30 days before, over the days of them the reading covers, once it covers 7. Its dashed line
    is a usual workout's minutes. None of it shows for a source that gives no workouts."""
    def got(d, f):
        return (rows.get(d.isoformat()) or {}).get(f)

    def count(d):
        return len(D.kinds(got(d, "sports")))

    if not any(D.kinds(r.get("sports")) or r.get("workout_minutes") for r in rows.values()):
        return _card("workouts", "Workouts", "", [None] * N, None, "", [], "", "", "", "", "", "", 1, week={"count": 0, "usual": None})
    v = [got(d, "workout_minutes") for d in dates]
    t = sum(count(d) for d in dates[-7:])
    first = min(rows) if rows else None
    covered = [d for d in back if first is not None and d.isoformat() >= first]
    usual = round(sum(count(d) for d in covered) * 7 / len(covered)) if len(covered) >= USUAL_MIN else None
    mins = [m for m in (got(d, "workout_minutes") for d in covered) if m]
    ref = statistics.median(mins) if usual is not None and mins else None
    lit = [i for i, d in enumerate(dates) if kinds and any(k == "" or k in D.kinds(got(d, "sports")) for k in kinds) and count(d)]
    week = "this week" if w["fresh"] else f"in the week to {w['to']}"
    if usual is None:
        line = f"{_plural(t, 'workout')[0].upper() + _plural(t, 'workout')[1:]} {week}. {_after(USUAL_MIN)}"
        short, moved, why = f"{_plural(t, 'workout')} {week}.", "", "Your usual is your week over the last 30 days."
    else:
        d = t - usual
        base = "In line with your usual week." if d == 0 else \
            f"{_plural(-d, 'workout')} short of your usual week." if d < 0 else f"{_plural(d, 'workout')} over your usual week."
        base = base[0].upper() + base[1:]
        line = base
        # Home's tile line, one sentence of at most 60 characters: "that week" once the days aren't today's,
        # as the card's own unit says it and as the other cards' lines name no day (the tile's caption gives it once
        # they're old), and the count against the usual names no noun twice
        than = "in line with your usual week" if d == 0 else \
            f"{_number(-d)} short of your usual week" if d < 0 else f"{_number(d)} over your usual week"
        short = f"{_plural(t, 'workout')} {'this week' if w['fresh'] else 'that week'}, {than}."
        moved = "steady" if d == 0 else f"up {d}" if d > 0 else f"down {-d}"
        why = f"{t} in the 7 days to {w['to']}, against your usual of {usual} a week."
    label = (f"Workout minutes each day for the last 14 days, {_span(dates)} to {w['to']}"
             + (f", against your usual of {usual} a week." if usual is not None else ".")
             + f" {t} {week}.")
    return _card("workouts", "Workouts", "this week" if w["fresh"] else "that week", v, ref,
                 f"{usual} a week" if usual is not None else "", lit, str(t), line, short, moved, why, label, 1,
                 week={"count": t, "usual": usual})


def _heart(v, usual, back, dates, w):
    t = v[-1]
    lit = [i for i, x in enumerate(v) if x is not None and usual is not None and x - usual >= OVER]
    over, runs = DOCTOR
    ask = usual is not None and all(x is not None and x - usual >= over for x in v[-runs:])
    if t is None:
        line = short = f"No resting heart {w['on']}."
        moved, why = "", "Resting heart is how hard the body is working at rest."
    elif usual is None:
        line = f"{round(t)} {w['on']}. {_after(_still(back))}"
        short, moved, why = f"Resting heart {w['is']} {round(t)} {w['on']}.", "", "Your usual is the middle of your last 30 days."
    else:
        d = round(t - usual)
        if ask:
            line = f"Up {d} for {COUNT[runs]} mornings. Worth asking a doctor if it stays up."
        else:
            line = f"Up {d} on your usual." if d >= OVER else f"Down {-d} on your usual." if d <= -OVER \
                else "In line with your usual."
        short = f"Resting heart {w['is']} {round(t)}, {'up ' + str(d) if d >= OVER else 'down ' + str(-d) if d <= -OVER else 'in line with'}" \
                + (" on your usual." if abs(d) >= OVER else " your usual.")
        moved = f"up {d}" if d >= OVER else f"down {-d}" if d <= -OVER else "steady"
        why = f"{round(t)} against your usual of {round(usual)}."
    label = (f"Resting heart rate each morning for the last 14 days, {_span(dates)} to {w['to']}"
             + (f", against your usual of {round(usual)}." if usual is not None else ".")
             + (f" {w['Day']} {w['is']} {round(t)}." if t is not None else ""))
    return _card("heart", "Resting heart", "bpm", v, usual, f"{round(usual)} bpm" if usual is not None else "", lit,
                 str(round(t)) if t is not None else "", line, short, moved, why, label, _still(back), ask=bool(ask))


def _out(v, usual, late, plan, back, dates, w):
    seen = [x for x in v[-8:-1] if x is not None]
    first, last_ = (_clock(min(seen)).split()[0], _clock(max(seen)).split()[0]) if seen else ("", "")
    ran = "" if len(seen) < 2 else \
        f"The last {_plural(len(seen), 'night')} ran {first} to {last_}." if first != last_ else \
        f"The last two nights were both at {first}." if len(seen) == 2 else f"The last {_plural(len(seen), 'night')} were all at {first}."
    last = next((x for x in reversed(v[:-1]) if x is not None), None)
    if plan is not None:
        fig, half = _clock(plan).split()
        line = ("Tonight's plan. " + ran).strip()
        short = f"Lights out tonight is {fig} {half}."
        why = "It leaves room for your usual night before your usual wake time."
    elif last is not None:
        fig, half = _clock(last).split()
        i = max(k for k, x in enumerate(v[:-1]) if x is not None)
        named = "Last night" if w["fresh"] and i == N - 2 else f"{dates[i]:%A} night"   # v[i] is the evening of dates[i]
        if usual is None:   # a short history: no usual to set it against yet
            line = f"{named}. {_after(_still(back))}"
        else:   # set against the usual the chart draws (never "Your usual shows once..." beside it)
            gap = round(last - usual)
            far = f"{_hours(round(abs(gap) / 60, 1))} hours" if abs(gap) >= 60 else f"{abs(gap)} minutes"
            line = f"{named}. " + ("In line with your usual." if abs(gap) < 15 else
                                   f"{far} {'later' if gap > 0 else 'earlier'} than your usual.")
        short = f"Lights out {named if named != 'Last night' else 'last night'} was {fig} {half}."
        why = "Your usual is the middle of your last 30 nights."
    else:
        fig, half, line, short = "", "", "No night read yet.", "No night read yet."
        why = "Lights out is when each night began."
    label = (f"Lights out each night for the last 14 days, {_span(dates)} to {w['to']}"
             + (f", against your usual of {_clock(usual).split()[0]}." if usual is not None else ".")
             + (f" Tonight's plan is {fig}." if plan is not None else ""))
    return _card("out", "Lights out", half, v, usual, _clock(usual).split()[0] if usual is not None else "", late,
                 fig, line, short, "", why, label, _still(back), plan=N - 1 if plan is not None else None)


def _food(meals: list, dates: list, slp: list, u_slp, plan, w, bed=False):
    """Food and drink, against sleep: a row for each kind and a column for each night,
    on the same 14 days, with that night's sleep under them. None until a meal in the window is logged. Observations
    only: what was eaten and when, never a plan or a count of calories."""
    by_day = {}
    for m in meals:
        by_day.setdefault(m["day"], []).append(m)
    if not any(d.isoformat() in by_day for d in dates):
        return None
    cutoff = plan - 180 if plan is not None else 360      # three hours before lights out, else 6 pm; minutes after noon
    shut = D.clock12(D.hhmm(cutoff + 720))[0]

    def of(i, meal=None):
        return [m for m in by_day.get(dates[i].isoformat(), []) if meal is None or m["meal"] == meal]

    def mark(kind, i):
        din, any_ = of(i, "Dinner"), of(i)
        if kind == "dinner":
            got = None if not din else not any(m.get("where") in ("Takeout", "Out") for m in din)
        elif kind == "drinks":
            got = True if any(m.get("drinks") for m in any_) else False if any(m.get("none") for m in any_) or i < N - 1 else None
        elif kind == "veg":
            got = True if any(m.get("veg") for m in din) else None if i == N - 1 else False
        elif kind == "protein":
            got = True if any(m.get("protein") for m in of(i, "Breakfast")) else None if i == N - 1 else False
        else:
            got = None if not din else any(D.minutes(m["at"]) - 720 > cutoff for m in din)
        if got is None:
            return "t" if i == N - 1 else "n"     # today is still open until its own log settles it
        return ("a" if kind == "drinks" else "y") if got else "n"

    rows = []
    for kind, label, unit in (("dinner", "Dinner at home", "night"), ("drinks", "With drinks", "night"),
                              ("veg", "Vegetables at dinner", "night"),
                              ("late", f"Dinner after {shut[:-3] if shut.endswith(':00') else shut}", "night")):
        marks = [mark(kind, i) for i in range(N)]
        n = sum(1 for x in marks if x in ("y", "a"))
        rows.append({"id": kind, "label": label, "marks": marks, "count": f"{n} {unit}{'' if n == 1 else 's'}"})
    night = slp[1:] + [None]   # a dinner's night is the sleep that ended the next morning
    nights = [i for i in range(N - 1) if rows[1]["marks"][i] == "a" and night[i] is not None]
    short = [night[i] for i in nights if u_slp is not None and night[i] <= u_slp - 0.5]
    lead = ""
    if short and len(short) == len(nights):
        said = " and ".join(_hours(round(v, 1)) for v in short[:2])
        lead = f"The night with drinks was a short one, {said} hours." if len(short) == 1 else \
            f"Both nights with drinks were short ones, {said} hours." if len(short) == 2 else \
            f"All {COUNT[len(short)]} nights with drinks were short ones."
    what = "In bed" if bed else "Sleep"
    out = {"rows": rows, "lead": lead,
           "why": f"{what} after drinks, against your usual of {_hours(round(u_slp, 1))} hours." if lead else "",
           "caption": f"Kitchen closes at {shut}, three hours before lights out." if plan is not None else "",
           "label": f"The last 14 days of meals, {_span(dates)} to {w['to']}. {rows[0]['label']} on {rows[0]['count']}, "
                    f"with drinks on {rows[1]['count']}."}
    if any(v is not None for v in night):
        lo, hi = SCALE["sleep"]
        got = [v for v in night + [u_slp] if v is not None]
        bars = {"label": f"{what}, that night", "values": [None if v is None else round(v, 2) for v in night],
                "min": min(lo, int(min(got)) - 1), "max": max(hi, int(max(got)) + 1), "lit": [i for i in nights if night[i] in short],
                "count": " and ".join(f"{_hours(round(v, 1))} h" for v in short[:3])}
        if u_slp is not None:
            bars["ref"] = {"value": round(u_slp, 2), "label": f"Your usual {_hours(round(u_slp, 1))} h"}
        out["bars"] = bars
    return out


def _suggest(by: dict, plan) -> list:
    """Up to three, each with its reason and the reading it answers, worked out by rule."""
    out, rec, heart, sleep = [], by.get("rec"), by["heart"], by["sleep"]
    unit = ""

    def add(text, why, answers):
        if len(out) < 3 and text not in [s["text"] for s in out]:
            out.append({"text": text, "why": why, "answers": answers})

    d_heart = round(heart["today"] - heart["usual"]) if heart["today"] is not None and heart["usual"] is not None else None
    d_rec = round(rec["today"] - rec["usual"]) if rec and rec["today"] is not None and rec["usual"] is not None else None
    if heart.get("ask"):
        add("I'd rest today.", f"Resting heart has run {d_heart} over your usual.", "heart")
    elif d_heart is not None and d_heart >= OVER:
        add("I'd keep today easy.", f"Resting heart is {d_heart} over your usual.", "heart")
    if d_rec is not None and d_rec <= -LOW:
        add("I'd keep today easy.", f"{rec['name']} is {-d_rec}{unit} under your usual.", rec["id"])
    elif d_rec is not None and d_rec >= OVER and not out:
        add("I'd train today.", f"{rec['name']} is {d_rec}{unit} over your usual.", rec["id"])
    if sleep["today"] is not None and sleep["usual"] is not None and sleep["today"] <= sleep["usual"] - 1 and plan is not None:
        add(f"I'd turn in by {_clock(plan).split()[0]} tonight.",
            f"Last night was {_hrs(round(sleep['usual'] - sleep['today'], 1))} under your usual.", "sleep")
    return out


def _headline(by: dict, have: bool) -> str:
    rec, heart = by.get("rec"), by["heart"]
    if not have:
        return "Nothing has come in yet."
    if (rec is None or rec["usual"] is None) and heart["usual"] is None:
        return "Settling in."
    up = heart["today"] is not None and heart["usual"] is not None and heart["today"] - heart["usual"] >= OVER
    low = rec is not None and rec["today"] is not None and rec["usual"] is not None and rec["today"] <= rec["usual"] - LOW
    if heart.get("ask"):
        return "A rest day."
    if up or low:
        return "An easy day."
    if rec is not None and rec["today"] is not None and rec["usual"] is not None:
        return "Good to train."
    return "A steady day."


def _lead(by: dict, have: bool) -> dict:
    """The one reading Home's tile shows: the one that moved most against its usual."""
    rec, heart, sleep = by.get("rec") or by["workouts"], by["heart"], by["sleep"]
    if not have:
        return {"card": sleep["id"], "word": "Nothing in yet"}

    def gap(c, per):
        if c["id"] == "workouts":   # the week's count against the usual week, never minutes against a week
            wk = c.get("week") or {}
            return abs(wk["count"] - wk["usual"]) / per if wk.get("usual") is not None else 0
        return abs(c["today"] - c["usual"]) / per if c["today"] is not None and c["usual"] is not None else 0

    pick = max((heart, rec, sleep), key=lambda c: gap(c, {"heart": OVER, "rec": LOW, "workouts": 1, "sleep": 1}[c["id"]]))
    if gap(pick, 1) == 0:
        pick = next((c for c in (sleep, heart, rec) if c["today"] is not None), sleep)
    word = _headline(by, have).rstrip(".")   # the tile's word is the page's own: how today stands
    return {"card": pick["id"], "word": word}
