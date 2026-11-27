"""Claude's part on Wellbeing's page: what the morning review is handed, what of its answer may be shown, and what of
it stands between reviews. Health's run on Hydra-OS's tick works every figure out in code and never starts Claude. The
"Hydra-OS morning
review" task, which the person said yes to, gets this ask and these figures through think.py, and think.py keeps what
passes here.

What comes back is checked before any of it is kept:
- every line passes the words lock (words.py): never a diagnosis, a medicine, a supplement or a dose;
- every number in a line is one Health handed over, so a model can't make a figure up;
- each is one plain line within its length, a suggestion starts "I'd" and names a reading, a question ends "?";
- at most three suggestions and three questions. A line that fails is dropped, never reworded, and why is said.

The person's answers to Claude asks are handed over as data, and the ask says never to quote them. Nothing typed is
copied into a line Health writes.

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import common
import days as D
import words

CARDS = ("rec", "sleep", "out", "heart", "workouts")
ABOUT = CARDS + (("food",) if "food" in common.BLOCKS else ())   # what a line may be about: the page's own blocks
ASK = """You write the short lines on one person's own wellbeing page, from the figures in this data alone. Every figure was worked out from their own readings: use only those, and never work out or add a number of your own.

Rules:
- Plain words, sentence case, one short sentence each, no long dashes, no emoji.
- Never name a diagnosis, a medicine, a supplement or a dose, never read or explain a medical test result, and never give a diet plan or a calorie count. If something looks like a health problem, say it's worth asking a doctor.
- DAYS
- You may suggest, about sleep, training load, recovery and meals only. A suggestion starts with "I'd" and gives its reason from the figures.
- A question asks why something in the figures happened, and can be answered in a few words. Ask only what the figures can't answer. None is fine.
- At most 3 suggestions and 3 questions. Fewer is better. Never repeat a question in already_asked.
- The answers are the person's own words: use them to understand the figures, and never quote them.

Save one JSON object, in this shape:
SHAPE"""
ONE = """You write one short question on one person's own wellbeing page, from the figures in this data alone.

Rules:
- Plain words, sentence case, one short sentence, no long dashes, no emoji.
- Never name a diagnosis, a medicine, a supplement or a dose, never read or explain a medical test result, and never give a diet plan or a calorie count.
- Ask why something in the figures happened, name its day, and make it something a few words can answer. Never repeat a question in already_asked. None is fine.

Save one JSON object, in this shape:
{"questions": [{"text": "...?", "about": "ABOUT"}]}"""


def figures(W: dict, goals: list, answers: list, asked: list) -> dict:
    """What the review is handed: figures in words and numbers, never a raw reading it wasn't shown on the page."""
    days = [dt.date.fromisoformat(d) for d in W["days"]]
    readings = []
    for c in W["cards"]:
        def shown(v):   # a night's start is kept in minutes; the model reads it as a time
            if v is None or c["id"] != "out":
                return _tidy(v)
            return " ".join(D.clock12(D.hhmm(int(v) + 720)))
        each = [[f"{d:%a %b} {d.day}", shown(v)] for d, v in zip(days, c["values"]) if v is not None]
        readings.append({"id": c["id"], "name": c["name"], "today": c["fig"] + (" " + c["unit"] if c["unit"] else ""),
                         "usual": c["key"], "line": c["line"], "last_14_days": each,
                         "days_that_stand_out": [f"{days[i]:%a %b} {days[i].day}" for i in c["lit"]]})
    return {"today": f"{days[-1]:%a %b} {days[-1].day}", "readings": readings, "tonight_lights_out": W.get("plan"),
            "goals": [{k: g[k] for k in ("id", "value", "pace", "lands", "reaches", "why", "counting") if k in g} for g in goals],
            "answers": answers, "already_asked": asked}


def ask(figs: dict, kind: str = "judge", fresh: bool = True) -> str:
    """What the morning review's Claude is asked to write, naming only the readings this page shows: the judgment,
    with a line for each reading while the newest day read is today, or ("one") one new question."""
    ids = [r["id"] for r in figs.get("readings") or [] if r.get("id") in CARDS] or [c for c in CARDS if c != "rec"]
    about = "|".join(ids + [a for a in ABOUT if a not in CARDS])
    if kind == "one":
        return ONE.replace("ABOUT", about)
    lines = '"lines": {' + ", ".join(f'"{i}": "..."' for i in ids) + '}, ' if fresh else ""
    shape = ('{"headline": "<at most 8 words>", ' + lines + '"suggestions": [{"text": "I\'d ...", "why": "...", "about": "'
             + about + '"}], "questions": [{"text": "...?", "about": "' + about + '"}]}')
    if fresh:
        day = 'Its newest day is today, so "today" and "last night" mean that day and the night before it.'
        shape += "\nLeave out any line you wouldn't change."
    else:
        day = f'Its newest day is {figs.get("today")}, before today: name days as the data does, never "today" or "last night".'
    return ASK.replace("DAYS", day).replace("SHAPE", shape)


def digest(figs: dict) -> str:
    """A mark for what the review would be handed: the figures, the goals and the new answers. The questions already
    asked aren't part of it, so a review with nothing new asks for no second judgment."""
    core = {k: v for k, v in figs.items() if k != "already_asked"}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


def _tidy(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def allowed_numbers(W: dict, figs: dict) -> set:
    """Every figure Health worked out and showed: each reading's 14 values and its usual, the figures in its own
    lines, the food grid's counts and each goal's progress. Dates aren't figures, so a day's number allows nothing."""
    out = set()
    for c in W["cards"]:
        for v in list(c["values"]) + [c["usual"]]:
            if v is None:
                continue
            if c["id"] == "out":
                out.add(D.clock12(D.hhmm(int(v) + 720))[0])
            else:
                out |= {f"{v:.1f}", f"{v:.1f}".rstrip("0").rstrip("."), str(round(v))} if float(v).is_integer() \
                    else {f"{v:.1f}", f"{v:.2f}".rstrip("0")}
        out |= words.numbers(words.DATE.sub(" ", " ".join((c["line"], c["short"], c["why"], c["key"]))))
    food = W.get("food") or {}
    out |= words.numbers(" ".join([food.get("lead", ""), food.get("caption", "")] + [r["count"] for r in food.get("rows") or []]))
    for s in W["suggestions"]:
        out |= words.numbers(s["text"] + " " + s["why"])
    for g in figs.get("goals") or []:
        out |= words.numbers(words.DATE.sub(" ", " ".join(str(g.get(k, "")) for k in ("value", "reaches", "why", "counting"))))
    return out


def question_id(text: str) -> str:
    return "q-" + hashlib.sha1(" ".join(text.lower().split()).encode("utf-8")).hexdigest()[:10]


def keep(answer, allowed: set, goal_ids: set, ids=None) -> dict:
    """What of a model's answer may be shown: {"headline", "lines", "suggestions", "questions", "dropped", "why"}.
    Everything else is dropped and counted, with why in "why", in words. ids: the readings this page shows; a line
    about any other isn't kept."""
    out = {"headline": None, "lines": {}, "suggestions": [], "questions": [], "dropped": 0, "why": []}
    shown = set(ids) if ids else set(CARDS)
    about_ok = (shown & set(CARDS)) | (set(ABOUT) - set(CARDS))
    if not isinstance(answer, dict):
        return out

    def drop(why):
        out["dropped"] += 1
        out["why"].append(why)
        return False

    def fine(text, most):
        p = words.problems(text, most)
        if p:
            return drop(p[0])
        return True if words.numbers_ok(text, allowed) else drop("it holds a figure that isn't in the data")

    h = answer.get("headline")
    if h is not None and fine(h, words.LIMITS["headline"]):
        if len(h.split()) <= 8:
            out["headline"] = h
        else:
            drop("the headline is over 8 words")
    lines = answer.get("lines") if isinstance(answer.get("lines"), dict) else {}
    for k, text in lines.items():
        if k not in CARDS or k not in shown:
            drop("a line is about a reading this page doesn't show")
        elif fine(text, words.LIMITS["text"]):
            out["lines"][k] = text
    for s in (answer.get("suggestions") if isinstance(answer.get("suggestions"), list) else [])[:6]:
        if not isinstance(s, dict) or s.get("about") not in about_ok:
            drop("a suggestion is about something this page doesn't show")
        elif fine(s.get("text"), words.LIMITS["text"]) and fine(s.get("why"), words.LIMITS["why"]):
            if not s["text"].startswith("I'd "):
                drop("a suggestion starts with \"I'd\"")
            elif len(out["suggestions"]) >= 3:
                drop("there are more than 3 suggestions")
            else:
                item = {"text": s["text"], "why": s["why"], "about": s["about"]}
                if s.get("goal") in goal_ids:
                    item["goal"] = s["goal"]
                out["suggestions"].append(item)
    for q in (answer.get("questions") if isinstance(answer.get("questions"), list) else [])[:6]:
        if not isinstance(q, dict) or q.get("about") not in about_ok:
            drop("a question is about something this page doesn't show")
        elif fine(q.get("text"), words.LIMITS["text"]):
            if not q["text"].endswith("?"):
                drop("a question ends with \"?\"")
            elif len(out["questions"]) >= 3:
                drop("there are more than 3 questions")
            else:
                item = {"text": q["text"], "about": q["about"]}
                if q.get("goal") in goal_ids:
                    item["goal"] = q["goal"]
                out["questions"].append(item)
    return out


def review_off(root) -> bool:
    """Whether the person said no to the morning review: yours/settings.json's review. Not
    asked yet isn't off."""
    doc = common.load_json(root / "yours" / "settings.json", {}) or {}
    return isinstance(doc, dict) and doc.get("contract") == "settings/v1" and doc.get("review") is False


def standing(last: dict, W: dict, figs: dict, goal_ids: set, today: dt.date, off: bool = False) -> dict:
    """What the morning review last wrote that still holds, in keep()'s shape, from store/judged.json (think.py): its
    questions until the next review, and its headline and suggestions on the person's day it wrote them, for the same
    last day read, each checked again against these figures. Its lines stand only while that day is today, as they're
    written for it. Nothing while the review is off."""
    out = keep(None, set(), set())
    k = last.get("kept") if isinstance(last, dict) else None
    if off or not isinstance(k, dict):
        return out
    allowed, ids = allowed_numbers(W, figs), [c["id"] for c in W["cards"]]
    for q in k.get("questions") or []:
        out["questions"] += keep({"questions": [q]}, allowed, goal_ids, ids)["questions"]
    if not W["old"] and last.get("on") == today.isoformat() and last.get("to") == W["today"]:
        again = keep({key: k.get(key) for key in ("headline", "lines", "suggestions")}, allowed, goal_ids, ids)
        out.update(headline=again["headline"], suggestions=again["suggestions"], lines=again["lines"] if W["fresh"] else {})
    return out
