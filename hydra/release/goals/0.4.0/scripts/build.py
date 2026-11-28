"""What Goals writes in its own record, built in code from the reading (scripts/reading.py), with no model call and
no request:

    say.json    say/v1: how the goals stand, which page took goals kept by hand when it arrived, which page gave its
                goals back to be kept by hand when it was removed, and the day's check-in (scripts/checkin.py)
    home.json   home/v3: the tile's word, its one line, its 14 days, and the day's check-in while it's open
    STATUS.md   states and counts only

- **No goal's words leave yours/goals.json through these.** Each names a goal by its id, and counts the rest. The
  page, Home's band and Claude's primer read the words from goals.json themselves.
- **Goals asks nothing.** A goal past its date has its page's own quiet choice, a new date or setting it aside,
  which nothing waits on. It makes no suggestion of its own: a goal's next move is its measuring app's.

Each file is written whole or not at all, mode 0600. The same files and the same --now give the same bytes.
"""
from __future__ import annotations

import datetime as dt

import byhand
import checkin
import common
import goalsfile
import reading

STALE_HOURS = 26
BLOCK = "goals"  # the block on Goals' page that its insights belong to
ARRIVED = ("store", "arrived.json")  # each page's arrival and the goals it took, written by `act.py arrived`
ARRIVED_DAYS = 14  # how long Goals' page says a page that arrived counts goals kept by hand till then
LEFT = ("store", "left.json")  # each page removed, its name and the goals it gave back, written by `act.py left`


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


def arrivals(record) -> dict:
    """Each page's arrival: {app: {"at", "goals": [ids it took]}}, as `act.py arrived` wrote it."""
    got = common.load_json(record.joinpath(*ARRIVED), None)
    apps = got.get("apps") if isinstance(got, dict) and isinstance(got.get("apps"), dict) else {}
    return {a: x for a, x in apps.items() if isinstance(x, dict) and common.parse_time(x.get("at") or "")
            and isinstance(x.get("goals"), list)}


def arrived_lines(root, record, now) -> list:
    """For ARRIVED_DAYS after a page arrived and took goals kept by hand till then, one line that says so: "Wellbeing
    now counts 2 of your goals." Its goals' words stay in goals.json."""
    import pages
    here = {p["id"]: p for p in pages.installed(root)}
    out = []
    for app, x in sorted(arrivals(record).items(), key=lambda kv: kv[1]["at"]):
        at = common.parse_time(x["at"])
        if app in here and x["goals"] and now.date() < at.date() + dt.timedelta(days=ARRIVED_DAYS):
            n = len(x["goals"])
            out.append({"id": f"i-arrived-{app}", "block": BLOCK,
                        "text": f"{here[app]['title']} now counts {n} of your goals." if n > 1 else
                        f"{here[app]['title']} now counts one of your goals."})
    return out


def leavings(record) -> dict:
    """Each page's removal: {app: {"at", "goals": [ids it gave back], "title"}}, as `act.py left` wrote it."""
    got = common.load_json(record.joinpath(*LEFT), None)
    apps = got.get("apps") if isinstance(got, dict) and isinstance(got.get("apps"), dict) else {}
    return {a: x for a, x in apps.items() if isinstance(x, dict) and common.parse_time(x.get("at") or "")
            and isinstance(x.get("goals"), list) and isinstance(x.get("title"), str) and x["title"].strip()}


def left_lines(root, record, now) -> list:
    """For ARRIVED_DAYS after a page was removed and gave back goals it counted, one line that says so: "Finance was
    removed, so 2 of your goals are kept by hand now." None while that page is installed again."""
    import pages
    here = {p["id"] for p in pages.installed(root)}
    out = []
    for app, x in sorted(leavings(record).items(), key=lambda kv: kv[1]["at"]):
        at = common.parse_time(x["at"])
        if app not in here and x["goals"] and now.date() < at.date() + dt.timedelta(days=ARRIVED_DAYS):
            n, title = len(x["goals"]), x["title"].strip()
            out.append({"id": f"i-left-{app}", "block": BLOCK,
                        "text": f"{title} was removed, so {n} of your goals are kept by hand now." if n > 1 else
                        f"{title} was removed, so one of your goals is kept by hand now."})
    return out


def say(root, record, now) -> dict:
    """say.json: how the goals stand, each page that arrived and took goals kept by hand, and each page removed
    that gave its goals back to be kept by hand, and the day's check-in, Goals' one question."""
    doc, _ = goalsfile.load(root)
    got = readings(root, now)
    c = counts(got["goals"])
    return {
        "contract": "say/v1",
        "as_of": common.iso(now),
        "stale_after": common.iso(now + dt.timedelta(hours=STALE_HOURS)),
        "headline": headline(c, got["tally"]),
        "insights": [{"id": "i-standing", "block": BLOCK, "text": standing(c)}] + arrived_lines(root, record, now)
                    + left_lines(root, record, now),
        "suggestions": [],
        "questions": [q for q in (checkin.question(doc, record, now),) if q],  # open, or answered today
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
    week = "behind" if c["behind"] or c["missed"] else "on pace" if c["pace"] else "quiet"
    return {
        "contract": "home/v3", "id": common.ID, "state": "ok", "as_of": said["as_of"],
        "word": word(c), "line": line(c), "days": days(got["goals"], now.date()),
        "suggest": None, "questions": checkin.for_home(next(iter(said.get("questions") or []), None)), "move": None, "dates": [], "week": {"word": week},
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


def write(root, record, now) -> dict:
    """say.json, then home.json, each whole. The say.json it wrote."""
    before = common.load_json(record / "say.json", None)
    said = say(root, record, now)
    common.write_json(record / "say.json", said)
    if said["goals"] or (isinstance(before, dict) and before.get("goals")):
        # a goal kept by hand is read from this say.json's own entries, so its counts come from the file just written
        said = say(root, record, now)
        common.write_json(record / "say.json", said)
    common.write_json(record / "home.json", home(root, record, now, said))
    return said


def after_save(root, record, now) -> None:
    """What a save rebuilds: say.json and home.json, then the page."""
    write(root, record, now)
    import page
    page.build(root, record, now)
