"""Goals' save path: the only code that writes <root>/yours/goals.json. A page
reaches it through Home's server (POST /api/act/goals/<verb>), and Claude through `hydra goals <verb>`, which is
`hydra act goals <verb>`: the same declared action, with the same fields.

    python3 scripts/act.py <verb> --record <root>/goals --<field>=<value> ...                       the check
    python3 scripts/act.py <verb> --record <root>/goals --<field>=<value> ... --yes [--token=<t>]   the save
    python3 scripts/act.py ids <list> --record <root>/goals [--question=<id>]                       a field's ids

- A goal is saved only by the person's own act. From a page (HYDRA_BY is page, or unset) a save writes at once and
  answers with Undo. From Claude's panel (HYDRA_BY=chat) every save is two steps: the check prints the goal as it
  would be saved, with a token, and the save needs that token back, after the person's yes. A token from another
  reading, or from before the file last changed, is refused.
- The check writes nothing. The save writes goals.json whole or not at all, then one line in the record's own
  journal, store/changes.jsonl, so `undo` puts goals.json back byte for byte.
- The last line on stdout is one JSON object: {"ok": true, "said": ...}, with "token" from a chat check and
  "undo": {"change": ...} from a save. A refusal is {"ok": false, "said": why} and exit 2, never a traceback.
- It starts no process and makes no request. Python 3.9, standard library only.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

import common
import goalsfile
import pages
import reader
from goalsfile import Refused

JOURNAL = "store/changes.jsonl"
PROGRESS = "store/progress.jsonl"  # the numbers the person tells Claude for a goal kept by hand
ANSWERS = "answers.jsonl"
KEPT = 20  # how many changes back Undo reaches
GONE = "That goal isn't in your goals any more, so nothing was changed."
NOT_READ_BACK = "That wasn't read back first, or something changed since. Read it back again, then save it."
WORDS_ONLY = "That question takes your answer in a few words of your own."
CHECK_SECONDS = 10  # a page's own goals script answers within this, or it's taken as a no

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
    "measure": (("goal", "id", "goals", True), ("app", "id", "apps", True)),
    "progress": (("goal", "id", "by-hand", True), ("value", "number", None, True), ("on", "date", (-3660, 0), False)),
    "aside": (("goal", "id", "in-hand", True),),
    "done": (("goal", "id", "in-hand", True),),
    "back": (("goal", "id", "ended", True),),
    "drop": (("goal", "id", "goals", True),),
    "undo": (("change", "id", "changes", True),),
    "answer": (("question", "id", "questions", True), ("pick", "id", "picks", False),
               ("on", "choice", ("yes", "no"), False), ("words", "words", 120, False)),
    "unanswer": (("question", "id", "questions", True), ("pick", "id", "picks", False)),
}
CONFIRM = {"undo": "once", "unanswer": "once"}  # every other verb saves at once on a page, with Undo
UNDO = {"answer": "unanswer"}  # every other verb's Undo is `undo`, with the change the save names
LISTS = ("goals", "in-hand", "ended", "by-hand", "apps", "changes", "questions", "picks")
WRITES = {"answer": [ANSWERS, JOURNAL], "unanswer": [ANSWERS, JOURNAL], "progress": [PROGRESS, JOURNAL],
          "undo": [JOURNAL, PROGRESS]}  # every other verb writes only its journal line, beside goals.json


def declaration() -> list:
    """column.json's `actions`, from the table above, so the two can't drift (tests hold them equal)."""
    out = []
    for verb, fields in FIELDS.items():
        act = {"name": verb, "script": ["scripts/act.py", verb], "confirm": CONFIRM.get(verb, "undo")}
        if act["confirm"] == "undo":
            act["undo"] = UNDO.get(verb, "undo")
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
                if needs == "picks":
                    f["of"] = "question"
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


def questions(record) -> list:
    """The questions Goals' last run asked, as its say.json holds them."""
    say = common.load_json(record / "say.json", None)
    qs = say.get("questions") if isinstance(say, dict) else None
    return [q for q in qs or [] if isinstance(q, dict) and isinstance(q.get("id"), str)]


def ids(root, record, which: str, question: str = "") -> list:
    """What a field may take, as its `list` prints it."""
    doc, _ = goalsfile.load(root)
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
    if which == "questions":
        return [q["id"] for q in questions(record)]
    if which == "picks":
        q = next((q for q in questions(record) if q["id"] == question), None)
        return [p["id"] for p in (q or {}).get("picks") or [] if isinstance(p, dict) and isinstance(p.get("id"), str)]
    raise Refused("That isn't something Goals can list.")


# ---- reading the fields --------------------------------------------------------------------------------------------

def parse(argv: list):
    """(verb, record, now, yes, token, fields as given). Each thing once, else Refused."""
    if not argv:
        raise Refused("Say what to do: add a goal, change one, or put one back.")
    verb, rest = argv[0], argv[1:]
    record = at = token = None
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
            if token is not None:
                raise Refused("That was said twice.")
            token = val
        else:
            if key in fields:
                raise Refused("That was said twice.")
            fields[key] = val
    return verb, record, at, yes, token, fields


def checked(verb: str, given: dict, root, record, today) -> dict:
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
            listed = ids(root, record, needs, given.get("question", ""))
            if raw not in listed and needs == "by-hand" and raw in ids(root, record, "in-hand"):
                raise Refused("A page counts that goal, so its number comes from that page.")
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
    nights, so a count read from those hours goes, and Claude asks for the nights."""
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
                g.pop("target", None)
                g.pop("rate", None)
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
        g = distance_by_hand(root, g)
        g.update(status="active", set={"at": stamp, "from": "chat" if by == "chat" else "page"})
        g = goalsfile.ordered(g)
        line = goalsfile.target_line(g, today)
        check = f"{short(text)}: {line or how(g, today).lower()}. {who_counts(root, g, who)}"
        return {"goal": g["id"], "before": None, "after": g, "index": len(doc["goals"]), "check": check,
                "saved": f"Saved. {how(g, today)}."}
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
            pass  # it counts it already, so there's nothing to ask and nothing changes
        elif page is not None and page["fits"]["script"]:  # the page says whether it counts it, and in what
            said = page_says(root, page, old)
            if not said["counts"]:
                raise Refused(" ".join(w for w in (said.get("why"), "It stays as it is.") if w))
            if said.get("as") == "nights" and old.get("unit") not in (None, "", "nights"):
                raise Refused(f"{page['title']} counts this in nights, so tell Claude to set it again.")
            g = dict(g, measured_by={"app": f["app"]}, unit=said["unit"].strip())
        else:
            g = distance_by_hand(root, dict(g, measured_by=None if f["app"] == "none" else {"app": f["app"]}))
        check = f"{name}: {who_short(root, g)}"
        saved = f"Saved. {who_short(root, g)}"
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


def token_of(verb: str, given: dict, raw, today) -> str:
    """What a chat save hands back: this verb, these fields, this file, this day."""
    body = json.dumps([verb, sorted(given.items()), hashlib.sha256(raw or b"").hexdigest(), today.isoformat()])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


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


# ---- answers to Goals' own questions --------------------------------

def take_back(path, question: str) -> None:
    """Takes a question's last answer back out of answers.jsonl, so the file is byte for byte as it was before that
    answer. The file goes when that line was all it held."""
    take_out(path, lambda obj: obj.get("question") == question)


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


SAVED = "Saved."  # what an answer under Claude asks says, word for word
OFFER_ONLY = "That question takes Count it or Not this one."
NOT_COUNTED = "Not counted yet. Tell Claude to keep it by hand."  # a goal no page counts


def offer_answer(q, f, doc, root, record, now, by, yes, raw, stamp, gid) -> dict:
    """The one offer, answered: "Count it" moves the goal to the page that arrived, as `measure` does,
    and has that page count it at once; "Not this one" keeps it by hand, its answer's line alone. Undo (`unanswer`)
    puts goals.json and answers.jsonl back byte for byte."""
    app = q["id"].split("-", 2)[2] if q["id"].count("-") >= 2 else ""
    pick = f.get("pick")
    if q.get("kind") != "one" or "words" in f or pick not in ("count", "pass"):
        raise Refused(OFFER_ONLY)
    g = next((g for g in doc["goals"] if g["id"] == gid), None)
    if g is None:
        raise Refused(GONE)
    if pick == "count":
        p = plan("measure", {"goal": gid, "app": app}, doc, root, record, now, by)
        if not yes:
            return {"ok": True, "said": p["check"]}
        with locked(record):
            line = {"at": stamp, "question": q["id"], **named(gid), "pick": "count", "on": True, "by": by}
            if p["after"] != p["before"]:
                line["change"] = keep(root, record, doc, raw, p, "measure", stamp)
            common.append_line(record / ANSWERS, line)
        count_now(root, gid)
        return {"ok": True, "said": SAVED}
    if not yes:
        return {"ok": True, "said": f"{short(g['text'])}: you keep it by hand."}
    with locked(record):
        common.append_line(record / ANSWERS, {"at": stamp, "question": q["id"], **named(gid), "pick": "pass", "on": True,
                                              "by": by})
    return {"ok": True, "said": SAVED}


def arrived(root, record, now, app: str) -> dict:
    """A page that just arrived (Hydra-OS's install calls this): each goal it measures already is counted
    at once, by its own `--count`; and each goal in hand that no page counted, set before it and fitting it (its
    `units`, else its own check), is offered to it once. The arrival and the goals offered go in Goals' own
    store/arrived.json, then say.json, home.json and the page are written again. {"ok", "counted", "offered"}."""
    page = next((p for p in pages.installed(root) if p["id"] == app), None)
    if page is None:
        raise Refused("That page isn't installed, so there's nothing to offer.")
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        raise Refused(goalsfile.BROKEN_LINE)
    import build
    mine = [g for g in doc["goals"] if g.get("status") == "active" and (g.get("measured_by") or {}).get("app") == app
            and goalsfile.read(g)]
    counted_now = len(mine) if mine and count_page(root, app) else 0
    fit = []
    for g in doc["goals"]:
        if g.get("status") != "active" or (g.get("measured_by") or {}).get("app") not in (None, common.ID):
            continue
        at = common.parse_time((g.get("set") or {}).get("at") or "")
        if at is None or at >= now:
            continue  # set while the page was here: who counts it was settled then
        # its units, else, for a unit no page names, its own check; a check has the final word, so "Count it" is never
        # refused
        mine = pages.unit_fits(page["fits"], g.get("unit"))
        if not (mine or (page["fits"]["script"] and not pages.claimed(root, g.get("unit")))):
            continue
        if page_says(root, page, g)["counts"] if page["fits"]["script"] else mine:
            fit.append(g["id"])
    with locked(record):
        path = record.joinpath(*build.ARRIVED)
        got = common.load_json(path, None)
        apps = dict(got["apps"]) if isinstance(got, dict) and isinstance(got.get("apps"), dict) else {}
        apps[app] = {"at": common.iso(now), "goals": fit}
        common.write_json(path, {"contract": "goal-arrivals/v1", "apps": apps})
    rebuild(root, record, now)
    return {"ok": True, "counted": counted_now, "offered": len(fit)}


def named(gid) -> dict:
    """An answer's line names its goal by its id, which the primer reads to quote the goal's latest answer on its
    line."""
    return {"goal": gid} if isinstance(gid, str) else {}


def answer(verb: str, f: dict, doc: dict, root, record, now, by: str, yes: bool, raw):
    """Goals' own questions, saved with Undo: a new goal's why, in the person's own words, saved as its why; and what
    got in the way of a goal behind, kept in answers.jsonl with its goal and shown on its page as "You said". Saving
    one answers "Saved."
    """
    q = next((q for q in questions(record) if q["id"] == f["question"]), None)
    if q is None:
        raise Refused("That question isn't on Goals' page any more, so nothing was saved.")
    stamp, gid = common.iso(now), q.get("goal")
    said = [x for x in common.lines(record / ANSWERS) if x.get("question") == q["id"]]
    last = said[-1] if said and not said[-1].get("undone") else None
    if verb == "unanswer":
        if last is None:  # nothing was answered, so there's nothing to take back, and that's no error
            return {"ok": True, "said": "Nothing to put back."}
        if "pick" in f and f["pick"] != last.get("pick"):
            raise Refused("That isn't the answer that was given.")
        if not yes:
            return {"ok": True, "said": "Put back."}
        with locked(record):
            if last.get("change"):
                e = next((e for e in undoable(doc, journal(record)) if e["id"] == last["change"]), None)
                if e is not None:
                    keep(root, record, doc, raw, {"goal": e["goal"], "before": e.get("after"), "after": e.get("before"),
                                                  "index": e.get("index", 0), "undoes": e["id"]}, "undo", stamp)
            take_back(record / ANSWERS, q["id"])
        return {"ok": True, "said": "Put back."}
    if q["id"].startswith("o-"):
        return offer_answer(q, f, doc, root, record, now, by, yes, raw, stamp, gid)
    if q.get("kind") != "words" or "pick" in f or "on" in f or "words" not in f:
        raise Refused(WORDS_ONLY)
    goalsfile.locked(f["words"])
    if q["id"].startswith("x-"):  # what got in the way: its words in answers.jsonl alone, goals.json as it is
        g = next((g for g in doc["goals"] if g["id"] == gid), None)
        if g is None:
            raise Refused("That goal isn't on Goals' page any more, so nothing was saved.")
        if not yes:
            return {"ok": True, "said": f"{short(g['text'])}, what got in the way: {short(f['words'])}"}
        with locked(record):
            common.append_line(record / ANSWERS, {"at": stamp, "question": q["id"], **named(gid), "words": f["words"],
                                                  "by": by})
        return {"ok": True, "said": SAVED}
    # a new goal's why: the same save as `because`, its words kept in answers.jsonl as every answer is
    p = plan("because", {"goal": gid, "words": f["words"]}, doc, root, record, now, by)
    if not yes:
        return {"ok": True, "said": p["check"]}
    with locked(record):
        line = {"at": stamp, "question": q["id"], **named(gid), "words": f["words"], "by": by}
        if p["after"] != p["before"]:
            line["change"] = keep(root, record, doc, raw, p, "because", stamp)
        common.append_line(record / ANSWERS, line)
    return {"ok": True, "said": SAVED}


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
    verb, record, at, yes, token, given = parse(argv)
    if verb == "ids":
        raise Refused("Say which list.")
    if verb == "arrived":  # not a page's action: Hydra-OS's install, when a page arrives
        app = given.get("app") if set(given) == {"app"} else ""
        if not (app and app == app.lower() and app.replace("-", "").isalnum() and app[0].isalpha() and len(app) <= 32):
            raise Refused("Say which page arrived: --app=<its id>.")
        root = common.root_of(record)
        return arrived(root, common.record_of(root, record), common.now(at), given["app"])
    if verb not in FIELDS:
        raise Refused("That isn't something Goals does.")
    root = common.root_of(record)
    record = common.record_of(root, record)
    now = common.now(at)
    by = "chat" if os.environ.get("HYDRA_BY") == "chat" else "page"
    try:
        doc, raw = goalsfile.load(root)
    except goalsfile.Broken:
        raise Refused(goalsfile.BROKEN_LINE)
    f = checked(verb, given, root, record, now.date())
    tok = token_of(verb, given, raw, now.date())
    if yes and by == "chat" and token != tok:
        raise Refused(NOT_READ_BACK)
    if verb in ("answer", "unanswer"):
        out = answer(verb, f, doc, root, record, now, by, yes, raw)
        if not yes and by == "chat":
            out["token"] = tok
        if yes:
            rebuild(root, record, now)
        return out
    p = plan(verb, f, doc, root, record, now, by)
    if not yes:
        out = {"ok": True, "said": p["check"]}
        if by == "chat":
            out["token"] = tok
        return out
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
        if argv[:1] == ["ids"]:
            which = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else ""
            _, record, _, _, _, given = parse(["ids"] + argv[2:])
            if which not in LISTS or set(given) - {"question"}:
                raise Refused("That isn't something Goals can list.")
            root = common.root_of(record)
            try:
                print(json.dumps(ids(root, common.record_of(root, record), which, given.get("question", ""))))
            except goalsfile.Broken:
                print("[]")
            return 0
        print(json.dumps(run(argv), ensure_ascii=False))
        return 0
    except Refused as e:
        print(json.dumps({"ok": False, "said": str(e)}, ensure_ascii=False))
        return 2
    except common.NotSetUp as e:
        print(json.dumps({"ok": False, "said": str(e)}, ensure_ascii=False))
        return 2
    except Exception:  # noqa: BLE001  (never a traceback: the page shows this line)
        print(json.dumps({"ok": False, "said": "Goals couldn't save that just now. Nothing was changed."}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
