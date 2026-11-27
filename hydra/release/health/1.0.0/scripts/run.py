#!/usr/bin/env python3
"""Health's run, started by Hydra-OS once a day at its scheduled time, or by `hydra run health` (column.json's
schedule.run). In six steps:

1. Sources. <root> comes from HYDRA_ROOT and hydra/config.json, then Health's entries in <root>/yours/sources.json.
   No device is assumed: Health reads only a source the person chose that its own column.json declares. With none
   chosen it writes no say.json, so the page stays just installed, and it makes no call.
2. Read, in code, with no model: the files the person dropped on Health's page, in inbox/ (upload.py): Apple
   Health's export (apple.py), or a file of days. Each gives the shape's rows, kept in store/days.jsonl. A source
   that can't be read is said in an insight, never skipped, and an export whose newest day is before yesterday says
   it's a snapshot.
3. Work it out in code (work.py, goals.py): the 14 days, each usual, the days that prove a finding, tonight's lights
   out, and each goal's progress.
4. Claude's part is the morning review's, never the run's: the tick never starts a run that needs Claude. Each morning
   the person said yes to, the "Hydra-OS morning review" task gives Claude the figures through think.py, which keeps what passes Health's checks in store/judged.json.
5. Show what of it still holds (judge.standing): its questions, and its headline and suggestions on the day it wrote
   them for the same last day read, each checked again against the new figures, and nothing while the review is
   off. Every other line is the one worked out in code, and every line passes the words lock (words.py).
6. Write, each file whole or not at all: say.json, home.json and Health's offer, the page with its datasets and
   summary, drawn by Hydra-OS's kit (page.py), STATUS.md, and one runs.jsonl line with its state and its tokens.

    python3 scripts/run.py [--record DIR] [--now ISO] [--trigger schedule|manual|test]

It prints one line, states and counts only, never a reading. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import os
import sys

import answers as answer_log
import common
import days
import doctor
import goals
import home
import judge
import meals
import page
import say
import sources
import status
import upload
import work


def read_sources(rec, root, now) -> dict:
    """Step 2. {"lists": [rows, ...], "tried": {id: answered}, "notes": [(text, why)], "state", "move", "reads": n}, and
    "came", the day the newest file came in, for a file source."""
    reads, waits = sources.chosen(root)
    out = {"lists": [], "tried": {}, "notes": [], "state": "ran", "why": "", "move": None, "reads": len(reads), "waits": len(waits)}
    for e in reads:
        sid, name = e["id"], e["source"]
        if sid in out["tried"]:
            continue   # two entries for one declared source are read once
        if sid == upload.SOURCE:
            rows, c = upload.read(rec)
            out["lists"].append(rows)
            out["came"] = c.get("came")   # the day the newest file came in: an export is a snapshot to it
            out["tried"][sid] = bool(rows)
            if not c["files"]:
                out["notes"].append(("No export has come in yet.", f"Drop your Apple Health export on the {common.TITLE} page."))
            elif c["unread"]:
                out["notes"].append((f"{c['unread']} of {c['files']} files you added couldn't be read.",
                                     f"{common.TITLE} reads Apple Health's export, or a .csv or .json with a day in each row."))
            newest = goals.last_day({r["day"]: r for r in rows}, meals.owners_day(now), c.get("came")) if rows else None
            if newest is not None and newest < meals.owners_day(now) - dt.timedelta(days=1):
                out["notes"].append((f"The newest day in your export is {newest:%a %b} {newest.day}.",
                                     "An export is a snapshot, so new days need another export."))
    for e in waits:
        out["notes"].append((f"{common.TITLE} can't read {e['source']} yet.", "For now it reads your Apple Health export, or a file of days."))
    return out


def draw(rec, root, now, run_id: str, W=None, move=None) -> bool:
    """The page, by Hydra-OS's kit. False when it couldn't be drawn, which the run's line says."""
    try:
        page.build(rec, root, now, run_id, W=W, move=move or "")   # whole, so the kit adds its button
        return True
    except (page.NoKit, ValueError, OSError, KeyError):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{common.TITLE}'s run: read the chosen source, work it out, and write the page's facts.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    ap.add_argument("--trigger", default="schedule", choices=["manual", "schedule", "test"])
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    root = common.root_of(rec)
    if not rec.is_dir():
        print(f"run: {common.TITLE}'s folder isn't there yet. Set up Hydra-OS first.", file=sys.stderr)
        return 1
    started = common.now(a.now)
    at = str((common.MANIFEST.get("schedule") or {}).get("at") or "07:40")
    if upload.waiting(rec):   # for the minutes the read takes, the page says it's reading
        try:
            page.build(rec, root, started, common.iso(started), reading=True)
        except Exception:  # noqa: BLE001 (the read goes on, and its own page follows)
            pass
    got = read_sources(rec, root, started)
    line = {"started_at": common.iso(started), "trigger": a.trigger, "how": "launchd" if a.trigger == "schedule" else "terminal",
            "unattended": a.trigger == "schedule", "waiting_permission": False, "denied": 0, "sources": got["tried"],
            "model": False, "mcp_servers": [], "state": got["state"], "tokens": None}
    if os.environ.get("HYDRA_CAUGHT_UP") == "1":
        line["caught_up"] = True   # Hydra-OS started it late, after this Mac was off or asleep; only it can tell
    if got["why"]:
        line["why"] = got["why"]   # why it waits, in words Hydra-OS can show as they are
    as_of, drawn, facts = None, True, {"now": "The last read didn't finish."}
    try:
        before = say.load(rec)
        facts = {"next": [f"- The next read is at {at}."]}
        if not got["reads"]:
            # nothing chosen that Health can read: no say.json, so the page stays just installed
            line["tokens_why"] = "no source is chosen yet"
            facts.update(now="Waiting for a source.", needs=[f"- Drop your Apple Health export on the {common.TITLE} page."])
            as_of = None
            drawn = draw(rec, root, started, common.iso(started))
        else:
            rows = days.merge(*got["lists"])
            days.save(rec, rows)
            read_ok = any(got["tried"].values())
            as_of = started if read_ok or before is None else (common.parse_time(before.get("as_of")) or started)
            today = meals.owners_day(started)
            log = meals.load(rec)
            W = work.build(rows, log, goals.last_day(rows, today, got.get("came")) or today, today,   # the last day read
                           kinds=goals.kinds(root))
            mine = goals.build(root, rows, today, common.iso(as_of), read=bool(rows), came=got.get("came"))
            if W["old"] and not got["move"]:   # the old-export line, under the page's crumb and on Home's tile
                ends = dt.date.fromisoformat(W["today"])   # the last day read, as everything has it
                got["move"] = {"text": f"Your Health data ends {ends:%a %b} {ends.day}.", "urgency": "week", "link": f"{common.ID}#drop"}
            handed, answered, done = answer_log.handed(rec, before)
            open_before = [q["text"] for q in (before or {}).get("questions") or [] if isinstance(q, dict) and "answer" not in q]
            figs = judge.figures(W, mine, handed, open_before)
            # Claude's part is the morning review's (think.py): what it last wrote that still holds stands, and while
            # the review is off, nothing of it, nor an answer waiting for a review that won't come
            off = judge.review_off(root)
            last = common.load_json(rec / "store" / "judged.json", {}) or {}
            kept = judge.standing(last, W, figs, {g["id"] for g in mine}, today, off)
            answered = [] if off else answered
            line["tokens_why"] = "Claude's part runs in the morning review" if W["have"] else "nothing has come in to read yet"
            doc = say.compose(W, kept, mine, as_of, at, got["notes"], answered, done)
            say.write(rec, doc)
            later = common.now(a.now)
            home.day_offer(rec, W, later)
            home.build(rec, root, later, got["move"], W=W)
            drawn = draw(rec, root, later, common.iso(started), W, got["move"])
            facts.update(now="Up to date." if read_ok else "The last read didn't come in.",
                         needs=["- Sign your source in again, in Claude."] if got["state"] == "waiting" else [],
                         done=[f"- Read {sum(1 for v in got['tried'].values() if v)} of {len(got['tried'])} "
                               f"source{'' if len(got['tried']) == 1 else 's'}: {len(rows)} day{'' if len(rows) == 1 else 's'} kept."])
    except Exception:  # noqa: BLE001 (whatever went wrong, the run still writes its line, so Hydra-OS knows it ended)
        line["state"] = "failed"
    finished = common.now(a.now)
    try:
        status.write(rec, finished, as_of, facts)
    except OSError:
        line["state"] = "failed"
    line["finished_at"] = common.iso(finished)
    if not drawn:
        line["state"] = "failed"   # the page couldn't be drawn; everything else was written
    line["ok"] = line["state"] != "failed"
    common.append_line(rec / "runs.jsonl", line)
    try:   # the doctor last, after STATUS.md, the page and the run's line
        with contextlib.redirect_stdout(io.StringIO()):
            doctor.main(["--record", str(rec)] + (["--now", a.now] if a.now else []))
    except Exception:  # noqa: BLE001 (the doctor's own trouble never undoes a run)
        pass
    print(f"run: {sum(1 for v in got['tried'].values() if v)} of {len(got['tried'])} sources read, state {line['state']}")
    return 0 if line["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
