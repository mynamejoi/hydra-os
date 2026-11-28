"""Research's run, started by Hydra-OS once a day at its scheduled time, or by `hydra run learning` (column.json's
schedule.run). It never starts Claude: the week's searches are the morning review's
(think.py), and everything here is code.

1. Read, in code: the public release notes allow.json lists (release.py), and any note dropped on the page (notes.py).
   A page that can't be read keeps its last read, and the block says so.
2. Draw, from what the folder holds: say.json, home.json with the angles offer, and the page (draw.py).
3. Write STATUS.md and one runs.jsonl line, states and counts only, then the doctor.

    python3 scripts/run.py [--record DIR] [--now ISO] [--trigger schedule|manual|test]

For tests only: LEARNING_TEST_PAGES, a folder holding <id>.txt for each allowed page, is read in place of the
network, so nothing is fetched. It prints one line, states and counts only. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import pathlib
import sys

import common
import doctor
import draw
import notes
import plan as planner
import release
import status
import store


def getter():
    folder = os.environ.get("LEARNING_TEST_PAGES")
    if not folder:
        return release.fetch
    by_url = {s["url"]: s["id"] for s in release.allowed()}

    def read(url: str) -> str:
        return (pathlib.Path(folder) / f"{by_url[url]}.txt").read_text(encoding="utf-8")
    return read


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{common.TITLE}'s run: read release notes and notes, and draw the page.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    ap.add_argument("--trigger", default="schedule", choices=["manual", "schedule", "test"])
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    if not rec.is_dir():
        print(f"run: {common.TITLE}'s folder isn't there yet. Set up Hydra-OS first.", file=sys.stderr)
        return 1
    root = common.root_of(rec)
    started = common.now(a.now)
    line = {"started_at": common.iso(started), "trigger": a.trigger, "how": "launchd" if a.trigger == "schedule" else "terminal",
            "unattended": a.trigger == "schedule", "waiting_permission": False, "denied": 0, "sources": {},
            "model": False, "mcp_servers": [], "state": "ran", "tokens": None,
            "tokens_why": "Research's searches run in the morning review"}
    if os.environ.get("HYDRA_CAUGHT_UP") == "1":
        line["caught_up"] = True
    facts = {"now": "The last run didn't finish."}
    drawn, as_of = True, None
    try:
        got = release.read(rec, started, getter=getter())
        for sid, s in store.releases(rec).items():   # read by this run: its own check reached the page, and the page answered
            line["sources"][sid] = s.get("checked_at") == common.iso(started) and s.get("ok") is True
        n = notes.read(rec, started)
        line["sources"]["notes"] = n["unread"] == 0
        later = common.now(a.now)
        drawn = draw.everything(rec, root, later, run=common.iso(started))
        as_of = later
        ps = store.all_projects(rec, root)
        p = planner.load(rec)
        facts = {"now": "Up to date." if got["failed"] == 0 else f"{got['failed']} of {got['read'] + got['failed']} release-note pages couldn't be read.",
                 "needs": [],
                 "done": [f"- Read {got['read']} release-note pages: {got['new']} new lines.",
                          f"- {len(ps)} project{'' if len(ps) == 1 else 's'}, {n['kept']} note{'' if n['kept'] == 1 else 's'} kept."]
                 + ([f"- The last scout: {len(p.get('searched') or [])} of {len(p.get('searches') or [])} searches."] if p else []),
                 "next": [f"- The next read is at {common.AT}. The next scout is Monday's morning review."]}
    except Exception:  # noqa: BLE001  (whatever went wrong, the run still writes its line, so Hydra-OS knows it ended)
        line["state"] = "failed"
    finished = common.now(a.now)
    try:
        status.write(rec, finished, as_of, facts)
    except OSError:
        line["state"] = "failed"
    line["finished_at"] = common.iso(finished)
    if not drawn:
        line["state"] = "failed"
    line["ok"] = line["state"] != "failed"
    common.append_line(rec / "runs.jsonl", line)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            doctor.main(["--record", str(rec)] + (["--now", a.now] if a.now else []))
    except Exception:  # noqa: BLE001
        pass
    read = sum(1 for v in line["sources"].values() if v)
    print(f"run: {read} of {len(line['sources'])} sources read, state {line['state']}")
    return 0 if line["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
