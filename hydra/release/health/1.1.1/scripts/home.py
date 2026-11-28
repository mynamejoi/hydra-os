"""Health's facts for Home: <Health's folder>/home.json, home/v3, and Health's one offer,
shared/day.json, which Home's greeting turns on.

Home draws every tile itself, from these facts: a word, one line, the 14 days behind the lead finding with the days
that prove it and one reference line, Health's first suggestion, its questions marked for Home, and a move only when
the person must do something for Health to work, such as signing a source in again. There's no snapshot to draw.

It's written from say.json at the end of each run and after each save, whole or not at all, 0600. With no say.json
yet there's nothing to write: Home draws the just-installed tile from Health's column.json alone.

Never a typed word, a key or a token: every string here is one Health's own page shows, and each passes the words
lock (words.py) first.

Standard library only, Python 3.9 or newer. Nothing here prints a value.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import common
import days as D
import meals
import say as say_file
import words
import work

PACE = {"behind": "Behind", "on": "On pace", "ahead": "Ahead", "unknown": "Can't tell yet"}
ORDER = ("behind", "missed", "unknown", "on", "ahead", "done")   # the most pressing paced goal's word leads


def readings(root, now):
    """Health's goals, read the one way Goals' page and Home read them (the kit's read_goals), or
    None when the kit can't be loaded."""
    try:
        import page  # noqa: PLC0415 (the kit's finder lives there)
        return page.load_kit(root).read_goals(str(root), today=now.astimezone().date(), app=common.ID, now=now)["goals"]
    except Exception:  # noqa: BLE001 (no kit, or one that can't read: say.json's paces stand in)
        return None


def _word(say: dict, lead: dict, root=None, now=None) -> str:
    """How the area stands in a word: Health's goals in
    hand with an entry in its own say.json, read as every other reader reads them. A goal in its first window gives no
    pace word; with all of them just started, the word is "Just started", or "Not started yet" while every one starts
    after today (v1.7); several paced goals give the first word in ORDER; with no goal, it's Health's own word for the
    day. So the tile never says a pace the goal beside it doesn't."""
    got = readings(root, now) if root is not None and now is not None else None
    if got is not None:
        mine = [r for r in got if r.get("state") != "new"]   # a new goal has no entry of Health's
        for state in ORDER:
            hit = next((r for r in mine if r.get("state") == state), None)
            if hit:
                return hit["word"]
        started = [r for r in mine if r.get("state") == "started"]
        if started:   # "Just started" once any has begun, "Not started yet" while all start after today
            return "Just started" if any(r.get("word") == "Just started" for r in started) else "Not started yet"
        return lead.get("word") or "Steady"
    paces = [g.get("pace") for g in say.get("goals") or []]
    for p in ORDER:
        if p in paces:
            return PACE[p]
    return lead.get("word") or "Steady"


def _says(card: dict, dates: list) -> list:
    """Each of the 14 days in Health's own words, for Home's line when a day is scrubbed; None for a day with nothing."""
    out = []
    for d, v in zip(dates, card["values"]):
        if v is None:
            out.append(None)
            continue
        day = f"{d:%a %b} {d.day}"
        if card["id"] == "rec":
            out.append(f"{day}: {round(v)}%")
        elif card["id"] == "workouts":
            out.append(f"{day}: {round(v)} minutes of workouts")
        elif card["id"] == "sleep":
            out.append(f"{day}: {v:.1f} hours {'in bed' if card['name'] == 'In bed' else 'of sleep'}")
        elif card["id"] == "heart":
            out.append(f"{day}: resting heart {round(v)}")
        else:
            t, half = D.clock12(D.hhmm(int(v) + 720))
            out.append(f"{day}: lights out {t} {half}")
    return out


def compose(rec, root, now: dt.datetime, move=None, W=None):
    say = say_file.load(rec)
    if say is None:
        return None
    if W is None:   # after a save, from what Health's folder holds
        W = work.build(D.load(rec), meals.load(rec), meals.owners_day(now))
    card = next(c for c in W["cards"] if c["id"] == W["lead"]["card"])
    stale = (common.parse_time(say.get("stale_after")) or now) < now
    settings = common.load_json(root / "yours" / "settings.json", {}) or {}
    first = next((s for s in say["suggestions"] if isinstance(s.get("text"), str) and isinstance(s.get("why"), str)), None)
    suggest = None
    if first and not stale and settings.get("suggestions") is not False:
        answers = str(first.get("answers") or "")   # "See why on Wellbeing" opens on the card it answers
        suggest = {"text": first["text"], "why": first["why"],
                   "link": f"{common.ID}#c-{answers[2:]}" if answers.startswith("i-") else f"{common.ID}#today"}
    questions = []
    for q in say["questions"]:   # the open ones, and one answered since its run, with only that it was answered
        if q.get("home") is True and len(questions) < 3:
            questions.append({k: q[k] for k in ("id", "kind", "text", "picks", "only", "max", "answer") if k in q})
    dates = [dt.date.fromisoformat(d) for d in W["days"]]
    picture = _picture(card, W, dates)
    word = _word(say, W["lead"], root, now)[:words.LIMITS["word"]]
    doc = {"contract": "home/v3", "id": common.ID, "state": "stale" if stale else "ok", "as_of": say["as_of"],
           "word": word, "line": card["short"][:words.LIMITS["line"]], "days": picture,
           "suggest": suggest, "questions": questions, "move": move, "dates": [],
           "week": {"word": word}, "updated_at": common.iso(now)}
    offers = _offers(W, dates)
    if offers:
        doc["offers"] = offers
    for text in [doc["word"], doc["line"]] + [x for x in picture["says"] if x] + \
            [x for o in offers for x in [o["word"], o["line"]] + [s for s in o["days"]["says"] if s]]:
        if words.problems(text, 60):
            return None
    return doc


def _picture(card: dict, W: dict, dates: list) -> dict:
    """A card's 14 days as a tile draws them. From an old export, its caption says the day they're
    counted to, as Goals says it, and the tile keeps its state."""
    caption = ""
    if W.get("old"):
        to = dt.date.fromisoformat(W["today"])
        caption = f"Counted to {to:%a %b} {to.day}."
    return {"to": W["today"], "values": card["values"], "lit": card["lit"],
            "ref": {"value": card["usual"], "label": "Usual"} if card["usual"] is not None else None,
            "label": card["label"], "caption": caption, "min": card["scale"][0], "max": card["scale"][1],
            "says": _says(card, dates)}


OFFERS = (("sleep", "sleep"), ("resting-heart", "heart"), ("lights-out", "out"))


def _offers(W: dict, dates: list) -> list:
    """Wellbeing's other findings for Home's Add a widget: sleep, resting heart and lights out, each in
    the tile's own shape, from the same cards the page draws. A card with nothing in its 14 days isn't offered."""
    out = []
    for oid, cid in OFFERS:
        card = next((c for c in W["cards"] if c["id"] == cid), None)
        if card is None or (card["today"] is None and not any(v is not None for v in card["values"][:-1])):
            continue
        fig = f"{card['fig']} {card['unit']}".strip() if card["fig"] else ""
        word = (card["moved"][:1].upper() + card["moved"][1:]) if card["moved"] else fig or "Settling in"
        out.append({"id": oid, "title": card["name"], "word": word[:words.LIMITS["word"]],
                    "line": card["short"][:words.LIMITS["line"]], "days": _picture(card, W, dates)})
    food = W.get("food") or {}
    bars = food.get("bars")
    if bars and food.get("rows"):   # meals, against that night's sleep
        n = food["rows"][1]["count"].split()[0]   # the tile's word: one to three words
        says = [None if v is None else f"{d:%a %b} {d.day}: {v:.1f} hours that night" for d, v in zip(dates, bars["values"])]
        out.append({"id": "meals", "title": "Meals", "word": f"{n} drink night{'' if n == '1' else 's'}"[:words.LIMITS["word"]],
                    "line": (food.get("lead") or food["label"])[:words.LIMITS["line"]],
                    "days": {"to": W["today"], "values": bars["values"], "lit": bars["lit"],
                             "ref": {"value": bars["ref"]["value"], "label": "Usual"} if bars.get("ref") else None,
                             "label": bars["label"], "caption": "", "min": bars["min"], "max": bars["max"], "says": says}})
    return out


def day_offer(rec, W: dict, now: dt.datetime) -> None:
    """shared/day.json: tonight's lights out and when the person woke, for Home's greeting."""
    common.folder(rec / "shared")
    common.write_json(rec / "shared" / "day.json", {"contract": "day/v1", "day": W["today"], "lights_out": W.get("plan"),
                                                    "woke": W.get("woke"), "as_of": common.iso(now)})


def build(rec, root, now: dt.datetime, move=None, W=None) -> bool:
    doc = compose(rec, root, now, move, W)
    if doc is None:
        return False
    common.write_json(rec / "home.json", doc, 0o600)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"Write {common.TITLE}'s facts for Home, from say.json.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    wrote = build(rec, common.root_of(rec), common.now(a.now))
    print("home: written" if wrote else "home: nothing to write yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
