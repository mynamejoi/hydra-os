"""Reading a goal: the one way a goal in yours/goals.json and its progress in
the measuring app's say.json become what a page shows. The state, with its word and caption; the share and the plan
of its small plot; who measures a goal that isn't measured yet; the tally; and the order.

The main plugin's kit carries this same reading for every page, as kit.read_goals, and the two read every goal the
same. Goals' run and its save path read through this copy.

    read_goal(goal, entry, app, today, stale=False)   one goal and its say.json entry in, one reading out (pure)
    read_goals(root, now=None, app=None)              {"goals": [...], "tally": "2 of 4 on pace, 2 new"}

Nothing here writes. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import math
import pathlib

import common
import goalsfile
import pages

WORDS = {"aside": "Set aside", "done": "Done", "new": "", "missed": "Missed", "unknown": "Can't tell yet",
         "started": "Just started", "behind": "Behind", "on": "On pace", "ahead": "Ahead"}
COUNTED = ("behind", "on", "ahead", "unknown", "missed")  # the states the tally counts
NEW = ("new", "started")  # the states the tally's ", 2 new" counts
DONE_DAYS = 7  # a done goal stays in hand this long, then joins Goals' quiet list
WEEK = 7  # the first window of a goal that isn't said as a rate


def clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def share_of(goal: dict, value) -> float:
    """How far from its start to its target a value is, held from 0 to 1."""
    start, target = goal["start"]["value"], goal["target"]
    return clamp((value - start) / (target - start))


def plan_of(goal: dict, today: dt.date) -> float:
    """Where a straight path from its start to its target has it today, held from 0 to 1."""
    on, by = common.day(goal["start"]["on"]), common.day(goal["by"])
    return clamp((today - on).days / (by - on).days)


def window_days(goal: dict) -> float:
    """How long a goal's first window is, in days: one of its rate's day, week or calendar month, else a week, and
    never more than half the days from its start to its date."""
    on, by = common.day(goal["start"]["on"]), common.day(goal["by"])
    per = (goal.get("rate") or {}).get("per")
    days = 1 if per == "day" else (common.next_month(on) - on).days if per == "month" else WEEK
    return min(days, (by - on).days / 2)


def in_first_window(goal: dict, today: dt.date) -> bool:
    """A goal too young for its pace to mean anything yet, or one that starts after today."""
    return (today - common.day(goal["start"]["on"])).days < window_days(goal)


def counted_to(entry, today: dt.date) -> dt.date:
    """The last day a goal's app read, its entry's `to`, never after today; else today. An export is a snapshot, so a
    goal's first window and plan mark run to it."""
    to = common.day(entry.get("to")) if isinstance(entry, dict) else None
    return min(to, today) if to is not None else today


def who_measures(goal: dict, app) -> str:
    """Who counts a goal that isn't counted yet, in one line: the first row that holds. Every word a person reads about
    a goal says count, and Hydra-OS's pages are pages."""
    if app is None:
        return "No page counts this yet."
    name = app["title"]
    if not app.get("installed"):
        return f"Add {name} to count this."
    if not goalsfile.read(goal):
        return f"{name} counts it once it has a target and a date."
    if not (app.get("source") or app.get("has_source")) and app.get("needs"):
        what = app["needs"]
        return (f"{name} counts it once {what} {'are' if what.endswith('s') else 'is'} "
                f"{'in' if app.get('uploads_only') else 'connected'}.")
    if app.get("ran") and not app.get("measures"):
        return f"{name} doesn't count goals yet."
    return f"{name} starts counting it tonight."


def how_read(goal: dict, today: dt.date) -> str:
    """How a goal that isn't counted yet is read: "Counted as 17 swims by Aug 1, at 2 a week", else "Not counted yet",
    which the row and the detail's lead say alike; the detail adds the one sentence of what it still needs."""
    line = goalsfile.target_line(goal, today)
    if line:
        return f"Counted as {line}"
    return "Not counted yet"


def read_goal(goal: dict, entry, app, today: dt.date, stale: bool = False) -> dict:
    """One goal's reading. entry: its entry in the measuring app's say.json `goals`, or None. app: None when no
    app measures it, else {"id", "title", "installed", "needs", "source", "ran", "measures"}. stale: that say.json is
    past its stale_after."""
    is_read = goalsfile.read(goal)
    value = entry.get("value") if isinstance(entry, dict) else None
    has_value = is_read and common.number(value)
    upto = counted_to(entry, today)  # its first window and plan mark run to the last day its app read
    to = common.day(entry.get("to")) if isinstance(entry, dict) else None  # the entry's own, said as "Counted to"
    step, do = "", None  # the state's own next step, said after its words, and its page action
    drop = {"words": "", "link": f"{app['id']}#drop"} if app and app.get("uploads_only") else None
    share = share_of(goal, value) if has_value else None
    plan = plan_of(goal, upto) if has_value else None
    by = common.day(goal.get("by")) if goal.get("by") else None
    lands = common.day(entry.get("lands")) if isinstance(entry, dict) else None
    reaches = entry.get("reaches") if isinstance(entry, dict) and common.number(entry.get("reaches")) else None
    as_of = common.parse_time(entry.get("as_of")) if isinstance(entry, dict) else None
    ended = common.day(goal.get("ended")) if goal.get("ended") else None
    pace = entry.get("pace") if isinstance(entry, dict) else None
    status = goal.get("status")

    done_on = None
    if status == "aside":
        state, caption = "aside", common.day_words(ended, today) if ended else ""
    elif status == "done" or share == 1:
        done_on = ended or lands
        state, caption = "done", f"Reached {common.day_words(done_on, today)}" if done_on else ""
        step = "Tell Claude what's next."
    elif not is_read or app is None or not app.get("installed") or entry is None:
        state, caption = "new", f"{how_read(goal, today)}. {who_measures(goal, app)}"
        needs = (app or {}).get("needs") or ""
        if app is None:  # nothing here counts it
            caption, step = "Not counted yet.", "Tell Claude to keep it by hand."
        elif (is_read and app.get("installed") and drop and needs
              and not (app.get("source") or app.get("has_source"))):  # no data in yet
            caption, step = "Not counted yet.", f"{app['title']} needs {needs}."
            do = dict(drop, words=app.get("needs_line") or f"Add {needs}")
    elif by is not None and today > by:
        state, caption = "missed", "Its date has passed."
        step = "Tell Claude a new date, or to set it aside."
    elif stale or pace not in ("behind", "on", "ahead"):
        state = "unknown"
        caption = f"As of {common.day_words(as_of.date(), today)}" if as_of else ""
    elif in_first_window(goal, upto):  # too soon for a pace: the app's lands or reaches is kept, and never shown
        on = common.day(goal["start"]["on"])
        state, caption = "started", f"First update {common.weekday_day(on + dt.timedelta(days=math.ceil(window_days(goal))))}"
    else:
        state = pace
        if lands is not None:
            caption = f"Lands {common.day_words(lands, today)}, due {common.day_words(by, today)}"
        elif reaches is not None:
            percent = int(share_of(goal, reaches) * 100 + 0.5)
            caption = f"Reaches {percent}% by {common.day_words(by, today)}"
        else:
            caption = ""
    if to is not None and (today - to).days > 1 and state in ("behind", "on", "ahead", "unknown", "started"):
        caption = f"Counted to {common.weekday_day(to)}."  # an export that ends before yesterday, and a fresh one offered
        do = dict(drop, words="Add a fresh export") if drop else None
    shown = state not in ("aside", "done", "new")
    if not (shown or state == "done"):
        share = plan = None  # a goal set aside or not measured yet has no small plot
    word = WORDS[state]
    if state == "started" and common.day(goal["start"]["on"]) > today:
        word = "Not started yet"

    figure = ""
    if has_value:
        unit = goal.get("unit")
        figure = (f"{common.with_unit(value, unit)} of {common.with_unit(goal['target'], unit)}" if common.is_sign(unit)
                  else f"{common.figure(value)} of {common.with_unit(goal['target'], unit)}")
    in_hand = status == "active" and state != "done"
    if state == "done" and status != "aside":
        in_hand = done_on is None or 0 <= (today - done_on).days <= DONE_DAYS
    measured = isinstance(entry, dict)  # what its app wrote is passed on as given, whatever the goal's state
    return {
        "id": goal["id"], "text": goal["text"], "why": goal.get("why", ""),
        "app": app["id"] if app else None, "app_title": app["title"] if app else "",
        "accent": app.get("accent") if app else None, "installed": bool(app and app.get("installed")),
        "state": state, "word": word, "caption": caption,
        "share": share, "plan": plan, "figure": figure,
        "measured": how_read(goal, today) if state == "new" else "",
        "who": who_measures(goal, app) if state == "new" else "",
        "in_hand": in_hand, "line": goalsfile.target_line(goal, today), "move": None,
        "step": step, "do": do, "counted_to": to.isoformat() if to else None,
        "unit": goal.get("unit", ""), "start": goal.get("start"), "target": goal.get("target"), "by": goal.get("by"),
        "rate": goal.get("rate"), "status": status,
        "value": value if common.number(value) else None,
        "lands": entry.get("lands") if measured else None, "reaches": reaches if measured else None,
        "points": list(entry.get("points") or []) if measured else [],
        "changes": list(entry.get("changes") or []) if measured else [],
        "counting": entry.get("counting", "") if measured else "",
        "why_pace": entry.get("why", "") if measured else "",
        "as_of": entry.get("as_of", "") if measured else "",
    }


def tally(readings: list) -> str:
    """"2 of 4 on pace, 2 new": the goals in hand that have a pace to tell, and of those the ones on it; then the
    ones not measured yet or just started. "" when there's none to count."""
    hand = [r for r in readings if r["in_hand"]]
    counted = [r for r in hand if r["state"] in COUNTED]
    if not counted:
        return ""
    on = sum(1 for r in counted if r["state"] in ("on", "ahead"))
    new = sum(1 for r in hand if r["state"] in NEW)
    return f"{on} of {len(counted)} on pace" + (f", {new} new" if new else "")


# ---- from the files -------------------------------------------------------------------------------------------

def apps_of(root) -> dict:
    """Each installed app the registry lists, by id: its title, its record, what it needs and whether a source is
    recorded for it. {} when there's no registry yet."""
    root = pathlib.Path(root)
    reg = common.load_json(root / "hydra" / "registry.json", None)
    sources = common.load_json(common.yours(root) / "sources.json", None)
    recorded = set()
    if isinstance(sources, dict):
        rows = sources.get("sources")
        if isinstance(rows, list):
            recorded = {r.get("app") for r in rows if isinstance(r, dict)}
        else:  # the connect kit's older shape, keyed by app
            recorded = {k for k, v in sources.items() if isinstance(v, list) and v}
    out = {}
    for a in (reg.get("apps") if isinstance(reg, dict) else None) or []:
        if not (isinstance(a, dict) and isinstance(a.get("id"), str)):
            continue
        home = a.get("home") if isinstance(a.get("home"), dict) else {}
        needs = home.get("needs")
        if isinstance(needs, str):
            needs = " ".join(needs.split()[1:])  # "your health export" from "Add your health export"
        else:
            needs = ""
        record = a.get("record")
        out[a["id"]] = {
            "id": a["id"], "title": a.get("title") if isinstance(a.get("title"), str) else a["id"].capitalize(),
            "installed": True, "needs": needs, "accent": a.get("accent"),
            "needs_line": " ".join(home["needs"].split()) if isinstance(home.get("needs"), str) else "",
            "source": bool(a.get("source")) or a["id"] in recorded, "uploads_only": uploads_only(a),
            "record": pathlib.Path(record) if isinstance(record, str) and record else root / a["id"],
        }
    return out


def uploads_only(entry: dict) -> bool:
    """Every source the app's column.json declares is an upload, as Wellbeing's Apple Health export is, so a
    goal it measures waits for a file to be in, not for something to be connected. The column.json is the one in the
    registry entry's root, and one that can't be read is another way in."""
    root = entry.get("root")
    column = common.load_json(pathlib.Path(root) / "column.json", None) if isinstance(root, str) and root else None
    sources = column.get("sources") if isinstance(column, dict) else None
    return isinstance(sources, list) and bool(sources) and all(
        isinstance(s, dict) and s.get("kind") == "upload" for s in sources)


def app_of(apps: dict, app_id: str, names=None) -> dict:
    """What a reading needs to know of an app, installed or not: one not installed is named by its catalog card or
    the kit's own names, else by its id, as the kit names it."""
    if app_id in apps:
        return dict(apps[app_id])
    title = (names or {}).get(app_id) or app_id[:1].upper() + app_id[1:]
    return {"id": app_id, "title": title, "installed": False,
            "needs": "", "source": False, "uploads_only": False, "record": None, "accent": None}


def read_goals(root, now=None, app=None) -> dict:
    """Every goal's reading, in the file's order, and the tally. app: only the goals that app measures, for the band
    on its own page. Raises goalsfile.Broken when the file isn't goals/v1."""
    now = now or common.now()
    today = now.date()
    doc, _ = goalsfile.load(root)
    apps = apps_of(root)
    settings = common.load_json(common.yours(root) / "settings.json", None)
    suggests = not (isinstance(settings, dict) and settings.get("suggestions") is False)
    said = {}  # each measuring app's say.json, read once

    def say_of(info):
        if info["id"] not in said:
            doc_ = common.load_json(info["record"] / "say.json", None) if info.get("record") else None
            said[info["id"]] = doc_ if isinstance(doc_, dict) else None
        return said[info["id"]]

    readings, names = [], None
    for goal in doc["goals"]:
        measured_by = goal.get("measured_by")
        if app is not None and (measured_by or {}).get("app") != app:
            continue
        info = entry = say = None
        stale = False
        if measured_by:
            if measured_by["app"] not in apps and names is None:
                names = pages.names(root)  # read once, and only for a page that isn't installed
            info = app_of(apps, measured_by["app"], names)
            say = say_of(info) if info["installed"] else None
            info["ran"] = say is not None
            info["measures"] = say is not None and isinstance(say.get("goals"), list)
            if info["measures"]:
                entry = next((e for e in say["goals"] if isinstance(e, dict) and e.get("id") == goal["id"]), None)
            after = common.parse_time(say.get("stale_after")) if say else None
            stale = after is not None and now > after
        r = read_goal(goal, entry, info, today, stale)
        if say and entry is not None and suggests and not stale and r["state"] not in ("aside", "done", "on", "ahead"):
            for s in say.get("suggestions") or []:
                if isinstance(s, dict) and s.get("goal") == goal["id"] and isinstance(s.get("text"), str):
                    r["move"] = {"text": s["text"], "why": s.get("why", "") if isinstance(s.get("why"), str) else ""}
                    break
        readings.append(r)
    return {"goals": readings, "tally": tally(readings)}
