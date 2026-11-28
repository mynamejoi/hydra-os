"""What a run concluded: <Health's folder>/say.json, say/v1, written whole, mode 0600. The
page, Home's tile, the summary and Goals all read this one file.

- insights: one for each reading, in the block it belongs to, and one for a source that couldn't be read or that
  Health can't read yet, which is said out loud, never skipped;
- suggestions: at most three, each with its why and the insight it answers; `rule` when code worked it out, `model`
  when the judgment step wrote it. Never a button;
- questions: at most three open, in the person's own words to answer. One answered since the last run stays, with
  only that it was answered: the typed words stay in answers.jsonl;
- goals: Health's progress toward each goal it measures, [] when it measures none.

Every line passes the words lock first (words.py). One that doesn't is left out.

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import datetime as dt

import common
import judge
import words

BLOCK = {"rec": "today", "workouts": "today", "sleep": "today", "heart": "today", "out": "today", "food": "food"}
ASK_DAYS = 2      # a question stops asking by itself after this many days


def stale_after(now: dt.datetime, at: str) -> dt.datetime:
    """Two hours after the next scheduled read."""
    try:
        h, m = (int(x) for x in at.split(":"))
    except (ValueError, AttributeError):
        h, m = 7, 40
    t = now.astimezone()
    due = t.replace(hour=h, minute=m, second=0, microsecond=0)
    if due <= t:
        due += dt.timedelta(days=1)
    return due + dt.timedelta(hours=2)


def compose(W: dict, kept: dict, goals: list, now: dt.datetime, at: str, notes: list, answered: list, done=()) -> dict:
    """say.json as a dict. kept: judge.keep()'s answer (or its empty shape). notes: [(text, why)] for sources that
    couldn't be read. answered: the questions answered since the last run, as say.json holds them. done: every question
    with an answer standing, which is never asked again, whoever asks it."""
    insights = []
    for c in W["cards"]:
        text = kept["lines"].get(c["id"]) or c["line"]
        row = {"id": f"i-{c['id']}", "block": BLOCK[c["id"]], "text": text, "why": c["why"]}
        if c["moved"]:
            row["moved"] = c["moved"]
        insights.append(row)
    food = W.get("food") or {}
    if food.get("lead") and "food" in common.BLOCKS:   # only when the page has Food and drink
        insights.append({"id": "i-food", "block": "food", "text": food["lead"], "why": food["why"]})
    for text, why in notes[:6 - len(insights)][:2]:
        if words.ok(text, words.LIMITS["text"]) and words.ok(why, words.LIMITS["why"]):
            insights.append({"id": "i-source" if "i-source" not in {i["id"] for i in insights} else "i-source-2", "block": "connections",
                             "text": text, "why": why})
    ids = {i["id"] for i in insights}

    suggestions = []

    def add(text, why, about, kind, goal=None):
        if len(suggestions) < 3 and f"i-{about}" in ids and text not in [s["text"] for s in suggestions] \
                and words.ok(text, words.LIMITS["text"]) and words.ok(why, words.LIMITS["why"]):
            s = {"id": f"s-{len(suggestions) + 1}", "text": text, "why": why, "answers": f"i-{about}", "kind": kind}
            if goal:
                s["goal"] = goal
            suggestions.append(s)

    rule = W["suggestions"]
    for s in rule[:1] if any(c.get("ask") for c in W["cards"]) else []:   # "worth asking a doctor" always leads
        add(s["text"], s["why"], s["answers"], "rule")
    for s in kept["suggestions"]:
        add(s["text"], s["why"], s["about"], "model", s.get("goal"))
    for s in rule if not kept["suggestions"] else []:   # the lines worked out in code stand when no model wrote any
        add(s["text"], s["why"], s["answers"], "rule")

    questions = list(answered)
    day = now.astimezone().date()
    for q in kept["questions"]:
        if len([x for x in questions if "answer" not in x]) >= 3 or BLOCK[q["about"]] not in common.BLOCKS:
            continue
        qid = judge.question_id(q["text"])
        if qid in {x["id"] for x in questions} or qid in done:
            continue
        row = {"id": qid, "kind": "words", "text": q["text"], "max": 120, "block": BLOCK[q["about"]],
               "home": not [x for x in questions if x.get("home") and "answer" not in x],
               "ends": (day + dt.timedelta(days=ASK_DAYS)).isoformat()}
        if q.get("goal"):
            row["goal"] = q["goal"]
        questions.append(row)

    headline = kept.get("headline") or W["headline"]
    out = {"contract": "say/v1", "as_of": common.iso(now), "stale_after": common.iso(stale_after(now, at)),
           "headline": headline, "insights": insights, "suggestions": suggestions, "questions": questions, "goals": goals}
    if (W.get("counts") or {}).get("days"):   # the one last day read, which every reader takes
        out["data_to"] = W["today"]
    return out


def write(rec, doc: dict) -> None:
    common.write_json(rec / "say.json", doc, 0o600)


def load(rec):
    """The last say.json, or None. Each of its lists holds records only: a stray item is left out, so every
    reader meets the shape it writes."""
    doc = common.load_json(rec / "say.json", None)
    if not (isinstance(doc, dict) and doc.get("contract") == "say/v1"):
        return None
    for k in ("insights", "suggestions", "questions", "goals"):
        doc[k] = [x for x in doc[k] if isinstance(x, dict)] if isinstance(doc.get(k), list) else []
    return doc
