"""The week's scout, planned in code: which projects, which of the six questions, and
the exact queries, at most 6, each written by search.py from Research's shipped words and checked before it's listed.

- **When:** once a week, at the first morning review of the week (Monday's, or the next one when Monday's didn't run).
  A scout that couldn't search gets one catch-up the next morning, with only its missing searches.
- **Which projects:** three a week, two searches each, from those with a general topic: the ones searched longest ago
  first, so each gets its turn however many there are. A project whose searches would all be held gives its place to
  the next. A project with no topic yet is never searched for: its row on the page says so instead.
- **Which questions:** what's new every week, and one more that comes round in turn (learn, sell, opportunities, gaps,
  Claude skills), so each is asked about every five weeks.
- **Kept** in <record>/think/plan.json, out of what Claude sees: which project, topic and question each search serves,
  and the week each project was last searched for, which the next week's plan reads.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import common
import search
import store

THINK = "think"
PLAN = "plan.json"
MOST = 6
A_WEEK = 3   # projects scouted a week, two searches each
TURN = ("learn", "sell", "opportunities", "gaps", "skills")


def week_of(day: dt.date) -> dt.date:
    """The Monday a day's week starts on."""
    return day - dt.timedelta(days=day.weekday())


def load(rec: pathlib.Path) -> dict:
    doc = common.load_json(rec / THINK / PLAN, {}) or {}
    if not isinstance(doc, dict) or doc.get("contract") != "research-plan/v1":
        return {}
    doc["searches"] = [s for s in doc.get("searches") or [] if isinstance(s, dict) and isinstance(s.get("id"), str)]
    return doc


def save(rec: pathlib.Path, doc: dict) -> None:
    common.folder(rec / THINK)
    common.write_json(rec / THINK / PLAN, doc)


def last_scouted(rec: pathlib.Path, old: dict) -> dict:
    """{project id: the newest week it was searched for}: what the plan before this one carried, then that plan's own
    searches that ran, then the weeks finds were kept for, which a record from before plans carried it holds."""
    out = {k: v for k, v in (old.get("last") or {}).items() if isinstance(k, str) and isinstance(v, str)} \
        if isinstance(old.get("last"), dict) else {}
    ran, week = set(old.get("searched") or []), str(old.get("week") or "")
    for s in old.get("searches") or []:
        if s.get("id") in ran and isinstance(s.get("project"), str) and week > out.get(s["project"], ""):
            out[s["project"]] = week
    for f in store.finds(rec):
        p, w = f.get("project"), str(f.get("week") or "")
        if isinstance(p, str) and w > out.get(p, ""):
            out[p] = w
    return out


def make(rec: pathlib.Path, root: pathlib.Path, now) -> dict:
    """This week's plan, written whole: {"contract", "week", "made_at", "searches": [...], "held": n, "done": False,
    "caught_up", "last"}."""
    today = now.astimezone().date()
    week = week_of(today)
    doc = search.load()
    phrases = doc["phrases"]
    names = search.topics(doc)
    own = search.own_words(root, rec)
    turn = TURN[(week.toordinal() // 7) % len(TURN)]
    every = store.all_projects(rec, root)
    last = last_scouted(rec, load(rec))   # the plan on file is an earlier week's: make runs when this week has none
    ps = [p for p in every if p.get("topics")]
    ps.sort(key=lambda p: (last.get(p["id"], ""), p.get("added", ""), p["id"]))
    searches, held, chosen = [], 0, 0
    for p in ps:
        if chosen >= A_WEEK or len(searches) >= MOST:
            break
        got = []
        for q in ("new", turn):
            tid = next((t for t in p["topics"] if t in names), None)
            if tid is None:
                continue
            if q == turn and p["topics"].index(tid) == 0 and len(p["topics"]) > 1:
                tid = p["topics"][1] if p["topics"][1] in names else tid   # a second topic takes the turn's question
            options = phrases.get(q) or []
            if not options:
                continue
            text = search.query(options[(week.toordinal() // 7) % len(options)], names[tid], today)
            if search.problem(text, doc, own, today.year):
                held += 1
                continue
            got.append((q, tid, text))
        if got:
            chosen += 1
            for q, tid, text in got[:MOST - len(searches)]:
                searches.append({"id": f"s{len(searches) + 1:02d}", "query": text, "project": p["id"], "topic": tid,
                                 "question": q})
    ids = {p["id"] for p in every}
    plan = {"contract": "research-plan/v1", "week": week.isoformat(), "made_at": common.iso(now), "searches": searches,
            "held": held, "done": False, "caught_up": "", "last": {k: v for k, v in sorted(last.items()) if k in ids}}
    save(rec, plan)
    return plan


def this_week(rec: pathlib.Path, now) -> dict:
    """This week's plan, or {} when none was made this week."""
    p = load(rec)
    return p if p.get("week") == week_of(now.astimezone().date()).isoformat() else {}
