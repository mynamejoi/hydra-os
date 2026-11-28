"""The day's check-in: one short question a day, "How's '{goal}' going?", about one goal in hand, which Home's Claude
asks and Claude in a Hydra-OS chat both ask, and its answer, saved at once with its Undo through the answer path every
page declares (`act.py answer` and `unanswer`).

- Which goal: each day, the goal in hand that has gone longest since its last check-in, one never asked first, in
  goals.json's order. A goal set today waits for tomorrow. Once a check-in is answered, that's the day's question,
  shown as answered in say.json and home.json, never with its words, so nothing more is asked that day.
- The answer is the person's own words, at most 120 characters: one line in answers.jsonl, Goals' own file, and never
  in say.json, home.json or shared/. For a goal kept by hand, a number said with the goal's unit ("7 books",
  "$2,400"), or the words being that number alone, is where it stands now: a line in store/progress.jsonl, so its pace
  moves. "2 more books" or "another 2 books" adds to the last number told. Words with no such number, or with more
  than one, move nothing. A goal a page counts keeps the words alone.
- Undo (`unanswer`) takes that answer's lines back out of both files, so each is byte for byte as before.
- Goals' page shows a goal's newest answer from the last 28 days in its detail, as "You said".

It starts no process and makes no request. Python 3.9, standard library only.
"""
from __future__ import annotations

import datetime as dt
import os
import re

import common
import goalsfile
from goalsfile import Refused

ANSWERS = "answers.jsonl"
PROGRESS = "store/progress.jsonl"
PREFIX = "ci-"  # a check-in's id: "ci-" and its goal's six characters
MAX = 120
SHOWN_DAYS = 28  # how long a goal's detail shows its newest answer
BLOCK = "goals"
TEXT = "How's '{goal}' going?"
BY_HAND_WHY = "Say where it stands with its number, and its pace moves."
CARE_LINE = ("Goals doesn't keep words about a diagnosis, a medicine, a supplement or a dose. "
             "Say how it's going without them.")
TRADE_LINE = "Goals doesn't keep words about buying, selling or holding an investment. Say how it's going without them."
WRITES = [ANSWERS, PROGRESS]
# column.md's answer path, as every page declares it, with the one more file a check-in's number goes to
DECLARED = [
    {"name": "answer", "script": ["scripts/act.py", "answer"], "confirm": "undo", "undo": "unanswer", "writes": WRITES,
     "fields": {"question": {"kind": "id", "list": ["scripts/act.py", "questions"]},
                "pick": {"kind": "id", "list": ["scripts/act.py", "picks"], "of": "question", "optional": True},
                "on": {"kind": "choice", "of": ["yes", "no"], "optional": True},
                "words": {"kind": "words", "max": MAX, "optional": True}}},
    {"name": "unanswer", "script": ["scripts/act.py", "unanswer"], "confirm": "once", "writes": WRITES,
     "fields": {"question": {"kind": "id", "list": ["scripts/act.py", "questions"]},
                "pick": {"kind": "id", "list": ["scripts/act.py", "picks"], "of": "question", "optional": True}}},
]
NUM = r"(?<![\d.,])(?P<n>\d{1,3}(?:,\d{3})+|\d+)(?P<f>\.\d+)?(?![\d,]*\.?\d)"  # 7, 2,400, 12.5
SIGNS = ("$", "\u20ac", "\u00a3")


def qid(gid: str) -> str:
    return PREFIX + gid[2:]


def goal_of(question: str) -> str:
    return "g-" + question[len(PREFIX):]


def answers(record) -> list:
    """Every check-in's answer in answers.jsonl, oldest first: {"at", "question", "words", ...}, each a real one."""
    return [x for x in common.lines(record / ANSWERS) if isinstance(x.get("question"), str)
            and x["question"].startswith(PREFIX) and isinstance(x.get("words"), str) and common.parse_time(x.get("at"))]


def on_day(x: dict):
    return common.parse_time(x["at"]).date()


def set_on(goal: dict):
    at = common.parse_time((goal.get("set") or {}).get("at") or "")
    return at.date() if at else None


def by_hand(goal: dict) -> bool:
    return (goal.get("measured_by") or {}).get("app") == common.ID


def pick(doc: dict, record, today: dt.date):
    """The goal to ask about today: of the goals in hand set before today, one never asked, in the file's order, else
    the one asked longest ago. None when there's none."""
    last = {}
    for x in answers(record):
        last[goal_of(x["question"])] = on_day(x)
    hand = [g for g in doc["goals"] if g.get("status") == "active" and set_on(g) and set_on(g) < today]
    never = [g for g in hand if g["id"] not in last]
    if never:
        return never[0]
    return min(hand, key=lambda g: last[g["id"]]) if hand else None  # min keeps the file's order on a tie


def made(goal: dict, today: dt.date) -> dict:
    q = {"id": qid(goal["id"]), "kind": "words", "text": TEXT, "max": MAX, "block": BLOCK, "home": True,
         "ends": (today + dt.timedelta(days=1)).isoformat(), "goal": goal["id"]}
    if by_hand(goal) and goalsfile.read(goal):  # its number moves its pace
        q["why"] = BY_HAND_WHY
    return q


def question(doc: dict, record, now):
    """Today's check-in as say.json holds it: open, or, once answered today, with its `answer`, never the words. None
    with no goal to ask about."""
    today = now.date()
    done = [x for x in answers(record) if on_day(x) == today]
    if done:
        _, goal = goalsfile.find(doc, goal_of(done[-1]["question"]))
        if goal is None:
            return None
        return dict(made(goal, today), answer={"at": done[-1]["at"], "words": True})
    goal = pick(doc, record, today)
    return made(goal, today) if goal else None


def for_home(q):
    """home.json's questions: today's check-in, as Home asks it, and once answered today with its `answer`, never
    the words, so Home shows it saved, with its Undo."""
    if not q:
        return []
    out = {k: q[k] for k in ("id", "kind", "text", "max", "goal")}
    if "answer" in q:
        out["answer"] = dict(q["answer"])
    return [out]


def said(doc: dict, record, today: dt.date) -> dict:
    """{goal id: {"words", "on"}}: each goal in hand's newest answer from the last SHOWN_DAYS days, for its detail."""
    hand = {g["id"] for g in doc["goals"] if g.get("status") == "active"}
    out = {}
    for x in answers(record):
        gid, d = goal_of(x["question"]), on_day(x)
        if gid in hand and 0 <= (today - d).days < SHOWN_DAYS:
            out[gid] = {"words": x["words"], "on": d.isoformat()}
    return out


def today_words(doc: dict, record, now) -> dict:
    """{question id: words} for today's answered check-in, as the kit shows it in Claude asks."""
    q = question(doc, record, now)
    if not q or "answer" not in q:
        return {}
    done = [x for x in answers(record) if on_day(x) == now.date() and x["question"] == q["id"]]
    return {q["id"]: done[-1]["words"]} if done else {}


# ---- where a goal kept by hand stands, from the words ---------------------------------------------------------------

def forms(unit: str) -> list:
    """The ways the goal's unit is said: "books" and "book"; "km", and kilometers; "miles" and "mile"."""
    u = unit.strip().lower()
    out = [u]
    if u.endswith("s") and len(u) > 2:
        out.append(u[:-1])
    if u == "km":
        out += ["kilometers", "kilometres", "kilometer", "kilometre"]
    return sorted(set(out), key=len, reverse=True)


def figure(m) -> float:
    n = float(m.group("n").replace(",", "") + (m.group("f") or ""))
    return int(n) if n.is_integer() else n


def standing(goal: dict, words: str, last):
    """Where a goal kept by hand stands, read from its check-in's words: the one number said with its unit ("7 books",
    "$2,400", "12.5 km"), or the words being that number alone ("7"). "2 more books" or "another 2 books" adds to
    `last`, the last number told. None for no such number, or more than one."""
    unit = (goal.get("unit") or "").strip()
    s = " ".join(words.split())
    alone = re.fullmatch(NUM + r"\s*\.?", s)
    if alone:
        return figure(alone)
    if not unit:
        return None
    if unit in SIGNS:  # a sum: "$2,400", "$300 more", "another $300"
        rx = r"(?P<another>another\s+)?" + re.escape(unit) + r"\s?" + NUM + r"(?P<after>\s+more\b)?"
    else:
        rx = (r"(?P<another>another\s+)?" + NUM + r"\s?(?P<more>more\s+)?(?:" + "|".join(re.escape(f) for f in forms(unit))
              + r")\b(?P<after>\s+more\b)?")
    hits = list(re.finditer(rx, s, re.I))
    if len(hits) != 1:
        return None
    m = hits[0]
    n = figure(m)
    if any(m.groupdict().get(k) for k in ("another", "more", "after")):
        return last + n if common.number(last) else None
    return n


def last_told(record, goal: dict):
    """The last number told for the goal, as its pace reads it, else where it began."""
    told = [x for x in common.lines(record / PROGRESS) if x.get("goal") == goal["id"] and common.number(x.get("value"))
            and common.day(x.get("on"))]
    if told:
        return max(enumerate(told), key=lambda ix: (ix[1]["on"], ix[0]))[1]["value"]
    start = (goal.get("start") or {}).get("value")
    return start if common.number(start) else None


# ---- the save and its Undo -------------------------------------------------------------------------------------------

def checked_words(words) -> str:
    s = goalsfile.typed(words, MAX)
    if goalsfile.CARE.search(s):
        raise Refused(CARE_LINE)
    if goalsfile.TRADE.search(s) and goalsfile.SECURITY.search(s):
        raise Refused(TRADE_LINE)
    return s


def by() -> str:
    return "chat" if os.environ.get("HYDRA_BY") == "chat" else "page"


def answer(root, record, now, f: dict, yes: bool, rebuild) -> dict:
    """A check-in's answer, saved at once: its line in answers.jsonl and, for a goal kept by hand whose words say where
    it stands, that number's line in store/progress.jsonl. Without --yes, what it would save, and nothing written."""
    if "pick" in f or "on" in f:
        raise Refused("This one takes their words, not a pick.")
    if "words" not in f:
        raise Refused("Say how it's going, in their words.")
    words = checked_words(f["words"])
    doc, _ = goalsfile.load(root)
    q = question(doc, record, now)
    if not q or q["id"] != f["question"]:
        raise Refused("That check-in isn't today's any more, so nothing was saved.")
    _, goal = goalsfile.find(doc, q["goal"])
    stamp, today = common.iso(now), now.date()
    told = None
    if by_hand(goal) and goalsfile.read(goal):
        value = standing(goal, words, last_told(record, goal))
        began = common.day((goal.get("start") or {}).get("on") or "")
        if value is not None and abs(value) <= goalsfile.LIMIT and not (began and today < began):
            told = {"goal": goal["id"], "value": value, "on": today.isoformat(), "at": stamp, "by": by()}
    figure_ = common.with_unit(told["value"], goal.get("unit")) if told else ""
    if not yes:
        return {"ok": True, "said": f"Saves what you said, with {figure_} as where it stands today." if told else
                "Saves what you said."}
    line = {"at": stamp, "question": q["id"], "words": words, "on": True, "by": by(), "goal": goal["id"]}
    if told:
        common.append_line(record / PROGRESS, told)
        line["told"] = told
    common.append_line(record / ANSWERS, line)
    rebuild(root, record, now)
    if told:
        saved = f"Saved: {figure_}, as of today."
    elif by_hand(goal) and goalsfile.read(goal):
        saved = "Saved. Say where it stands with its number, and its pace moves too."
    else:
        saved = "Saved. It shows with the goal on Goals' page."
    return {"ok": True, "said": saved, "undo": {"question": q["id"]}}


def unanswer(root, record, now, f: dict, yes: bool, rebuild, take_out) -> dict:
    """Today's newest answer to that check-in back out, with the number it told, so both files are byte for byte as
    before it."""
    if "pick" in f:
        raise Refused("This one takes their words, not a pick.")
    done = [x for x in answers(record) if on_day(x) == now.date() and x["question"] == f["question"]]
    if not done:
        if yes:
            rebuild(root, record, now)
        return {"ok": True, "said": "Nothing to put back."}
    if not yes:
        return {"ok": True, "said": "Takes back what you said today."}
    x = done[-1]
    take_out(record / ANSWERS, lambda obj: obj == x)
    if isinstance(x.get("told"), dict):
        take_out(record / PROGRESS, lambda obj: obj == x["told"])
    rebuild(root, record, now)
    return {"ok": True, "said": "Put back."}
