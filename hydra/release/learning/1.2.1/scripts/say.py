"""What Research concluded: <record>/say.json, say/v1, written whole, mode 0600. The page,
Home's tile, the summary and the morning review's next ask read this one file.

- **headline and insights:** this week's lead find, or the plain state when there's none: the first scout's day, nothing
  new, a scout that couldn't search, no project yet, no topic yet, or the morning review off. One insight a block,
  never a count of Research's work. The week's is the header's, since the page leads there, and This week's rows
  already hold each find whole. Your projects' says how many projects have no general topic yet, when any.
- **suggestions:** a move a project, from this week's finds, at most three, each with its why. Never a button. The first
  is the header's move (page.py), and Home's tile's suggestion.
- **questions:** [], since Research asks nothing: its projects come from the person's goals and from what they tell
  Claude, and each project's topic from its own words or from Claude.
- **goals:** [], since Research counts no goal (fits null).

Typed words never go in this file: a find's words come here only when they hold no project's name, no word of one that
isn't a shipped word, and no note's title. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt

import common
import plan as planner
import search
import store

QN = {"learn": "Learn", "sell": "Sell", "new": "What's new", "opportunities": "Opportunities", "gaps": "Gaps",
      "skills": "Claude skills"}
STALE_HOURS = 26
# The plain states (plain, one idea a line, no exclamation marks, no "please", "just" or "simply"), and the line
# each shows under it on the page
FIRST = "Your first scout runs at the next morning review."   # any day: the first review after a project has a topic
NAME_ONE = "No projects yet."
OFF = "Research fills in once the morning review is back on."
NOTHING = "Nothing new for your projects this week."
COULDNT = "This week's scout couldn't search."
NO_TOPIC = "No general topic matches your projects yet."
NEXT = {FIRST: "One move for each project lands here.",
        NAME_ONE: "Your goals and the projects you tell Claude about show here.",
        NOTHING: "The next scout is Monday morning.", COULDNT: "It tries again tomorrow morning.",
        NO_TOPIC: "Tell Claude what one is about, and it picks the closest topic."}


def next_scout(now) -> dt.date:
    today = now.astimezone().date()
    return planner.week_of(today) + dt.timedelta(days=7)


def strict_ok(text: str, rec, root, ps: list) -> bool:
    """Whether a find's words may go into say.json, home.json or the shared file: no word of the person's name or city,
    no project's name, no word of a project's name that isn't a shipped word, and no note's title."""
    doc = search.load()
    allowed = search.shipped(doc)
    ws = search.words_of(text)
    strong, _ = search.own_words(root, rec)
    if any(w in strong for w in ws):
        return False
    joined = " " + " ".join(ws) + " "
    for p in ps:
        name = search.words_of(p.get("name", ""))
        if name and f" {' '.join(name)} " in joined:
            return False
        if any(len(w) >= 4 and w not in allowed and w in ws for w in name):
            return False
    for n in store.notes(rec):
        t = " ".join(search.words_of(n.get("title", "")))
        if t and f" {t} " in joined:
            return False
    return True


def week_finds(rec, now) -> tuple:
    """(the finds of the newest scout, this week's or else last week's, and its week), the best sourced first."""
    fs = store.finds(rec)
    for week in (planner.week_of(now.astimezone().date()), planner.week_of(now.astimezone().date()) - dt.timedelta(days=7)):
        got = [f for f in fs if f.get("week") == week.isoformat()]
        if got:
            got.sort(key=lambda f: (-len(f.get("sources") or []), f.get("kept_at", "")))
            return got, week
    return [], None


def first_done(p) -> bool:
    """Whether this week's scout has searched, so a first scout is no longer to come."""
    return bool(p and p.get("done") and p.get("searched"))


def state_line(rec, root, now, ps: list, finds: list) -> str:
    if common.review_off(root):
        return OFF
    if not ps:
        return NAME_ONE
    if not any(p.get("topics") for p in ps):
        return NO_TOPIC
    p = planner.this_week(rec, now)
    if p and p.get("done") and p.get("searches") and not p.get("searched"):
        return COULDNT
    if not store.finds(rec) and not first_done(p):
        return FIRST
    return NOTHING if not finds else ""


def untopiced(ps: list) -> str:
    """Your projects' line when some of them have no general topic yet, else ""."""
    n = sum(1 for p in ps if not p.get("topics"))
    if not n or n == len(ps):
        return ""   # with none topical, the header says it
    if n == 1:
        return "One project has no general topic yet, so it isn't scouted. Tell Claude what it's about."
    return f"{n} projects have no general topic yet, so they aren't scouted. Tell Claude what each is about."


def compose(rec, root, now) -> dict:
    """say.json from the store."""
    ps = store.all_projects(rec, root)
    finds, week = week_finds(rec, now)
    state = state_line(rec, root, now, ps, finds)
    ok = [f for f in finds if strict_ok(" ".join([f["line"], f["move"], f["why"]]), rec, root, ps)]
    lead = ok[0] if ok else None
    headline = (lead["move"] if lead else state or "A quiet week for your projects.")[:90]
    # the page's conclusion is its header's (every page leads in one place), so This
    # week shows its rows alone: the lead's line and move are already its first row
    insights = [{"id": "i-week", "block": "header", "text": (lead["line"] if lead else state or NOTHING)[:120]}]
    if untopiced(ps):
        insights.append({"id": "i-projects", "block": "projects", "text": untopiced(ps)})
    nxt = next_scout(now)
    suggestions = []
    seen = set()
    for f in ok:
        if f["project"] in seen or len(suggestions) >= 3:
            continue
        seen.add(f["project"])
        suggestions.append({"id": f"s-{f['id'][2:]}", "text": f["move"][:120], "why": f["why"][:140], "answers": "i-week",
                            "kind": "model"})
    return {"contract": "say/v1", "as_of": common.iso(now),
            "stale_after": common.iso(now + dt.timedelta(hours=STALE_HOURS)), "headline": headline,
            "measure": {"label": "Next scout", "value": f"{nxt:%a %b} {nxt.day}", "note": "every Monday morning"},
            "insights": insights, "suggestions": [] if common.review_off(root) else suggestions,
            "questions": [], "goals": []}


def write(rec, doc: dict) -> None:
    common.write_json(rec / "say.json", doc)


def load(rec):
    doc = common.load_json(rec / "say.json", None)
    return doc if isinstance(doc, dict) and doc.get("contract") == "say/v1" else None
