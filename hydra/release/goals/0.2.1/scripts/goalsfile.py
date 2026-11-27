"""The goals file, <root>/yours/goals.json: its shape and limits, the typed-words rule,
the locks, and how a goal said as a rate is counted. Only scripts/act.py writes the file. Everything else reads it.

Every line a person may see from here is in plain words, for someone who has never used Hydra-OS: what to do next,
and no word for how it's built.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

import common

CONTRACT = "goals/v1"
FILE = "goals.json"
MAX_HAND, MAX_ALL = 12, 60
TEXT_MAX, WHY_MAX, UNIT_MAX = 120, 120, 16
LIMIT = 1_000_000_000
GOAL_ID = re.compile(r"g-[0-9a-f]{6}")
APP_ID = re.compile(r"[a-z][a-z0-9-]{0,31}")
STATUSES = ("active", "done", "aside")
PERS = {"day": 1.0, "week": 7.0, "month": 30.44}
KEYS = ("id", "text", "why", "measured_by", "unit", "start", "target", "by", "rate", "status", "ended", "set", "changed")
NEEDED = ("id", "text", "measured_by", "status", "set")

# ---- the person's typed words ------
CONTROL = re.compile("[\x00-\x1f\x7f-\x9f  ]")
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# A link: a scheme, www., or a bare domain of any ending ("made-up.example"). A missing space after a full stop reads
# as one too, so the line it gives says both.
LINK = re.compile(r"(?i)[a-z][a-z0-9+.-]*://|\bwww\.|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?![a-z0-9-])")
DIGITS = re.compile(r"\+?\(?[0-9][0-9 ().-]{6,}[0-9]")  # a run a phone number could be: refused with ten digits or more
WHEN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[ T][0-9]{1,2}:[0-9]{2})?|[0-9]{1,2}:[0-9]{2}")  # a day or a time isn't one
SECRET = re.compile(r"[A-Za-z0-9_\-.=+/]{24,}")
FOLDER = re.compile(r"/Users/|/home/[^/\s]+/|~/")  # a home folder spelled out, or a path under one

# ---- the locks: never a goal about a diagnosis, a medicine, a supplement or a dose, and never
# one to buy, sell or hold a security. "Save $20,000 for a deposit" and "Sleep 7 hours a night" are fine.
CARE = re.compile(r"\b(?:diagnos\w*|medicat\w*|medicines?|meds|prescri\w*|pills?|dos(?:e|es|age|ing)|supplements"
                  r"|(?:a|an|any|take|taking|daily|new|my)\s+supplement|\d+\s?(?:mg|mcg|iu))\b", re.I)
TRADE = re.compile(r"\b(?:buy|buying|sell|selling|hold|holding|short|shorting|trade|trading|purchase|purchasing"
                   r"|invest in|investing in)\b", re.I)
SECURITY = re.compile(r"\b(?:shares?|stocks?|securit(?:y|ies)|etfs?|index funds?|mutual funds?|hedge funds?"
                      r"|crypto\w*|bitcoin|ethereum|bonds?|equit(?:y|ies))\b|\$[A-Z]{2,5}\b", re.I)
CARE_LINE = ("Goals doesn't keep a goal about a diagnosis, a medicine, a supplement or a dose. "
             "Try the habit behind it, like 'Sleep 7 hours a night'.")
TRADE_LINE = ("Goals doesn't keep a goal to buy, sell or hold an investment. "
              "A sum works, like 'Save $20,000 for a deposit'.")
BROKEN_LINE = "Your goals couldn't be read just now, so nothing was changed."


class Refused(Exception):
    """A change the save path won't make, with its reason in one plain line."""


class Broken(Exception):
    """The file is there and isn't goals/v1. Nothing is written over it."""


def typed(value, most: int, what: str = "That") -> str:
    """The person's typed line, normalised: one line of 1 to `most` characters, with no control character, email
    address, link (a scheme, www. or a bare domain), run of ten digits, folder path or key, as Home's server holds
    it too. Refused with what to do about it."""
    if not isinstance(value, str) or CONTROL.search(value):
        raise Refused("Say it in one line of plain words.")
    s = " ".join(unicodedata.normalize("NFC", value).split())
    if not s:
        raise Refused("Say it in a line first.")
    if len(s) > most:
        raise Refused(f"{what} is {len(s)} characters long. Keep it to {most}.")
    for rx, said in ((ADDRESS, "Leave the email address out of it."), (FOLDER, "Leave the folder's path out of it."),
                     (SECRET, "That looks like it holds a key or a password. Leave it out."),
                     (LINK, "That reads as holding a web address. Leave it out, or put a space after the full stop.")):
        if rx.search(s):
            raise Refused(said)
    if any(sum(c.isdigit() for c in m.group(0)) >= 10 for m in DIGITS.finditer(WHEN.sub(" ", s))):
        raise Refused("Leave the phone number, or any number that long, out of it.")
    return s


def locked(text: str) -> None:
    """Refuses a goal the locks don't allow."""
    if CARE.search(text):
        raise Refused(CARE_LINE)
    if TRADE.search(text) and SECURITY.search(text):
        raise Refused(TRADE_LINE)


# ---- the file ---------------------------------------------------------------------------------------------------

def path(root):
    return common.yours(root) / FILE


def empty() -> dict:
    return {"contract": CONTRACT, "goals": []}


def dump(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def load(root):
    """(the file's document, its bytes, or None when there's no file yet). Raises Broken when it isn't goals/v1."""
    p = path(root)
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return empty(), None
    except OSError as e:
        raise Broken(type(e).__name__)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise Broken("not JSON")
    found = problems(doc)
    if found:
        raise Broken(found[0])
    return doc, raw


def write(root, doc: dict) -> None:
    """The file whole or not at all, mode 0600 in a 0700 yours/. Never a document that breaks the file's rules."""
    found = problems(doc)
    if found:
        raise Broken(found[0])
    common.write_whole(path(root), dump(doc), 0o600)


def read(goal: dict) -> bool:
    """A goal is read once it has its start, its target and its date."""
    return all(goal.get(k) is not None for k in ("start", "target", "by"))


def in_hand(doc: dict) -> int:
    return sum(1 for g in doc["goals"] if g.get("status") == "active")


def find(doc: dict, gid: str):
    for i, g in enumerate(doc["goals"]):
        if g.get("id") == gid:
            return i, g
    return None, None


def ordered(goal: dict) -> dict:
    """The goal with its keys in the file's own order (KEYS), and nothing empty."""
    return {k: goal[k] for k in KEYS if goal.get(k) is not None or k == "measured_by"}


def new_id(text: str, at: str, taken) -> str:
    """g- and six of 0-9a-f, from the line and when it was saved. It holds no word of the goal."""
    n = 0
    while True:
        gid = "g-" + hashlib.sha1(f"{at}\n{text}\n{n}".encode("utf-8")).hexdigest()[:6]
        if gid not in taken:
            return gid
        n += 1


def spans(start_on, by, per: str) -> float:
    """How many days, weeks or months lie between two days. A month is a calendar month, and part of one counts by
    its days over 30.44, so Jan 1 to Jul 1 is six months."""
    if per == "month":
        return (by.year - start_on.year) * 12 + (by.month - start_on.month) + (by.day - start_on.day) / PERS["month"]
    return (by - start_on).days / PERS[per]


def rate_target(start_value, start_on, by, rate: dict):
    """A goal said as a rate, stored as the count its path needs: n for each day, week or month from its start to
    its date, to the nearest whole and at least 1. Two a week from Jun 2 to Aug 1 is 17."""
    count = int(rate["n"] * spans(start_on, by, rate["per"]) + 0.5)
    return start_value + max(1, count)


def target_line(goal: dict, today) -> str:
    """The goal's target in a line, as a caption says it: "17 swims by Aug 1, at 2 a week". "" until it's read."""
    if not read(goal):
        return ""
    by = common.day(goal["by"])
    line = f"{common.with_unit(goal['target'], goal.get('unit'))} by {common.day_words(by, today)}"
    rate = goal.get("rate")
    return f"{line}, at {common.figure(rate['n'])} a {rate['per']}" if rate else line


def missing(goal: dict) -> list:
    """What a goal still needs before it's read, in the page's words."""
    out = []
    if goal.get("target") is None or goal.get("start") is None:
        out.append("no target yet")
    if goal.get("by") is None:
        out.append("no date yet")
    return out


# ---- the shape, held on every load and before every write -----------------------------------------------------

def _line(s, most) -> bool:
    return (isinstance(s, str) and 0 < len(s) <= most and not CONTROL.search(s) and s == " ".join(s.split()))


def goal_problems(g) -> list:
    if not isinstance(g, dict):
        return ["a goal isn't an object"]
    p = []
    extra = sorted(set(g) - set(KEYS))
    if extra:
        p.append(f"a goal holds a field outside the contract's table ({len(extra)})")
    if any(k not in g for k in NEEDED):
        p.append("a goal lacks its id, text, measured_by, status or set")
        return p
    if not (isinstance(g["id"], str) and GOAL_ID.fullmatch(g["id"])):
        p.append("a goal's id isn't g- and six of 0-9a-f")
    if not _line(g["text"], TEXT_MAX):
        p.append("a goal's text isn't one line of 1 to 120 characters")
    if "why" in g and not _line(g["why"], WHY_MAX):
        p.append("a goal's why isn't one line of at most 120 characters")
    m = g["measured_by"]
    if m is not None and not (isinstance(m, dict) and set(m) == {"app"} and isinstance(m["app"], str)
                              and APP_ID.fullmatch(m["app"])):
        p.append("a goal's measured_by isn't an app or null")
    if "unit" in g and not (_line(g["unit"], UNIT_MAX)):
        p.append("a goal's unit isn't a word or a sign of at most 16 characters")
    start, on = g.get("start"), None
    if start is not None:
        if not (isinstance(start, dict) and set(start) == {"value", "on"} and bounded(start["value"])
                and common.day(start["on"])):
            p.append("a goal's start isn't a value and a day")
            start = None
        else:
            on = common.day(start["on"])
    if "target" in g:
        if not bounded(g["target"]):
            p.append("a goal's target isn't a number in range")
        elif start is not None and g["target"] == start["value"]:
            p.append("a goal's target is its start")
    by = None
    if "by" in g:
        by = common.day(g["by"])
        if by is None:
            p.append("a goal's by isn't a day")
        elif on is not None and by <= on:
            p.append("a goal's by isn't after its start")
    r = g.get("rate")
    if r is not None and not (isinstance(r, dict) and set(r) == {"n", "per"} and common.number(r["n"]) and r["n"] > 0
                              and r["per"] in PERS):
        p.append("a goal's rate isn't a count for each day, week or month")
    if g["status"] not in STATUSES:
        p.append("a goal's status isn't active, done or aside")
    elif (g["status"] == "active") == ("ended" in g):
        p.append("a goal's ended doesn't go with its status")
    if "ended" in g and common.day(g["ended"]) is None:
        p.append("a goal's ended isn't a day")
    s = g["set"]
    if not (isinstance(s, dict) and set(s) == {"at", "from"} and common.parse_time(s["at"]) and s["from"] in ("chat", "page")):
        p.append("a goal's set isn't when it was saved and from where")
    if "changed" in g and common.parse_time(g["changed"]) is None:
        p.append("a goal's changed isn't a time with its offset")
    return p


def bounded(x) -> bool:
    return common.number(x) and -LIMIT <= x <= LIMIT


def problems(doc) -> list:
    """Each way the document breaks the goals file's rules, in words that hold none of its values."""
    if not isinstance(doc, dict) or set(doc) != {"contract", "goals"} or doc.get("contract") != CONTRACT:
        return ["it isn't a goals/v1 document"]
    goals = doc["goals"]
    if not isinstance(goals, list):
        return ["goals isn't a list"]
    p = []
    for g in goals:
        p += goal_problems(g)
    ids = [g.get("id") for g in goals if isinstance(g, dict)]
    if len(ids) != len(set(ids)):
        p.append("two goals share an id")
    if len(goals) > MAX_ALL:
        p.append("more than 60 goals")
    if sum(1 for g in goals if isinstance(g, dict) and g.get("status") == "active") > MAX_HAND:
        p.append("more than 12 goals in hand")
    return list(dict.fromkeys(p))
