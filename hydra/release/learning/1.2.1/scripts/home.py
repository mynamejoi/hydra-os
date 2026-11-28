"""Research's facts for Home: <record>/home.json, home/v3, and its one offer,
shared/angles.json, angles/v1, which Content reads.

Home draws Research's tile from these facts: a word, one line, the 14 days as what came in each day (the Monday scout's
finds and the release notes' new lines) and Research's first move as its suggestion. Research asks nothing, so it
gives no questions and no move.

Written from say.json at the end of each run, after each save and after the morning review, whole or not at all, 0600.
Never a typed word, a key or a token: a project's name stays on Research's page, and every find's words here passed
say.strict_ok first.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import common
import plan as planner
import say as say_file
import search
import store

LINE = 60
ANGLES_WEEKS = 4
ANGLES_MOST = 8
ANGLE_KINDS = ("new", "learn", "opportunities")


def state(rec, doc, now) -> str:
    if doc is None:
        return "new"
    runs = [r for r in common.read_jsonl(rec / "runs.jsonl") if r.get("started_at")]
    if runs and runs[-1].get("ok") is False and runs[-1].get("state") == "failed":
        return "failed"
    stale = common.parse_time(doc.get("stale_after"))
    return "stale" if stale and now > stale else "ok"


def days(rec, now) -> dict:
    today = now.astimezone().date()
    first = today - dt.timedelta(days=13)
    finds = [0] * 14
    lines = [0] * 14
    for f in store.finds(rec):
        t = common.parse_time(f.get("kept_at"))
        if t and first <= t.astimezone().date() <= today:
            finds[(t.astimezone().date() - first).days] += 1
    for s in store.releases(rec).values():
        for line in [x for x in s.get("lines") or [] if isinstance(x, dict)]:
            try:
                d = dt.date.fromisoformat(line.get("seen", ""))
            except ValueError:
                continue
            if first <= d <= today:
                lines[(d - first).days] += 1
    values = [finds[i] + lines[i] for i in range(14)]
    lit = [i for i in range(14) if finds[i]]
    return {"to": today.isoformat(), "values": [v if v else None for v in values], "lit": lit, "ref": None,
            "label": (f"The last 14 days, {first:%b} {first.day} to today, as what came in each day: the Monday scout's "
                      "finds and the release notes' new lines."), "caption": ""}


def word_and_line(rec, root, now, doc) -> tuple:
    ps = store.all_projects(rec, root)
    finds, _ = say_file.week_finds(rec, now)
    ok = [f for f in finds if say_file.strict_ok(" ".join([f["line"], f["move"], f["why"]]), rec, root, ps)]
    if common.review_off(root):
        return "Scout off", say_file.OFF
    if not ps:
        return "No projects yet", "Research scouts your goals and what you tell Claude."
    if not any(p.get("topics") for p in ps):
        return "No topic yet", "Tell Claude what a project is about."
    if ok:
        n = len({f["project"] for f in ok})
        line = ok[0]["line"] if len(ok[0]["line"]) <= LINE else "This week's finds are on the page."
        return f"{n} to read", line
    if not store.finds(rec) and not say_file.first_done(planner.this_week(rec, now)):
        return "Scouting soon", say_file.FIRST
    return "Quiet week", "Nothing new for your projects this week."


def compose(rec, root, now, doc) -> dict:
    st = state(rec, doc, now)
    word, line = word_and_line(rec, root, now, doc)
    sug = None
    first = next((x for x in (doc or {}).get("suggestions") or [] if isinstance(x, dict)), None)
    if first and st != "stale" and not common.review_off(root) and isinstance(first.get("text"), str) \
            and isinstance(first.get("why"), str):
        sug = {"text": first["text"], "why": first["why"], "link": f"{common.ID}#week"}
    nxt = say_file.next_scout(now)
    finds, _ = say_file.week_finds(rec, now)
    n = len(finds)
    return {"contract": "home/v3", "id": common.ID, "state": st,
            "as_of": (doc or {}).get("as_of") or common.iso(now), "word": word, "line": line, "days": days(rec, now),
            "suggest": sug, "questions": [], "move": None,
            "dates": [{"day": nxt.isoformat(), "label": "Monday scout", "kind": "read"}],
            "week": {"word": "quiet" if n == 0 else "steady" if n <= 3 else "busy"},
            "updated_at": common.iso(now)}


def angles(rec, root, now) -> dict:
    """angles/1: the kept finds of the last four weeks on what's new, learn or opportunities, at most eight,
    newest first, each its general topic and never its project, its checked line and its https source."""
    ps = store.all_projects(rec, root)
    names = search.topics(search.load())
    first = (planner.week_of(now.astimezone().date()) - dt.timedelta(weeks=ANGLES_WEEKS - 1)).isoformat()
    out = []
    for f in sorted(store.finds(rec), key=lambda f: f.get("kept_at", ""), reverse=True):
        if f.get("question") not in ANGLE_KINDS or str(f.get("week", "")) < first or f.get("topic") not in names:
            continue
        src = next((s for s in f.get("sources") or [] if isinstance(s, dict) and str(s.get("url", "")).startswith("https://")), None)
        if src is None or not say_file.strict_ok(f["line"], rec, root, ps):
            continue
        out.append({"id": f["id"], "topic": names[f["topic"]], "kind": f["question"], "line": f["line"],
                    "source": {"url": src["url"], "site": src.get("site", "")}})
        if len(out) >= ANGLES_MOST:
            break
    return {"contract": "angles/v1", "as_of": common.iso(now), "stale_after": common.iso(now + dt.timedelta(days=14)),
            "angles": out}


def build(rec, root, now, doc) -> dict:
    h = compose(rec, root, now, doc)
    common.write_json(rec / "home.json", h)
    common.folder(rec / "shared")
    common.write_json(rec / "shared" / "angles.json", angles(rec, root, now))
    return h


def main(argv=None) -> int:
    """home.json and the angles offer again, from say.json as it is now."""
    ap = argparse.ArgumentParser(description=f"Write {common.TITLE}'s facts for Home from its say.json.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    if not rec.is_dir():
        print(f"home: {common.TITLE}'s folder isn't there yet.", file=sys.stderr)
        return 1
    h = build(rec, common.root_of(rec), common.now(a.now), say_file.load(rec))
    print(f"home: wrote home.json ({h['state']}) and the angles offer ({len(common.load_json(rec / 'shared' / 'angles.json', {}).get('angles') or [])} angles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
