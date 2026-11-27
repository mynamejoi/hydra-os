"""What Goals writes in its own record, built in code from the reading (scripts/reading.py), with no model call and
no request:

    say.json    say/v1: how the goals stand, and Goals' own questions
    home.json   home/v3: the tile's word, its one line and its 14 days
    STATUS.md   states and counts only

- **No goal's words leave yours/goals.json through these.** Each names a goal by its id, and counts the rest. The
  page, Home's band and Claude's primer read the words from goals.json themselves.
- **Goals asks only what the data can't tell:** a new goal with no why, in its first week: "Why does '{goal}' matter
  to you?", on Goals' page and Home's Claude asks, the answer saved as its why. A goal past its date isn't asked
  about: its page offers a new date, which really moves it, and setting it aside. It makes no suggestion of its own:
  a goal's next move is its measuring app's.
- **A run writes the questions fresh. A save keeps them** and marks the answered ones, so an answered question stays
  in place until the next run. A save also asks a new goal's why, and drops a why that was given some other way.

Each file is written whole or not at all, mode 0600. The same files and the same --now give the same bytes.
"""
from __future__ import annotations

import datetime as dt

import byhand
import common
import goalsfile
import reading

STALE_HOURS = 26
ANSWERS = "answers.jsonl"
BLOCK = "goals"  # the block on Goals' page that its insights and questions belong to
# A new goal's why, in fixed words. {goal} stays as it is here: the
# page that draws it fills in the goal's words from goals.json, since a goal's words never leave it.
WHY_ASK = "Why does '{goal}' matter to you?"
WHY_ASK_WHY = "Its why shows with the goal on Goals' page."
NEW_DAYS = 7  # a goal is new for its first week, and is asked its why while it's new
# What got in the way, in fixed words, its {goal} as WHY_ASK's: asked of a goal behind on two reads
# running, once a stretch behind. A read is the day its app's data runs to (its entry's `to`), else the day it read.
INWAY_ASK = "What got in the way of '{goal}' lately?"
INWAY_ASK_WHY = "Your answer shows with the goal on Goals' page."
INWAY_READS = 2
INWAY_DAYS = 7
READS = ("store", "reads.json")  # each goal's last read, and how many reads running it's been behind
# The one offer, in fixed words: when a page arrives, each goal in
# hand that no page counted, set before it and fitting it, is asked once whether that page should count it. {page} is
# the page's own name; {goal} stays for the page that draws it, as WHY_ASK's does.
OFFER_ASK = "{page} can count '{goal}' now."
OFFER_WHY = "Until now it's been kept by hand."
OFFER_PICKS = ({"id": "count", "label": "Count it"}, {"id": "pass", "label": "Not this one"})
OFFER_DAYS = 14
ARRIVED = ("store", "arrived.json")  # each page's arrival and the goals it was offered, written by `act.py arrived`
OPEN_MOST = 3  # at most three questions open


def readings(root, now) -> dict:
    """{"goals": every goal's reading, in the file's order, "tally"}. Through the kit's one reading, kit.read_goals,
    when the main plugin is in reach, so Goals' tile can't disagree with the band Home draws; else through Goals' own
    copy of it (scripts/reading.py), which the tests hold equal to the kit's."""
    kit = common.load_kit(root)
    if kit is not None:
        try:
            doc, _ = goalsfile.load(root)
            order = {g["id"]: i for i, g in enumerate(doc["goals"])}
            got = kit.read_goals(str(root), today=now.date(), now=now)
            both = sorted(list(got["goals"]) + list(got["record"]), key=lambda r: order.get(r["id"], len(order)))
            return {"goals": both, "tally": got["tally"]}
        except goalsfile.Broken:
            raise
        except Exception:  # noqa: BLE001  (a kit that can't read falls back to the copy held equal to it)
            pass
    return reading.read_goals(root, now)


def plural(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def counts(readings: list) -> dict:
    """How many goals in hand are in each state."""
    hand = [r for r in readings if r["in_hand"]]
    c = {s: sum(1 for r in hand if r["state"] == s)
         for s in ("behind", "on", "ahead", "unknown", "missed", "started", "new", "done")}
    c["hand"] = len(hand)
    c["soon"] = sum(1 for r in hand if r["state"] == "started" and r["word"] == "Not started yet")  # start after today
    c["pace"] = c["on"] + c["ahead"]
    c["counted"] = c["behind"] + c["pace"] + c["unknown"] + c["missed"]
    return c


def headline(c: dict, tally: str) -> str:
    if tally:
        return tally[0].upper() + tally[1:]
    if c["started"]:
        how = "not started yet" if c["soon"] == c["started"] else "just started"
        return f"{plural(c['started'], 'goal')} {how}" + (f", {c['new']} not counted yet" if c["new"] else "")
    if c["new"]:
        return f"{plural(c['new'], 'goal')} set, not counted yet"
    return "No goals yet"


def standing(c: dict) -> str:
    """How the goals stand, in one sentence of counts."""
    parts = []
    if c["pace"]:
        parts.append(f"{c['pace']} on pace")
    if c["behind"]:
        parts.append(f"{c['behind']} behind")
    if c["missed"]:
        parts.append(f"{c['missed']} past {'its' if c['missed'] == 1 else 'their'} date")
    if c["unknown"]:
        parts.append(f"{c['unknown']} that can't be told yet")
    if c["started"] > c["soon"]:
        parts.append(f"{c['started'] - c['soon']} just started")
    if c["soon"]:
        parts.append(f"{c['soon']} not started yet")
    if c["new"]:
        parts.append(f"{c['new']} not counted yet")
    if not parts:
        return "No goal is set yet."
    said = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"Of {plural(c['hand'], 'goal')} in hand: {said}."


def last_answers(record) -> dict:
    """Each question's newest answer that wasn't taken back: {question: line}."""
    out = {}
    for line in common.lines(record / ANSWERS):
        q = line.get("question")
        if not isinstance(q, str):
            continue
        if line.get("undone"):
            out.pop(q, None)
        else:
            out[q] = line
    return out


def new_without_why(doc: dict, now) -> list:
    """The goals in hand with no why that are still new, set within NEW_DAYS days and not past their date, the first
    set first, so the one asked stays asked until it's answered or its week ends: (goal, the day its question ends)."""
    today, out = now.date(), []
    for g in doc["goals"]:
        at, by = common.parse_time((g.get("set") or {}).get("at")), common.day(g.get("by") or "")
        if g.get("status") != "active" or g.get("why") or at is None or (by is not None and by < today):
            continue
        ends = at.date() + dt.timedelta(days=NEW_DAYS)
        if at.date() <= today < ends:
            out.append((at, g, ends))
    return [(g, ends) for _, g, ends in sorted(out, key=lambda x: x[0])]


def tracked(old: dict, goals: list) -> dict:
    """Each goal's last read and how many reads running it's been behind, from the last run's: {id: {"read", "behind",
    "since"}}. A new read is a later day its app's data runs to; the same day read again changes nothing."""
    out = {}
    for r in goals:
        read = r.get("counted_to") or (r.get("as_of") or "")[:10]
        if not r.get("in_hand") or not common.day(read):
            continue  # set aside, done a while, or not read yet
        prev = old.get(r["id"]) if isinstance(old.get(r["id"]), dict) else {}
        if prev.get("read") == read:
            out[r["id"]] = prev
            continue
        n = prev.get("behind") if isinstance(prev.get("behind"), int) else 0
        if r["state"] == "behind":
            since = prev.get("since") if n and prev.get("since") else read
            out[r["id"]] = {"read": read, "behind": n + 1, "since": since}
        else:
            out[r["id"]] = {"read": read, "behind": 0}
    return out


def track(root, record, now) -> dict:
    """A run's reads: store/reads.json, written whole. Its goals' words are never in it, only their ids."""
    path = record.joinpath(*READS)
    old = common.load_json(path, None)
    old = old.get("goals") if isinstance(old, dict) and isinstance(old.get("goals"), dict) else {}
    reads = tracked(old, readings(root, now)["goals"])
    common.write_json(path, {"contract": "goal-reads/v1", "goals": reads})
    return reads


def behind_twice(record) -> dict:
    """The goals behind on two reads running, with the read their stretch began on: {id: "YYYY-MM-DD"}."""
    got = common.load_json(record.joinpath(*READS), None)
    goals = got.get("goals") if isinstance(got, dict) and isinstance(got.get("goals"), dict) else {}
    return {g: x["since"] for g, x in goals.items() if isinstance(x, dict) and isinstance(x.get("behind"), int)
            and x["behind"] >= INWAY_READS and common.day(x.get("since") or "")}


def inway_question(goal: dict, since: str, today: dt.date) -> dict:
    """What got in the way of a goal behind on two reads running, once a stretch behind: its id names the stretch."""
    return {"id": "x-%s-%s" % (goal["id"][2:], since.replace("-", "")), "kind": "words", "text": INWAY_ASK,
            "max": goalsfile.WHY_MAX, "block": BLOCK, "home": True, "why": INWAY_ASK_WHY, "goal": goal["id"],
            "ends": (today + dt.timedelta(days=INWAY_DAYS)).isoformat()}


def arrivals(record) -> dict:
    """Each page's arrival: {app: {"at", "goals": [ids it was offered]}}, as `act.py arrived` wrote it."""
    got = common.load_json(record.joinpath(*ARRIVED), None)
    apps = got.get("apps") if isinstance(got, dict) and isinstance(got.get("apps"), dict) else {}
    return {a: x for a, x in apps.items() if isinstance(x, dict) and common.parse_time(x.get("at") or "")
            and isinstance(x.get("goals"), list)}


def offer_question(goal: dict, app: str, title: str, at) -> dict:
    """The one offer for a goal, from a page that arrived at `at`, asked for OFFER_DAYS days."""
    return {"id": f"o-{goal['id'][2:]}-{app}", "kind": "one", "text": OFFER_ASK.replace("{page}", title),
            "picks": [dict(x) for x in OFFER_PICKS], "block": BLOCK, "home": True, "why": OFFER_WHY,
            "goal": goal["id"], "ends": (at.date() + dt.timedelta(days=OFFER_DAYS)).isoformat()}


def offers(doc: dict, record, root, now, answers: dict, window: bool = True) -> list:
    """The offers open now, one a goal, in goals.json's order: each goal in hand that no page counts (kept by hand, or
    with no app), offered by a page still installed that arrived within OFFER_DAYS, whose offer isn't answered.
    window False leaves the days out: a save keeps the run's offers until the next run, which alone ends them."""
    if root is None:
        return []
    import pages
    here = {p["id"]: p for p in pages.installed(root)}
    came = sorted(((common.parse_time(x["at"]), a, x) for a, x in arrivals(record).items() if a in here),
                  key=lambda t: t[0])
    out = []
    for g in doc["goals"]:
        if g.get("status") != "active" or (g.get("measured_by") or {}).get("app") not in (None, common.ID):
            continue
        for at, app, x in came:
            if g["id"] in x["goals"] and (not window or now.date() < at.date() + dt.timedelta(days=OFFER_DAYS)):
                q = offer_question(g, app, here[app]["title"], at)
                if q["id"] not in answers:
                    out.append(q)
                    break
    return out


def why_question(goal: dict, ends: dt.date) -> dict:
    """A new goal's why, in the person's own words, for Goals' page and Home's Claude asks."""
    return {"id": "w-" + goal["id"][2:], "kind": "words", "text": WHY_ASK, "max": goalsfile.WHY_MAX, "block": BLOCK,
            "home": True, "why": WHY_ASK_WHY, "goal": goal["id"], "ends": ends.isoformat()}


def asked(doc: dict, record, now, kept=None, root=None) -> list:
    """Goals' questions: a new goal's why, one goal at a time, and what got in the way of one goal
    behind on two reads running, the first in the file's order not yet answered in its stretch. A goal past
    its date isn't asked about: "Keep it, with a new date" changed nothing, so its page offers a new date and
    setting it aside instead. Then the offers of pages that arrived, as many as keep three questions open.

    kept  on a save, the questions the last write asked. A why stays while its goal is new and in hand with no why, or
          once answered, until the next run; and a new goal is asked its why by the save that sets it, so it's asked
          the day it's set. Anything else the last write asked goes.
    A run asks afresh.
    """
    answers = last_answers(record)
    new = new_without_why(doc, now)
    if kept is None:
        twice = behind_twice(record)
        way = next((q for q in (inway_question(g, twice[g["id"]], now.date()) for g in doc["goals"]
                                if g.get("status") == "active" and g["id"] in twice) if q["id"] not in answers), None)
        out = ([why_question(*new[0])] if new else []) + ([way] if way else [])
        return out + offers(doc, record, root, now, answers)[:max(0, OPEN_MOST - len(out))]
    ids = {g["id"] for g in doc["goals"]}
    active = {g["id"] for g in doc["goals"] if g.get("status") == "active"}
    way = [q for q in kept if q["id"].startswith("x-") and q.get("goal") in active]  # a save keeps the run's
    still = {g["id"] for g, _ in new}
    why = [q for q in kept if q["id"].startswith("w-") and q.get("goal") in ids
           and (q["id"] in answers or q.get("goal") in still)]
    open_why = [q for q in why if q["id"] not in answers]
    if len(open_why) > 1:  # an Undo brought one back after the next was asked: the first set stays asked alone
        order = {g["id"]: i for i, (g, _) in enumerate(new)}
        first = min(open_why, key=lambda q: order.get(q.get("goal"), len(order)))
        why = [q for q in why if q["id"] in answers or q is first]
    if new and all(q["id"] in answers for q in why):
        have = {q["id"] for q in why}
        more = next(((g, e) for g, e in new if "w-" + g["id"][2:] not in have), None)
        why += [why_question(*more)] if more else []
    out = why + way
    now_open = {q["id"] for q in offers(doc, record, root, now, answers, window=False)}
    kept_offers = [q for q in kept if q["id"].startswith("o-") and q.get("goal") in ids
                   and (q["id"] in answers or q["id"] in now_open)]  # answered, it stays until the next run
    have = {q["id"] for q in kept_offers}
    room = OPEN_MOST - len([q for q in out + kept_offers if q["id"] not in answers])
    fresh_offers = [q for q in offers(doc, record, root, now, answers) if q["id"] not in have]
    return out + kept_offers + fresh_offers[:max(0, room)]


def marked(questions: list, record) -> list:
    """The questions with each one's answer as it stands now: that words were typed, never the words."""
    answers = last_answers(record)
    out = []
    for q in questions:
        q = {k: v for k, v in q.items() if k != "answer"}
        a = answers.get(q["id"])
        if a and isinstance(a.get("at"), str) and q.get("kind") == "words" and isinstance(a.get("words"), str):
            q["answer"] = {"at": a["at"], "words": True}
        elif a and isinstance(a.get("at"), str) and q.get("kind") == "one" and isinstance(a.get("pick"), str):
            q["answer"] = {"at": a["at"], "pick": a["pick"]}
        out.append(q)
    return out


def say(root, record, now, fresh: bool) -> dict:
    """say.json. fresh: a run, which asks its questions anew; else a save, which keeps the run's."""
    doc, _ = goalsfile.load(root)
    got = readings(root, now)
    c = counts(got["goals"])
    if fresh:
        questions = asked(doc, record, now, root=root)
    else:
        old = common.load_json(record / "say.json", None)
        questions = asked(doc, record, now, kept=[
            q for q in (old.get("questions") if isinstance(old, dict) else None) or []
            if isinstance(q, dict) and isinstance(q.get("id"), str)], root=root)
    return {
        "contract": "say/v1",
        "as_of": common.iso(now),
        "stale_after": common.iso(now + dt.timedelta(hours=STALE_HOURS)),
        "headline": headline(c, got["tally"]),
        "insights": [{"id": "i-standing", "block": BLOCK, "text": standing(c)}],
        "suggestions": [],
        "questions": marked(questions, record),
        "goals": byhand.entries(root, record, doc, now.date()),  # the goals Goals keeps by hand
    }


def word(c: dict) -> str:
    """How the goals stand, in one to three words."""
    if c["behind"]:
        return f"{c['behind']} behind"
    if c["missed"]:
        return f"{c['missed']} missed"
    if c["unknown"]:
        return "Can't tell yet"
    if c["pace"]:
        return "On pace"
    if c["started"]:
        return "Not started yet" if c["soon"] == c["started"] else "Just started"
    if c["new"]:
        return "Not counted yet"
    return "No goals yet"


def line(c: dict) -> str:
    """The tile's one line, at most 60 characters, with no goal's words in it."""
    if c["behind"]:
        b = c["behind"]
        return f"{b} of {c['counted']} {'is' if b == 1 else 'are'} behind where {'its' if b == 1 else 'their'} plan has {'it' if b == 1 else 'them'}."
    if c["missed"]:
        m = c["missed"]
        return f"{plural(m, 'goal')} {'is' if m == 1 else 'are'} past {'its' if m == 1 else 'their'} date."
    if c["unknown"]:
        u = c["unknown"]
        return f"{plural(u, 'goal')} can't be told yet."
    if c["pace"]:
        if c["counted"] < c["hand"]:  # beside goals that just started or aren't measured yet
            return "Every goal with a pace is on pace."
        return "Your goal is on pace." if c["counted"] == 1 else "Every goal is on pace."
    if c["started"]:
        s = c["started"]
        if c["soon"] == s:  # none of them has started yet
            return ("Your goal hasn't" if s == c["hand"] == 1 else f"{plural(s, 'goal')} {'hasn' if s == 1 else 'haven'}'t") + \
                " started yet, so there's no pace yet."
        return ("Your goal just started" if s == c["hand"] == 1 else f"{plural(s, 'goal')} just started") + \
            ", so there's no pace yet."
    if c["new"]:
        n = c["new"]
        return f"{plural(n, 'goal')} {'waits' if n == 1 else 'wait'} to be counted."
    return "Say what you're working toward, and it shows here."


def days(readings: list, today: dt.date) -> dict:
    """The tile's 14 days ending today: how many goals moved on each, from the measuring apps' points."""
    window = [today - dt.timedelta(days=13 - i) for i in range(14)]
    moved = {d: 0 for d in window}
    for r in readings:
        if not r["in_hand"]:
            continue
        before = (r.get("start") or {}).get("value")
        for point in r["points"]:
            if not (isinstance(point, (list, tuple)) and len(point) == 2 and common.number(point[1])):
                continue
            d = common.day(point[0])
            if d in moved and point[1] != before:
                moved[d] += 1
            before = point[1]
    values = [moved[d] or None for d in window]
    lit = [i for i, v in enumerate(values) if v]
    first = common.day_words(window[0], today)
    took = (f"A goal moved on {plural(len(lit), 'day')}." if lit else "No goal has moved in them yet.")
    return {"to": today.isoformat(), "values": values, "lit": lit, "ref": None,
            "label": f"The last 14 days, {first} to today, as how many goals moved each day. {took}", "caption": ""}


def home(root, record, now, said: dict) -> dict:
    """home.json, from say.json and the same reading."""
    got = readings(root, now)
    c = counts(got["goals"])
    # Home's Claude asks: the home: true ones, open first, then one answered since the run, which keeps its answer as
    # say.json has it, never the typed words, and the goal it names
    shown = [q for q in said["questions"] if q.get("home") is True]
    open_home = [{k: q[k] for k in ("id", "kind", "text", "picks", "only", "max", "goal", "answer") if k in q}
                 for q in [q for q in shown if "answer" not in q] + [q for q in shown if "answer" in q]][:3]
    week = "behind" if c["behind"] or c["missed"] else "on pace" if c["pace"] else "quiet"
    return {
        "contract": "home/v3", "id": common.ID, "state": "ok", "as_of": said["as_of"],
        "word": word(c), "line": line(c), "days": days(got["goals"], now.date()),
        "suggest": None, "questions": open_home, "move": None, "dates": [], "week": {"word": week},
        "updated_at": common.iso(now),
    }


def clock(t: dt.datetime) -> str:
    """The clock's format, as date '+%a %b %-d, %H:%M' prints it."""
    return f"{t:%a %b} {t.day}, {t:%H:%M}"


def status(root, now, said: dict) -> str:
    """STATUS.md: states and counts only, never a goal's words."""
    got = readings(root, now)
    c = counts(got["goals"])
    m = c["missed"]  # a why can wait
    needs = (f"- {plural(m, 'goal')} past {'its' if m == 1 else 'their'} date: set a new date, or set "
             f"{'it' if m == 1 else 'them'} aside. Until then {'it stays' if m == 1 else 'each stays'} as missed."
             ) if m else "Nothing."
    return "\n".join([
        f"# STATUS: {common.TITLE}", "", f"Updated: {clock(now)}", f"As of: {clock(common.parse_time(said['as_of']))}",
        "", "## Now", "", standing(c), "", "## Needs you", "", needs, "", "## Done (with proof)", "",
        f"- Read the goals and each counting page's progress, and wrote how they stand (`say.json`, {clock(now)}).",
        "", "## Next", "", "- The next run follows the next page's run.", "", "## Signals for other pillars", "",
        "None.", ""])


def write(root, record, now, fresh: bool) -> dict:
    """say.json, then home.json, each whole. The say.json it wrote. A run first notes each goal's read."""
    before = common.load_json(record / "say.json", None)
    if fresh:
        track(root, record, now)
    said = say(root, record, now, fresh)
    common.write_json(record / "say.json", said)
    if said["goals"] or (isinstance(before, dict) and before.get("goals")):
        # a goal kept by hand is read from this say.json's own entries, so its counts come from the file just written
        said = say(root, record, now, fresh)
        common.write_json(record / "say.json", said)
    common.write_json(record / "home.json", home(root, record, now, said))
    return said


def after_save(root, record, now) -> None:
    """What a save rebuilds: say.json and home.json, keeping the run's questions, then the page."""
    write(root, record, now, fresh=False)
    import page
    page.build(root, record, now)
