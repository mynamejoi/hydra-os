#!/usr/bin/env python3
"""Health's page: one page, a list of blocks, drawn by Hydra-OS's own kit. This script works
Health's datasets out in code and hands them to the kit, which draws the page from layout.json and say.json and writes
page/data/, page/index.html and page/summary.json. It makes no model call and no request.

    python3 scripts/page.py [--record DIR] [--now ISO] [--run ISO|by-hand]

Setup runs it once, so the page is there before the first read, and Hydra-OS's server runs it again when the page is
older than its facts. The daily run and each save call build() themselves.

- Just installed is whenever there's no say.json. Nothing made up shows: Today's readings is its symbol, one line and
  the place to drop the export (`action: "drop"`, drawn by Hydra-OS's kit), so the export never goes through Claude's
  chat. Claude gives the three steps to it in the chat. A source other than a file, once chosen and before the first
  read, says it's connected and when it fills in.
- Loaded: the goals band, then Today's readings, each a figure, its line and its 14 days against the person's usual,
  then Claude asks and Connections. A reading the source doesn't give is left out.
- Food and drink: "Log a meal" at its top, then the meals on the same 14 days against that night's sleep.
  Its dataset is built whenever layout.json has the block.

It prints one line, a path and counts only. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import os
import sys

import common
import days
import goals
import meals
import say as say_file
import sources
import upload
import work

ICONS = {"rec": "pulse", "workouts": "trend", "sleep": "zzz", "heart": "heart", "out": "bed"}
# the ways in someone can finish on their first day: Apple Health's own export,
# or a file of days.
LINE = "Your sleep, bedtime, resting heart and workouts, each against your usual."   # the page's line under its title
# the export's three steps, as Claude gives them in the chat; the page itself never shows them
STEPS = ["On your iPhone, open the Health app, tap your picture, then Export All Health Data.", "AirDrop it to this Mac.",
         "Drop it here, or choose it."]
SNAPSHOT = "An export is a snapshot, so new days need another export."
DROP = "Drop your export here."                      # the app's line in its drop place; column.json's tip points to it
AGAIN = "Drop a newer export here for new days."      # the drop place in Connections, once the readings are in
FRESH = "Drop a fresh export here."                   # and once the newest day is before yesterday
# Read, but with no sleep or heart rate in the days it gave (an iPhone with no watch, or a spreadsheet of workouts):
# the page says so, rather than the first visit's steps and its promise.
NOTHING = "Nothing to show yet: what you added has no sleep or heart rate."
# A file dropped and still being read, for the minutes the read takes
READING = {"icon": "pulse", "line": "Reading your file…", "via": "Your sleep shows here in a few minutes."}   # every page's phrase, as Home's tile says it
WHERE = ("An Apple Watch, or another device that saves them to the Health app, adds them. "
         "In a spreadsheet, add Sleep and Resting heart rate columns.")
EXTERNAL = [{"service": "Apple Health", "icon": "watch",   # as the row reads once the export is in, from its source's reads
             "what": "sleep, resting heart and workouts, from its export"},
            # a file of days as upload.py reads it: its own plain column names, a row for each day
            {"service": "A file", "icon": "file", "what": "a file of days from another sleep tracker"}]
NEVER = f"{common.TITLE} never gives a diagnosis, medical advice or a diet plan."   # wellness only
FOOD_EMPTY = {"icon": "plate", "line": "The meals you log line up here against that night's sleep.",
              "via": "Log a meal above. Patterns show after about a week."}
MEAL = {"label": "Log a meal", "placeholder": "Dinner at 6:30, salmon and greens, then Return"}


class NoKit(Exception):
    """Hydra-OS's kit isn't where a page can load it."""


def load_kit(root):
    """Hydra-OS's kit, by its path: $HYDRA_KIT, else $HYDRA_PLUGINS/hydra/kit, else the main app's own folder."""
    folder = os.environ.get("HYDRA_KIT")
    if not folder and os.environ.get("HYDRA_PLUGINS"):
        folder = os.path.join(os.environ["HYDRA_PLUGINS"], "hydra", "kit")
    if not folder:
        scripts = common.main_scripts(root)
        folder = str(scripts.parent / "kit") if scripts else ""
    path = os.path.join(folder, "kit.py") if folder else ""
    if not path or not os.path.isfile(path):
        raise NoKit("Hydra-OS's kit wasn't found")
    spec = importlib.util.spec_from_file_location("hydra_kit", path)
    kit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kit)
    return kit


def clock_at(at: str) -> str:
    t, half = days.clock12(at)
    return f"{t} {half}" if t else at


def empty(reads: list, W=None) -> dict:
    """Today's readings with nothing to show: before anything is read, the place to drop the export alone, which the
    tip in column.json points to on the first visit (Claude gives the steps in the chat); once days in the window are
    read with no sleep or heart rate in them, what adds those, and the place to drop a newer one; or, once a source
    other than a file is chosen, when it fills."""
    if not reads or reads[0].get("id") == "upload":
        if W and (W.get("counts") or {}).get("window") and not W.get("have"):
            return {"icon": "pulse", "line": NOTHING, "action": "drop", "drop": FRESH if W.get("old") else AGAIN, "via": WHERE}
        return {"icon": "pulse", "line": LINE, "action": "drop", "drop": DROP}
    at = clock_at(str((common.MANIFEST.get("schedule") or {}).get("at") or "07:40"))
    name = reads[0]["source"]
    return {"icon": "pulse", "line": f"{name} is connected. Your readings fill in at the first read.",
            "via": f"Say yes when Claude offers to fill it in now, or it fills in at {at}."}


def where(W: dict, ran: str = "", apple: bool = True) -> dict:
    """"Where this comes from": one row each, drawn as written,
    the last day read on the source that gave it, and at the foot when it was read, then the wellness line. Before any
    read there's no run line."""
    read = bool((W.get("counts") or {}).get("days"))
    to = ""
    if read:
        d = dt.date.fromisoformat(W["today"])
        to = f", to {d:%a %b} {d.day}"
    rows = [{"line": "Apple Health: sleep, resting heart and workouts" + (to if apple and to else ", from its export"), "icon": "heart"},
            {"line": "A file: a file of days from another sleep tracker" + (to if to and not apple else ""), "icon": "file"},
            {"line": "Your meals, logged here", "icon": "plate"},
            {"line": "Your answers to Claude asks", "icon": "pencil"}]
    t = common.parse_time(ran) if read and ran else None
    when = f"Read {t:%a %b} {t.day} at {' '.join(days.clock12(f'{t:%H:%M}'))}. " if t else ""
    return {"title": "Where this comes from", "rows": rows, "foot": when + NEVER, "drop": FRESH if W.get("old") else AGAIN}


def datasets(W: dict, say, reads: list, reading: bool = False, ran: str = "", apple: bool = True) -> dict:
    """One dataset for each block that names one, in the kit's shapes."""
    lines = {i["id"][2:]: i["text"] for i in (say or {}).get("insights") or [] if isinstance(i, dict) and str(i.get("id", "")).startswith("i-")}
    moves = {}   # each card ends in its move: the first suggestion that answers it
    for s in (say or {}).get("suggestions") or []:
        if isinstance(s, dict) and str(s.get("answers") or "").startswith("i-"):
            moves.setdefault(s["answers"][2:], {"text": s["text"], "why": s["why"]})
    cards = []
    for c in W["cards"]:
        if c["today"] is None and not any(v is not None for v in c["values"][:-1]):
            continue   # a reading this source doesn't give is left out
        d = {"values": c["values"], "min": c["scale"][0], "max": c["scale"][1], "lit": c["lit"],
             "planned": [c["plan"]] if c.get("plan") is not None else [], "label": c["label"]}
        if c["usual"] is not None:
            d["ref"] = {"value": c["usual"], "label": c["key"]}
        pct = c["unit"] == "%"
        says = lines.get(c["id"], c["line"]) if W.get("fresh", True) else c["line"]   # Claude's lines were for that day's today
        cards.append({"id": c["id"], "icon": ICONS[c["id"]], "label": c["name"], "value": c["fig"] + ("%" if pct and c["fig"] else ""),
                      "unit": "" if pct else c["unit"], "says": says, "days": d})
        if c["id"] in moves:
            cards[-1]["move"] = moves[c["id"]]
    measured = bool((say or {}).get("goals"))
    note = ("Written from your last 14 days and your goal. " if measured else "Written from your last 14 days. ") \
        + "Claude reads your answers tomorrow morning."   # the note under Claude's questions
    food = {"kind": "days", "to": W["today"], "entry": MEAL, "empty": FOOD_EMPTY}
    if W.get("meals_after"):   # meals logged past the last day read wait for the next export's nights
        ends = dt.date.fromisoformat(W["today"])
        later = f"Meals since {ends:%a %b} {ends.day} line up at your next export."
        food["empty"] = dict(FOOD_EMPTY, via=later)
        food["caption"] = later
    if W.get("food"):
        food.update({k: W["food"][k] for k in ("rows", "bars", "label", "caption") if W["food"].get(k)})
    out = {"food": food} if "food" in common.BLOCKS else {}
    return {**out, "today": {"to": W["today"], "cards": cards, "empty": READING if reading else empty(reads, W)},
            "questions": {"note": note, "before": "once your sleep is in"},
            "connections": where(W, ran, apple)}


def typed(rec, say) -> dict:
    """What was typed for each answered question, by its id, from Health's own answers.jsonl, for the page alone."""
    ids = {q["id"] for q in (say or {}).get("questions") or [] if isinstance(q, dict) and isinstance(q.get("answer"), dict)}
    out = {}
    for a in common.read_jsonl(rec / "answers.jsonl"):
        if a.get("question") in ids and isinstance(a.get("words"), str):
            out[a["question"]] = a["words"]
    return out


def build(rec, root, now, run: str = "by-hand", W=None, move: str = "", reading=None) -> dict:
    """Draw the page from what Health's folder holds now. Returns the kit's answer: {"path", "blocks", ...}. reading:
    a file is being read now; drawn on its own, the page works that out from the inbox and the last run."""
    kit = load_kit(root)
    doc = say_file.load(rec)
    if reading is None:
        reading = W is None and upload.waiting(rec)
    if W is None:   # drawn on its own, between runs: the 14 days end on the last day read, as a run's do
        rows, today = days.load(rec), meals.owners_day(now)
        W = work.build(rows, meals.load(rec), goals.last_day(rows, today, upload.came(rec)) or today, today,
                       kinds=goals.kinds(root))
    reads, _ = sources.chosen(root)
    exports = common.load_json(rec / "store" / upload.EXPORTS, {}) or {}   # an Apple export read, or only a file of days
    apple = not (bool((W.get("counts") or {}).get("days")) and not exports)
    return kit.build(str(common.ROOT), str(rec), root=str(root), now=now, run=run,
                     data=datasets(W, doc, reads, reading, run if run != "by-hand" else "", apple),
                     answers=typed(rec, doc), move=move or "")


def last_run(rec) -> str:
    runs = [r for r in common.read_jsonl(rec / "runs.jsonl") if r.get("started_at")]
    return str(runs[-1]["started_at"]) if runs else "by-hand"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"Build {common.TITLE}'s page from what its folder holds. No model, no request.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    ap.add_argument("--run")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    if not rec.is_dir():
        print(f"page: {common.TITLE}'s folder isn't there yet. Set up Hydra-OS first.", file=sys.stderr)
        return 1
    root = common.root_of(rec)
    old = common.load_json(rec / "home.json", {}) or {}
    move = old.get("move") if isinstance(old.get("move"), dict) else ""   # {"text", "link"}: the kit adds its button
    try:
        got = build(rec, root, common.now(a.now), a.run or last_run(rec), move=move)
    except NoKit as e:
        print(f"page: {e}", file=sys.stderr)
        return 1
    print(f"page: {common.tilde(got['path'])}, {got['blocks']} blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
