"""Goals' save path: the only code that writes <root>/yours/goals.json. A page
reaches it through Home's server (POST /api/act/goals/<verb>), and Claude through `hydra goals <verb>`, which is
`hydra act goals <verb>`: the same declared action, with the same fields.

    python3 scripts/act.py <verb> --record <root>/goals --<field>=<value> ...                       the check
    python3 scripts/act.py <verb> --record <root>/goals --<field>=<value> ... --yes                 the save
    python3 scripts/act.py ids <list> --record <root>/goals                                         a field's ids
    python3 scripts/act.py answer --question=ci-<six> --words=<their words> --record <root>/goals --yesthe check-in
    python3 scripts/act.py arrived|left --app=<page> --record <root>/goals                          install and Remove

- A goal is saved only by the person's own act: their tap on a page, or their words to Claude, which are their
  choice. Either way a save writes at once and answers with Undo; there's no read-back to say yes to. HYDRA_BY=chat
  marks a save made from the chat. A `--token`, which callers of the old two steps still pass, is taken and ignored.
- A goal said with no date gets one, so its pace can be read: 12 weeks for a habit said as a rate, a year for any
  other target. Its saved line says so, and its date changes on the goal like any other.
- Goals asks one thing only: the day's check-in, "How's '{goal}' going?", answered through the answer path every
  page declares, `answer` and its Undo `unanswer` (scripts/checkin.py).
- The check writes nothing. The save writes goals.json whole or not at all, then one line in the record's own
  journal, store/changes.jsonl, so `undo` puts goals.json back byte for byte.
- The last line on stdout is one JSON object: {"ok": true, "said": ...}, with "undo": {"change": ...} from a
  save. A refusal is {"ok": false, "said": why} and exit 2, never a traceback.
- It starts no process and makes no request. Python 3.9, standard library only.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

import checkin
import common
import goalsfile
import pages
import reader
from goalsfile import Refused

JOURNAL = "store/changes.jsonl"
PROGRESS = "store/progress.jsonl"  # the numbers the person tells Claude for a goal kept by hand
KEPT = 20  # how many changes back Undo reaches
GONE = "That goal isn't in your goals any more, so nothing was changed."
UNCOUNTED = "No page counts that goal, so keep it by hand first (measure --app=goals), then save its number."
CHECK_SECONDS = 10  # a page's own goals script answers within this, or it's taken as a no
HABIT_WEEKS, A_YEAR = 12, 365  # how long a goal said with no date runs: a habit said as a rate, else any target
EVERY_NIGHT = {"n": 7, "per": "week"}  # a goal counted in nights, said with no count of nights, is every night

# Each verb's fields, in the order they're declared and sent: (name, kind, what the kind needs, required)
UNIT = ("unit", "words", goalsfile.UNIT_MAX, False)
START = (("from", "number", None, False), ("on", "date", (-3660, 366), False))  # where it began: set once, by add
MEASURE = (("target", "number", None, False), ("by", "date", (1, 7320), False),
           ("per", "choice", ("day", "week", "month"), False))
FIELDS = {
    "add": (("words", "words", goalsfile.TEXT_MAX, True), ("app", "id", "apps", False), UNIT) + START + MEASURE,
    "set": (("goal", "id", "goals", True), ("words", "words", 80, False), UNIT) + MEASURE,
    "reword": (("goal", "id", "goals", True), ("words", "words", goalsfile.TEXT_MAX, True)),
    "because": (("goal", "id", "goals", True), ("words", "words", goalsfile.WHY_MAX, True)),
    "measure": (("goal", "id", "goals", True), ("app", "id", "apps", True), ("unit", "choice", ("nights",), False)),
    "progress": (("goal", "id", "by-hand", True), ("value", "number", None, True), ("on", "date", (-3660, 0), False)),
    "aside": (("goal", "id", "in-hand", True),),
    "done": (("goal", "id", "in-hand", True),),
    "back": (("goal", "id", "ended", True),),
    "drop": (("goal", "id", "goals", True),),
    "undo": (("change", "id", "changes", True),),
    # the day's check-in, through column.md's answer path: a words question, so `pick` and `on` are always refused
    "answer": (("question", "id", "questions", True), ("pick", "id", "picks", False),
               ("on", "choice", ("yes", "no"), False), ("words", "words", checkin.MAX, False)),
    "unanswer": (("question", "id", "questions", True), ("pick", "id", "picks", False)),
}
CONFIRM = {"undo": "once"}  # every other verb saves at once, with Undo
LISTS = ("goals", "in-hand", "ended", "by-hand", "apps", "changes", "questions", "picks")
WRITES = {"progress": [PROGRESS, JOURNAL], "undo": [JOURNAL, PROGRESS]}  # every other verb writes only its
# journal line, beside goals.json


def declaration() -> list:
    """column.json's `actions`, from the table above, so the two can't drift (tests hold them equal)."""
    out = []
    for verb, fields in FIELDS.items():
        if verb in ("answer", "unanswer"):  # the answer path, as every page declares it
            out.append(next(json.loads(json.dumps(a)) for a in checkin.DECLARED if a["name"] == verb))
            continue
        act = {"name": verb, "script": ["scripts/act.py", verb], "confirm": CONFIRM.get(verb, "undo")}
        if act["confirm"] == "undo":
            act["undo"] = "undo"
        act["writes"] = list(WRITES.get(verb, [JOURNAL]))
        if verb != "progress":  # a number told for a goal kept by hand stays in Goals' own folder
            act["yours"] = [goalsfile.FILE]
        spec = {}
        for name, kind, needs, required in fields:
            f = {"kind": kind}
            if kind == "words":
                f["max"] = needs
            elif kind == "id":
                f["list"] = ["scripts/act.py", "ids", needs]
            elif kind == "choice":
                f["of"] = list(needs)
            elif kind == "date":
                f["from"], f["to"] = needs
            elif kind == "number":
                f["min"], f["max"] = -goalsfile.LIMIT, goalsfile.LIMIT
            if not required:
                f["optional"] = True
            spec[name] = f
        act["fields"] = spec
        out.append(act)
    return out


# ---- the record's own files -------------------------------------------------------------------------------------

@contextlib.contextmanager
def locked(record, wait: float = 20.0):
    """One writer at a time, by a lock on the record's own folder, so no file is made for it."""
    common.folder(record)
    fd = os.open(str(record), os.O_RDONLY)
    try:
        end = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > end:
                    raise Refused("Goals is busy saving something else. Try again in a moment.")
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def journal(record) -> list:
    return common.lines(record / JOURNAL)


def undoable(doc: dict, entries: list, told=None) -> list:
    """The changes Undo can still put back, newest first: not undone, and their goal as that save left it, or, for a
    number told, its line still in store/progress.jsonl (told: those lines, when the caller has read them)."""
    undone = {e.get("undoes") for e in entries if e.get("undoes")}
    out = []
    for e in reversed(entries):
        if "undoes" in e or e.get("id") in undone or not isinstance(e.get("id"), str):
            continue
        if e.get("verb") == "progress":
            if told is not None and e.get("told") in told:
                out.append(e)
        else:
            _, now_ = goalsfile.find(doc, e.get("goal"))
            if now_ == e.get("after"):
                out.append(e)
        if len(out) >= KEPT:
            break
    return out


def told_lines(record) -> list:
    """Every number told for a goal kept by hand, as store/progress.jsonl holds them, oldest first."""
    return common.lines(record / PROGRESS)


def ids(root, record, which: str, now=None) -> list:
    """What a field may take, as its `list` prints it. `now` is when it's asked, for today's check-in."""
    doc, _ = goalsfile.load(root)
    if which == "questions":  # today's check-in, open or answered, so its Undo can name it
        q = checkin.question(doc, record, now or common.now())
        return [q["id"]] if q else []
    if which == "picks":  # the check-in takes words, never a pick
        return []
    if which == "goals":
        return [g["id"] for g in doc["goals"]]
    if which == "in-hand":
        return [g["id"] for g in doc["goals"] if g["status"] == "active"]
    if which == "ended":
        return [g["id"] for g in doc["goals"] if g["status"] != "active"]
    if which == "by-hand":
        return [g["id"] for g in doc["goals"] if g["status"] == "active" and by_hand(g)]
    if which == "apps":  # the pages installed, then the pages on sale, then Goals itself and none
        seen = [p["id"] for p in pages.installed(root)]
        seen += [p["id"] for p in pages.on_sale(root) if p["id"] not in seen]
        return seen + [common.ID, "none"]  # Goals itself, for a goal kept by hand
    if which == "changes":
        return [e["id"] for e in undoable(doc, journal(record), told_lines(record))]
    raise Refused("That isn't something Goals can list.")


# ---- reading the fields --------------------------------------------------------------------------------------------

def parse(argv: list):
    """(verb, record, now, yes, fields as given). Each thing once, else Refused."""
    if not argv:
        raise Refused("Say what to do: add a goal, change one, or put one back.")
    verb, rest = argv[0], argv[1:]
    record = at = None
    yes, fields, i = False, {}, 0
    while i < len(rest):
        a = rest[i]
        i += 1
        if a == "--yes":
            if yes:
                raise Refused("That was said twice.")
            yes = True
            continue
        if not a.startswith("--") or len(a) < 3:
            raise Refused("That isn't a way Goals is asked.")
        key, eq, val = a[2:].partition("=")
        if not eq:
            if key != "record" or i >= len(rest):
                raise Refused("That isn't a way Goals is asked.")
            val = rest[i]
            i += 1
        if key == "record":
            if record is not None:
                raise Refused("That was said twice.")
            record = val
        elif key == "now":
            at = val
        elif key == "token":
            continue  # a token from a caller of the old two steps is taken and ignored: a save goes at once
        else:
            if key in fields:
                raise Refused("That was said twice.")
            fields[key] = val
    return verb, record, at, yes, fields


def checked(verb: str, given: dict, root, record, today, now=None) -> dict:
    """The verb's fields, each checked again here as if no server had: {name: value}, numbers and days as such."""
    spec = FIELDS[verb]
    names = [f[0] for f in spec]
    extra = [k for k in given if k not in names]
    if extra:
        raise Refused("That holds something Goals doesn't take.")
    out = {}
    for name, kind, needs, required in spec:
        if name not in given:
            if required:
                raise Refused("Something Goals needs for that is missing.")
            continue
        raw = given[name]
        if kind == "words":
            out[name] = goalsfile.typed(raw, needs)
        elif kind == "choice":
            if raw not in needs:
                raise Refused("That isn't one of the choices.")
            out[name] = raw
        elif kind == "date":
            d = common.day(raw)
            if d is None or not needs[0] <= (d - today).days <= needs[1]:
                raise Refused("That day isn't one Goals can take.")
            out[name] = d
        elif kind == "number":
            out[name] = number(raw)
        elif kind == "id":
            listed = ids(root, record, needs, now)
            if raw not in listed and needs == "by-hand" and raw in ids(root, record, "in-hand"):
                _, g = goalsfile.find(goalsfile.load(root)[0], raw)  # a number for a goal no page counts, or a page's
                raise Refused(UNCOUNTED if g and g.get("measured_by") is None else
                              "A page counts that goal, so its number comes from that page.")
            if raw not in listed:
                raise Refused(GONE if needs in ("goals", "in-hand", "ended") else "That isn't on Goals' page any more, "
                              "so nothing was changed.")
            out[name] = raw
    return out


def number(raw: str):
    """A plain decimal in range: no nan, no infinity, no grouping, no other base."""
    s = raw.strip() if isinstance(raw, str) else ""
    body = s[1:] if s[:1] in "+-" else s
    if not body or body.count(".") > 1 or not body.replace(".", "").isdigit() or s != raw:
        raise Refused("That number isn't one Goals can take.")
    n = float(s)
    if not goalsfile.bounded(n):
        raise Refused("That number isn't one Goals can take.")
    return int(n) if n == int(n) else n


# ---- what each verb would save -----------------------------------------------------------------------------------

def short(text: str, most: int = 80) -> str:
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


def distance_by_hand(root, goal: dict) -> dict:
    """A distance is kept by hand by a page that doesn't count distances: Wellbeing counts
    sessions, so a goal of km or miles named for it is Goals' own to measure, from the numbers the person tells
    Claude. A page whose `fits` names the unit counts it."""
    app = (goal.get("measured_by") or {}).get("app")
    if goal.get("unit") in reader.DISTANCES and app not in (None, common.ID):
        page = next((p for p in pages.installed(root) if p["id"] == app), None)
        if page is None or not pages.unit_fits(page["fits"], goal["unit"]):
            return dict(goal, measured_by={"app": common.ID})
    return goal


def page_says(root, page: dict, goal: dict) -> dict:
    """A page's own answer to whether it counts a goal, and as what: {"counts": True, "as", "unit", "kind",
    "counting"}, or {"counts": False, "why"}. It's the page's `fits.script --check`, run from its root. Anything else
    is a no, so nothing claims a count it didn't give."""
    no = {"counts": False, "why": f"{page['title']} couldn't say whether it counts this."}
    script = pathlib.Path(page["root"]) / page["fits"]["script"] if page["root"] and page["fits"]["script"] else None
    if script is None or not script.is_file():
        return no
    ask = json.dumps({"text": goal["text"], "unit": goal.get("unit", "")}, ensure_ascii=False)
    try:
        done = subprocess.run([sys.executable, "-B", str(script), "--check", ask], capture_output=True, text=True,
                              timeout=CHECK_SECONDS)
        said = json.loads(done.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return no
    if not isinstance(said, dict) or said.get("counts") not in (True, False):
        return no
    if said["counts"] and not (isinstance(said.get("unit"), str) and said["unit"].strip()
                               and isinstance(said.get("counting"), str)):
        return no
    return said


COUNT_VERBS = ("add", "set", "measure", "back")  # the saves that can leave a goal a page counts ready to read


def count_now(root, gid) -> bool:
    """A goal set while its page's data is already in is counted at once: when the save leaves it active, a page's,
    with a target and a date, and that page has read before (its say.json's `data_to`, the last day it read), the
    page reads once more, with its own `fits.script --count`, before Goals' own rebuild. Anything else, no script, a
    slow one or a no, changes nothing: the goal waits for the page's next run."""
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        return False
    g = next((g for g in doc["goals"] if g["id"] == gid), None)
    app = (g.get("measured_by") or {}).get("app") if g else None
    if not (g and g.get("status") == "active" and app not in (None, common.ID) and goalsfile.read(g)):
        return False
    return count_page(root, app)


def count_page(root, app: str) -> bool:
    """The page's `fits.script --count`, once, when it has read before. True when it said it counted."""
    page = next((p for p in pages.installed(root) if p["id"] == app), None)
    if page is None or not (page["root"] and page["fits"]["script"]):
        return False
    import reading
    info = reading.apps_of(root).get(app) or {}
    say = common.load_json(info["record"] / "say.json", None) if info.get("record") else None
    if not (isinstance(say, dict) and common.day(say.get("data_to") or "")):
        return False  # nothing read yet (its say.json's `data_to`, the last day it read): its first read counts it
    script = pathlib.Path(page["root"]) / page["fits"]["script"]
    if not script.is_file():
        return False
    try:
        done = subprocess.run([sys.executable, "-B", str(script), "--count", "--record", str(info["record"])],
                              capture_output=True, text=True, timeout=CHECK_SECONDS,
                              env=dict(os.environ, HYDRA_ROOT=str(root)))
        said = json.loads(done.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return False
    return isinstance(said, dict) and said.get("ok") is True


def counted(root, goal: dict, named, f: dict) -> tuple:
    """Who counts a new goal, and the goal as it's saved for them: (goal,
    the read-back's words for who counts it). Kept by hand, or with no app, when the person chose that with Claude. A
    page named with the person counts it once it's installed, with its own check's yes when it has one. Any other
    goal goes to the installed pages by their `fits`, in the registry's order: first those whose `units` hold the
    goal's unit, then those whose own check says yes; the first that counts it takes it, in the unit it gives. With
    none, it's kept by hand, with a page's reason when it's about this goal. A sleep goal said in hours is counted in
    nights, so a count read from those hours goes, and it's every night until they say otherwise."""
    if named == "none":
        return dict(goal, measured_by=None), ""
    if named == common.ID:
        return dict(goal, measured_by={"app": common.ID}), ""
    here = pages.installed(root)
    if named:
        page = next((p for p in here if p["id"] == named), None)
        if page is None:  # named with the person, not installed: kept by hand until it's here
            return dict(goal, measured_by={"app": common.ID}), ""
        ask = [page]
    else:  # a unit some page names is that page's alone; any other unit, any page's own check may take
        unit = goal.get("unit")
        ask = [p for p in here if pages.unit_fits(p["fits"], unit)]
        if not pages.claimed(root, unit):
            ask += [p for p in here if p["fits"]["script"] and p not in ask]
    why = ""
    for page in ask:
        if not page["fits"]["script"]:  # its units alone say it counts it
            return dict(goal, measured_by={"app": page["id"]}), f"{page['title']} counts it."
        said = page_says(root, page, goal)
        if said["counts"]:
            g = dict(goal, measured_by={"app": page["id"]}, unit=said["unit"].strip())
            if said.get("as") == "nights" and goal.get("unit") not in (None, "", "nights") and not (
                    {"target", "per"} & set(f)):
                g = in_nights(g)
            counting = said["counting"].strip().rstrip(".")
            return g, f"{page['title']} counts it: {counting[:1].lower() + counting[1:]}."
        # its reason is said when it's about this goal, not a page's word for anything else
        plain = said.get("why", "") in (f"{page['title']} can't tell how to count this yet.",
                                        f"{page['title']} couldn't say whether it counts this.")
        if not why and (named or not plain):
            why = said.get("why", "")
    return dict(goal, measured_by={"app": common.ID}), why


def who_counts(root, goal: dict, who: str) -> str:
    """The read-back's words for who counts a new goal: the page's own, with what it still waits for; or why a page
    doesn't, then that it's kept by hand; or who counts it, as for any goal."""
    if (goal.get("measured_by") or {}).get("app") not in (None, common.ID) and who:
        waits = who_short(root, goal)  # "Wellbeing counts it once your health export is in."
        return f"{who} {waits}" if waits.endswith((" in.", " connected.")) else who
    return " ".join(w for w in (who, who_short(root, goal)) if w)


def by_hand(goal: dict) -> bool:
    """A goal no page counts, kept by hand: Goals counts it from the numbers the person tells Claude."""
    return (goal.get("measured_by") or {}).get("app") == common.ID


def who_short(root, goal: dict) -> str:
    """Who counts it, in the read-back: the page, and what it still needs, or that it's kept by hand."""
    m = goal.get("measured_by")
    if not m:  # one state, one phrase: the pages' own words for it, kept exactly
        return NOT_COUNTED
    if by_hand(goal):  # and, once a page on sale counts its unit, that page's one line
        sale = next((p for p in pages.on_sale(root) if pages.unit_fits(p["fits"], goal.get("unit"))), None)
        kept = "You keep it by hand: tell Claude where it stands."
        return f"{kept} The {sale['title']} page can count this for you." if sale else kept
    import reading
    app = reading.app_of(reading.apps_of(root), m["app"], pages.names(root))
    if not app["installed"]:
        return f"Add {app['title']} to count this."
    if not app.get("source") and app.get("needs"):  # "Wellbeing counts it once your health export is in."
        return reading.who_measures(goal, app)
    return f"{app['title']} counts it."


def how(goal: dict, today) -> str:
    """How a goal is read, in the read-back: as the pages say it, and, before it has a target and a date, what it
    still needs: "Not counted yet, no target yet, no date yet"."""
    import reading
    got = reading.how_read(goal, today)
    return ", ".join([got] + goalsfile.missing(goal)) if got == "Not counted yet" else got


def measured(goal: dict, f: dict, read: dict, today) -> dict:
    """The goal with how it's measured set from the fields given and, where they're silent, from what a typed line
    reads as: its unit, its start, its target and its date, with a rate stored as the count its path needs."""
    g = dict(goal)
    start = dict(g.get("start") or {"value": 0, "on": today.isoformat()})
    if "from" in f:
        start["value"] = f["from"]
    if "on" in f:
        start["on"] = f["on"].isoformat()
    by = f.get("by") or read.get("by") or common.day(g.get("by") or "")
    rate, target = g.get("rate"), g.get("target")
    if "per" in f:  # a rate: so many for each day, week or month, and once for each when no count is given
        n = f.get("target", 1)
        if n <= 0:
            raise Refused(f"Say how many for each {f['per']}, as a number above zero.")
        rate, target = {"n": n, "per": f["per"]}, None
    elif "target" in f:
        rate, target = None, f["target"]
    elif "rate" in read:
        rate, target = dict(read["rate"]), None
    elif "target" in read:
        rate, target = None, read["target"]
    unit = f.get("unit") or read.get("unit") or g.get("unit")
    unit = reader.distance_unit(unit) if unit else unit  # "kilometers" is km, "mile" is miles
    on = common.day(start["on"])
    if by is not None and by <= on:
        raise Refused("Its date has to come after the day it starts.")
    if rate is not None and by is not None:
        target = goalsfile.rate_target(start["value"], on, by, rate)
    elif rate is not None:
        target = None  # counted once it has its date
    if target is not None and target == start["value"]:
        raise Refused("Its target is where it starts. Say where it's heading.")
    g["start"] = start
    for key, val in (("unit", unit), ("target", target), ("by", by.isoformat() if by else None), ("rate", rate)):
        if val is None:
            g.pop(key, None)
        else:
            g[key] = val
    return g


def in_nights(goal: dict) -> dict:
    """A goal counted in nights: every night, so its count comes from its date, and a count read in another unit goes."""
    g = dict(goal, unit="nights", rate=dict(EVERY_NIGHT))
    g.pop("target", None)
    return g


def dated(goal: dict, today) -> tuple:
    """(the goal with a date, and how long it runs in words) for a goal with a number and no date: a habit said as a
    rate runs HABIT_WEEKS weeks, any other target a year; a rate's count then follows from its date. As it was, and "",
    for a goal that has its date or no number at all."""
    g = dict(goal)
    if not g.get("by") and (g.get("rate") or g.get("target") is not None):
        weeks = bool(g.get("rate"))
        g["by"] = (today + (dt.timedelta(weeks=HABIT_WEEKS) if weeks else dt.timedelta(days=A_YEAR))).isoformat()
        span = f"{HABIT_WEEKS} weeks" if weeks else "a year"
    else:
        span = ""
    if g.get("rate") and g.get("by") and g.get("target") is None:
        g["target"] = goalsfile.rate_target(g["start"]["value"], common.day(g["start"]["on"]), common.day(g["by"]),
                                            g["rate"])
    return g, span


def plan(verb: str, f: dict, doc: dict, root, record, now, by: str) -> dict:
    """What the save would do: {"goal": id, "before", "after", "index", "check": said, "saved": said, "extra"}.
    before or after is None for a goal that isn't there. Nothing is written here."""
    today, stamp = now.date(), common.iso(now)
    if verb == "add":
        text = f["words"]
        goalsfile.locked(text)
        if goalsfile.in_hand(doc) >= goalsfile.MAX_HAND:
            raise Refused("That's 12 goals in hand. Set one aside first.")
        if len(doc["goals"]) >= goalsfile.MAX_ALL:
            raise Refused("That's 60 goals kept. Take an old one out first.")
        read = reader.read(text, today)
        g = {"id": goalsfile.new_id(text, stamp, {x["id"] for x in doc["goals"]}), "text": text, "measured_by": None}
        g, who = counted(root, measured(g, f, read, today), f.get("app"), f)
        g, span = dated(distance_by_hand(root, g), today)
        g.update(status="active", set={"at": stamp, "from": "chat" if by == "chat" else "page"})
        g = goalsfile.ordered(g)
        line = goalsfile.target_line(g, today)
        note = f" It runs {span}: change its date on the goal any time." if span else ""
        counts = who_counts(root, g, who)
        check = f"{short(text)}: {line or how(g, today).lower()}. {counts}{note}"
        return {"goal": g["id"], "before": None, "after": g, "index": len(doc["goals"]), "check": check,
                "saved": f"Saved. {how(g, today)}. {counts}{note}"}
    if verb == "undo":
        e = next((e for e in undoable(doc, journal(record), told_lines(record)) if e["id"] == f["change"]), None)
        if e is None:
            raise Refused("That can't be put back any more, because it changed again since.")
        if e.get("verb") == "progress":  # a number told: its line comes back out of store/progress.jsonl
            _, g = goalsfile.find(doc, e["goal"])
            return {"goal": e["goal"], "told_back": e["told"], "undoes": e["id"], "saved": "Put back.",
                    "check": f"{short((g or {}).get('text', 'That goal'))}: that number taken back."}
        text = (e.get("before") or e.get("after") or {}).get("text", "")
        return {"goal": e["goal"], "before": e.get("after"), "after": e.get("before"), "index": e.get("index", 0),
                "check": f"{short(text)}: put back as it was.", "saved": "Put back.", "undoes": e["id"],
                "began": bool(e.get("began"))}
    index, old = goalsfile.find(doc, f["goal"])
    if old is None:
        raise Refused(GONE)
    g, name = dict(old), short(old["text"])
    if verb == "set":
        read = reader.read(f["words"], today) if "words" in f else {}
        if "words" in f and not any(k in read for k in ("by", "target", "rate")):
            raise Refused("That line has no number or date to read. Try '12 swims by Sep 1'.")
        g = distance_by_hand(root, measured(g, f, read, today))
        line = goalsfile.target_line(g, today)
        check = f"{name}: {line or how(g, today).lower()}."
        saved = f"Saved for tonight's run. Now {line}." if line else f"Saved. {how(g, today)}."
    elif verb == "reword":
        goalsfile.locked(f["words"])
        g["text"] = f["words"]
        check, saved = f"{name} becomes: {short(f['words'])}.", "Saved. Its words are changed."
    elif verb == "because":
        goalsfile.locked(f["words"])
        g["why"] = f["words"]
        check, saved = f"{name}, because: {short(f['words'])}", "Saved why it matters."
    elif verb == "measure":
        page = next((p for p in pages.installed(root) if p["id"] == f["app"]), None)
        if (old.get("measured_by") or {}).get("app") == f["app"] and page is not None:
            # it counts it already, so nothing changes; but Count it in nights, from that page's own entry, turns an
            # older goal it counts in nights, kept in another unit, into nights at once
            if f.get("unit") == "nights" and old.get("unit") != "nights" and page["fits"]["script"]:
                said = page_says(root, page, old)
                if said["counts"] and said.get("as") == "nights":
                    g, _ = dated(in_nights(g), today)
        elif page is not None and page["fits"]["script"]:  # the page says whether it counts it, and in what
            said = page_says(root, page, old)
            if not said["counts"]:
                raise Refused(" ".join(w for w in (said.get("why"), "It stays as it is.") if w))
            if said.get("as") == "nights" and old.get("unit") not in (None, "", "nights"):
                if f.get("unit") != "nights":
                    e = Refused(f"{page['title']} counts this in nights.")
                    e.then = {"words": "Count it in nights", "act": "measure",
                              "fields": {"goal": old["id"], "app": f["app"], "unit": "nights"}}
                    raise e
                g, _ = dated(in_nights(dict(g, measured_by={"app": f["app"]})), today)
            else:
                g = dict(g, measured_by={"app": f["app"]}, unit=said["unit"].strip())
        else:
            g = distance_by_hand(root, dict(g, measured_by=None if f["app"] == "none" else {"app": f["app"]}))
        line = goalsfile.target_line(g, today) if g.get("unit") != old.get("unit") else ""  # in nights now
        check = f"{name}: {line + '. ' if line else ''}{who_short(root, g)}"
        saved = f"Saved. {'Counted as ' + line + '. ' if line else ''}{who_short(root, g)}"
    elif verb in ("aside", "done"):
        if old["status"] != "active":
            raise Refused("That goal is already out of your goals in hand.")
        g.update(status=verb, ended=today.isoformat())
        check = f"{name}: {'set aside' if verb == 'aside' else 'marked done'}, from today."
        saved = "Set aside. It stays in your list of past goals." if verb == "aside" else "Marked done."
    elif verb == "back":
        if old["status"] == "active":
            raise Refused("That goal is already among your goals in hand.")
        if goalsfile.in_hand(doc) >= goalsfile.MAX_HAND:
            raise Refused("That's 12 goals in hand. Set one aside first.")
        g["status"] = "active"
        g.pop("ended", None)
        check, saved = f"{name}: back among your goals in hand.", "It's back among your goals."
    elif verb == "drop":
        return {"goal": old["id"], "before": old, "after": None, "index": index,
                "check": f"{name}: taken out of your goals for good.", "saved": "Taken out of your goals."}
    elif verb == "progress":  # where a goal kept by hand stands, as they told Claude: Goals' own line, never goals.json
        if not by_hand(old) or old["status"] != "active":
            raise Refused("A page counts that goal, so its number comes from that page.")
        on = f.get("on") or today
        began = common.day((old.get("start") or {}).get("on") or "")
        if began is not None and on < began:
            raise Refused(f"That's before this goal began, on {common.one_day(began, today)}.")
        figure = common.with_unit(f["value"], old.get("unit"))
        when = "today" if on == today else common.one_day(on, today)
        told = {"goal": old["id"], "value": f["value"], "on": on.isoformat(), "at": stamp, "by": by}
        return {"goal": old["id"], "told": told, "check": f"{name}: {figure}, as of {when}.",
                "saved": f"Saved: {figure}, as of {when}."}
    else:
        raise Refused("That isn't something Goals does.")
    if g != old:
        g["changed"] = stamp
    else:
        check, saved = f"{name}: nothing changes.", "Nothing to change."
    return {"goal": old["id"], "before": old, "after": goalsfile.ordered(g), "index": index, "check": check,
            "saved": saved}


def applied(doc: dict, p: dict) -> dict:
    """The document as the plan leaves it."""
    goals = list(doc["goals"])
    i, _ = goalsfile.find(doc, p["goal"])
    if p["after"] is None:
        if i is not None:
            goals.pop(i)
    elif i is None:
        goals.insert(min(p.get("index", len(goals)), len(goals)), p["after"])
    else:
        goals[i] = p["after"]
    return {"contract": goalsfile.CONTRACT, "goals": goals}


def change_id(stamp: str, verb: str, goal: str, n: int) -> str:
    return "c-" + hashlib.sha1(f"{stamp}\n{verb}\n{goal}\n{n}".encode("utf-8")).hexdigest()[:10]


def keep(root, record, doc: dict, raw, p: dict, verb: str, stamp: str) -> str:
    """Writes the plan: goals.json whole or not at all, or a told number's line, then its line in the journal. The
    change's id."""
    if "told" in p:  # a number told for a goal kept by hand: one line in Goals' own folder
        common.append_line(record / PROGRESS, p["told"])
    elif "told_back" in p:  # its Undo: that line back out, the file byte for byte as before it
        take_out(record / PROGRESS, lambda obj: obj == p["told_back"])
    else:
        new = applied(doc, p)
        if p.get("began") and not new["goals"]:  # this save began the file, and it's being undone: the file goes again
            goalsfile.path(root).unlink()
        elif new != doc or raw is None:
            goalsfile.write(root, new)
    cid = change_id(stamp, verb, p["goal"], len(journal(record)))
    line = {"id": cid, "at": stamp, "verb": verb, "goal": p["goal"]}
    if "undoes" in p:
        line["undoes"] = p["undoes"]
    elif "told" in p:
        line["told"] = p["told"]
    else:
        line.update(before=p["before"], after=p["after"], index=p["index"], began=raw is None)
    common.append_line(record / JOURNAL, line)
    return cid


def take_out(path, match) -> None:
    """Takes the last line `match` holds for back out of a .jsonl, so the file is byte for byte as it was before that
    line was added. The file goes when that line was all it held."""
    try:
        kept = path.read_text(encoding="utf-8").splitlines(True)
    except FileNotFoundError:
        return
    at = None
    for i, raw in enumerate(kept):
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict) and match(obj):
            at = i
    if at is None:
        return
    rest = kept[:at] + kept[at + 1:]
    if rest:
        common.write_whole(path, "".join(rest))
    else:
        path.unlink()


NOT_COUNTED = "Not counted yet."  # a goal no page counts, as every page says it


def arrived(root, record, now, app: str) -> dict:
    """A page that just arrived (Hydra-OS's install calls this): each goal in hand that no page counted, set before it
    and fitting it (its `units`, else its own check), moves to it at once, each a change with its Undo, and Goals asks
    nothing. Then the page counts every goal it measures, by its own `--count`. The arrival and the goals it took go
    in Goals' own store/arrived.json, which its page says for two weeks, then say.json, home.json and the page are
    written again. {"ok", "counted", "moved"}."""
    page = next((p for p in pages.installed(root) if p["id"] == app), None)
    if page is None:
        raise Refused("That page isn't installed, so there's nothing to count.")
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        raise Refused(goalsfile.BROKEN_LINE)
    import build
    fit = []
    for g in doc["goals"]:
        if g.get("status") != "active" or (g.get("measured_by") or {}).get("app") not in (None, common.ID):
            continue
        at = common.parse_time((g.get("set") or {}).get("at") or "")
        if at is None or at >= now:
            continue  # set while the page was here: who counts it was settled then
        # its units, else, for a unit no page names, its own check, which has the final word
        mine = pages.unit_fits(page["fits"], g.get("unit"))
        if not (mine or (page["fits"]["script"] and not pages.claimed(root, g.get("unit")))):
            continue
        if page_says(root, page, g)["counts"] if page["fits"]["script"] else mine:
            fit.append(g["id"])
    moved = []
    for gid in fit:
        doc, raw = goalsfile.load(root)
        try:
            p = plan("measure", {"goal": gid, "app": app}, doc, root, record, now, "page")
        except Refused:
            continue  # its page says no after all, so it stays kept by hand
        if p["after"] != p["before"]:
            with locked(record):
                keep(root, record, doc, raw, p, "measure", common.iso(now))
            moved.append(gid)
    doc, _ = goalsfile.load(root)
    mine = [g for g in doc["goals"] if g.get("status") == "active" and (g.get("measured_by") or {}).get("app") == app
            and goalsfile.read(g)]
    counted_now = len(mine) if mine and count_page(root, app) else 0
    with locked(record):
        path = record.joinpath(*build.ARRIVED)
        got = common.load_json(path, None)
        apps = dict(got["apps"]) if isinstance(got, dict) and isinstance(got.get("apps"), dict) else {}
        apps[app] = {"at": common.iso(now), "goals": moved}
        common.write_json(path, {"contract": "goal-arrivals/v1", "apps": apps})
    rebuild(root, record, now)
    return {"ok": True, "counted": counted_now, "moved": len(moved)}


def left(root, record, now, app: str) -> dict:
    """A page that was just removed (Hydra-OS's Remove calls this once the page is out): each goal in hand it
    counted is kept by hand at once, each a change with its Undo, and Goals asks nothing. The person tells Claude
    where it stands from then on, and if the page comes back, `arrived` moves it back. The removal, the goals it gave
    back and the page's name go in Goals' own store/left.json, which its page says for two weeks, then say.json,
    home.json and the page are written again. {"ok", "moved"}."""
    if app in pages.NOT_PAGES:
        raise Refused("Goals and Hydra-OS itself count no goal, so there's nothing to move.")
    if any(p["id"] == app for p in pages.installed(root)):
        raise Refused("That page is still installed, so it still counts its goals.")
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        raise Refused(goalsfile.BROKEN_LINE)
    import build
    gave = [g["id"] for g in doc["goals"] if g.get("status") == "active"
            and (g.get("measured_by") or {}).get("app") == app]
    moved = []
    for gid in gave:
        doc, raw = goalsfile.load(root)
        try:
            p = plan("measure", {"goal": gid, "app": common.ID}, doc, root, record, now, "page")
        except Refused:
            continue  # gone since the first read, so there's nothing to keep
        if p["after"] != p["before"]:
            with locked(record):
                keep(root, record, doc, raw, p, "measure", common.iso(now))
            moved.append(gid)
    with locked(record):
        path = record.joinpath(*build.LEFT)
        got = common.load_json(path, None)
        apps = dict(got["apps"]) if isinstance(got, dict) and isinstance(got.get("apps"), dict) else {}
        if moved or app in apps:  # a page that gave back nothing leaves no line, and clears an older one
            apps[app] = {"at": common.iso(now), "goals": moved,
                         "title": pages.names(root).get(app) or app.capitalize()}
            common.write_json(path, {"contract": "goal-leavings/v1", "apps": apps})
    rebuild(root, record, now)
    return {"ok": True, "moved": len(moved)}


# ---- one call ------------------------------------------------------------------------------------------------------

def rebuild(root, record, now) -> None:
    """After a save: Goals' own say.json and home.json again, and its page once it has one. A save stands whether or
    not this works, since Home's server builds the page again on request."""
    try:
        import build
        build.after_save(root, record, now)
    except Exception:  # noqa: BLE001  (the goal is saved; the next look or run rebuilds)
        pass


def run(argv: list) -> dict:
    verb, record, at, yes, given = parse(argv)
    if verb == "ids":
        raise Refused("Say which list.")
    if verb in ("arrived", "left"):  # not a page's action: Hydra-OS's install and Remove, as a page comes and goes
        app = given.get("app") if set(given) == {"app"} else ""
        if not (app and app == app.lower() and app.replace("-", "").isalnum() and app[0].isalpha() and len(app) <= 32):
            raise Refused("Say which page arrived: --app=<its id>." if verb == "arrived" else
                          "Say which page was removed: --app=<its id>.")
        root = common.root_of(record)
        return (arrived if verb == "arrived" else left)(root, common.record_of(root, record), common.now(at), app)
    if verb not in FIELDS:
        raise Refused("That isn't something Goals does.")
    if verb in ("answer", "unanswer"):  # the day's check-in
        root = common.root_of(record)
        record, now = common.record_of(root, record), common.now(at)
        try:
            f = checked(verb, given, root, record, now.date(), now)
        except goalsfile.Broken:
            raise Refused(goalsfile.BROKEN_LINE)
        with locked(record):
            if verb == "answer":
                return checkin.answer(root, record, now, f, yes, rebuild)
            return checkin.unanswer(root, record, now, f, yes, rebuild, take_out)
    root = common.root_of(record)
    record = common.record_of(root, record)
    now = common.now(at)
    by = "chat" if os.environ.get("HYDRA_BY") == "chat" else "page"
    try:
        doc, raw = goalsfile.load(root)
    except goalsfile.Broken:
        raise Refused(goalsfile.BROKEN_LINE)
    f = checked(verb, given, root, record, now.date())
    p = plan(verb, f, doc, root, record, now, by)
    if not yes:
        return {"ok": True, "said": p["check"]}
    with locked(record):
        cid = keep(root, record, doc, raw, p, verb, common.iso(now))
    if verb in COUNT_VERBS and isinstance(p.get("goal"), str):
        count_now(root, p["goal"])
    rebuild(root, record, now)
    out = {"ok": True, "said": p["saved"]}
    if verb != "undo":
        out["undo"] = {"change": cid}
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] in (["ids"], ["questions"], ["picks"]):  # a field's ids; the answer path's own two lists
            if argv[0] == "ids":
                which = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else ""
                rest = argv[2:] if which else argv[1:]
            else:
                which, rest = argv[0], argv[1:]
            _, record, at, _, given = parse(["ids"] + rest)
            if which not in LISTS or (given and not (which == "picks" and set(given) == {"question"})):
                raise Refused("That isn't something Goals can list.")
            root = common.root_of(record)
            try:
                print(json.dumps(ids(root, common.record_of(root, record), which, common.now(at))))
            except goalsfile.Broken:
                print("[]")
            return 0
        print(json.dumps(run(argv), ensure_ascii=False))
        return 0
    except Refused as e:
        out = {"ok": False, "said": str(e)}
        if isinstance(getattr(e, "then", None), dict):  # the one button that does what it says, for the page to draw
            out["then"] = e.then
        print(json.dumps(out, ensure_ascii=False))
        return 2
    except common.NotSetUp as e:
        print(json.dumps({"ok": False, "said": str(e)}, ensure_ascii=False))
        return 2
    except Exception:  # noqa: BLE001  (never a traceback: the page shows this line)
        print(json.dumps({"ok": False, "said": "Goals couldn't save that just now. Nothing was changed."}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
