"""Goals' own progress for a goal kept by hand.

A goal no installed app measures can be kept by hand: its measured_by is {"app": "goals"}, and each number the person
tells Claude for it is one line in Goals' own record, store/progress.jsonl, saved by act.py's `progress` with their
yes. Goals is then its measuring app: this turns those lines into the goal's entry in Goals' say.json `goals`, at
every run and every save, by the same progress rule as a measured goal's, so every page reads it as any measured goal.

    entries(root, record, doc, today)   say.json's `goals`: one entry for each active, read goal kept by hand

Nothing here writes, and no entry holds a goal's words. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import math

import common
import goalsfile

PROGRESS = "store/progress.jsonl"
QUIET_DAYS = 28  # a number this old says nothing about the pace now
COUNTING = "What you tell Claude"


def told(record) -> dict:
    """{goal id: [(day, value, at)]} from store/progress.jsonl, in the file's order. A line that isn't one is left out."""
    out = {}
    for line in common.lines(record / PROGRESS):
        d, value = common.day(line.get("on")), line.get("value")
        if isinstance(line.get("goal"), str) and d is not None and common.number(value) and isinstance(line.get("at"), str):
            out.setdefault(line["goal"], []).append((d, value, line["at"]))
    return out


def entries(root, record, doc: dict, today: dt.date) -> list:
    """say.json's `goals` for the goals Goals keeps by hand: [] when it keeps none."""
    import reading
    lines = told(record)
    return [entry(g, lines.get(g["id"], []), today, reading.in_first_window(g, today))
            for g in doc["goals"]
            if g.get("status") == "active" and (g.get("measured_by") or {}).get("app") == common.ID and goalsfile.read(g)]


def entry(goal: dict, said: list, today: dt.date, first_window: bool) -> dict:
    """One goal's entry, from the numbers told for it."""
    start_on, start = common.day(goal["start"]["on"]), goal["start"]["value"]
    target, by = goal["target"], common.day(goal["by"])
    up = target > start
    days = {}  # the last number told for each day, from the day it began to today
    for d, value, at in said:
        if start_on <= d <= today:
            days[d] = (value, at)
    order = sorted(days)
    out = {"id": goal["id"], "value": start, "as_of": goal["set"]["at"], "counting": COUNTING,
           "points": [[d.isoformat(), days[d][0]] for d in order][-366:]}
    unit = goal.get("unit")
    if not order:
        if first_window:  # too soon to say: every reader shows it as just started
            out.update(pace="behind", reaches=start,
                       why=f"Counts from {common.with_unit(start, unit)}, as you told Claude.")
        else:
            out.update(pace="unknown", why="Nothing told since it was set. Tell Claude where it stands.")
        return out
    last_on = order[-1]
    last, at = days[last_on]
    out.update(value=last, as_of=at)
    reached = next((d for d in order if (days[d][0] >= target if up else days[d][0] <= target)), None)
    if reached is not None:
        out["lands"] = reached.isoformat()
    elif (today - last_on).days > QUIET_DAYS:
        out.update(pace="unknown", why=f"Last told {common.day_words(last_on, today)}. Tell Claude where it stands.")
        return out
    else:
        rate = (last - start) / max(1, (last_on - start_on).days)  # a day, from where it began to the last number
        need = target - last
        # the first whole day at the target, with room for a float's last digit (45.000000000001 days is 45)
        lands = last_on + dt.timedelta(days=math.ceil(need / rate - 1e-9)) if rate and (need > 0) == (rate > 0) else None
        if lands is not None and (lands <= by or not goal.get("rate")):
            out["lands"] = lands.isoformat()
        else:
            out["reaches"] = round(last + rate * max(0, (by - last_on).days), 1)
    landed = common.day(out.get("lands") or "")
    out["pace"] = "behind" if landed is None or landed > by else "ahead" if (by - landed).days >= 14 else "on"
    out["why"] = (f"{common.with_unit(start, unit)} to {common.with_unit(last, unit)} since "
                  f"{common.day_words(start_on, today)}, as you told Claude on {common.day_words(last_on, today)}.")[:140]
    return out
