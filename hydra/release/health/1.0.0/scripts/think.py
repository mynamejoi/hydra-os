#!/usr/bin/env python3
"""Wellbeing's part in the morning review, the one step of Health's that needs Claude. The run on Hydra-OS's tick reads
the person's
files and works the page out in code, with no Claude. Each morning the person said yes to, the "Hydra-OS morning
review" task in the Claude app runs `hydra think`, which runs these two from Health's plugin with Hydra-OS's Python:

    python3 scripts/think.py --input --record DIR   # prints {"ask", "data"}: what Claude writes, and the figures
    python3 scripts/think.py --save --record DIR    # Claude's answer as JSON on stdin: checked, kept, drawn

--input works the 14 days out again from Health's folder, as the page drawn on its own does: no file is read again
and nothing is called. It asks for one of two things, or nothing:
- the judgment (judge.ASK): a headline, at most three suggestions and three questions, and a line for each reading
  while the newest day read is today. Asked when that day is today or yesterday, and the figures, the goals or the
  person's answers changed since the last judgment was saved;
- one new question (judge.ONE), on a day with nothing new to judge, when none is open and none was asked today;
- nothing, as {} with no ask, which Hydra-OS reads as nothing to review today: before any day has come in, with
  nothing new, or while the morning review is off.

--save checks the answer as Health's judgment step always has (judge.keep): its words lock, only figures it handed
over, one plain line each, at most three of each; a line that fails is dropped, never reworded, and why is said. What
passes is kept in store/judged.json, the answers it was handed are used, and say.json, home.json and the page are
written again. It prints one line and exits 0, or 2 with why nothing was saved. Wellbeing's answer comes whole, so
--part is refused and --done has nothing to finish.

The figures go to the review's Claude alone, given as data. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback

import answers as answer_log
import common
import days
import goals
import home
import judge
import meals
import page
import say
import upload
import work

MOST = 32 * 1024            # an input's most, in bytes
ANSWER_MOST = 64 * 1024     # an answer's most: Wellbeing's is a few short lines
AT = str((common.MANIFEST.get("schedule") or {}).get("at") or "07:40")   # the run's own time, for stale_after
SHAPE = f"That isn't the shape {common.TITLE}'s ask gives. Write the one JSON object it shows."


def worked(rec, root, now) -> dict:
    """What the last read worked out, again from Health's folder, as the page drawn on its own has it."""
    before = say.load(rec)
    rows, today = days.load(rec), meals.owners_day(now)
    came = upload.came(rec)
    W = work.build(rows, meals.load(rec), goals.last_day(rows, today, came) or today, today, kinds=goals.kinds(root))
    as_of = common.parse_time((before or {}).get("as_of")) or now
    mine = goals.build(root, rows, today, common.iso(as_of), read=bool(rows), came=came)
    handed, answered, done = answer_log.handed(rec, before)
    opened = [q["text"] for q in (before or {}).get("questions") or [] if isinstance(q, dict) and "answer" not in q]
    return {"before": before, "W": W, "mine": mine, "today": today, "as_of": as_of, "answered": answered,
            "done": done, "opened": opened, "figs": judge.figures(W, mine, handed, opened)}


def judged(rec) -> dict:
    """store/judged.json: {"mark", "kept", "on", "to", "asked"}, the last judgment's figures, what of it was kept, the
    person's day and the last day read it was written for, and the day of the last save, a judgment or a question."""
    got = common.load_json(rec / "store" / "judged.json", {}) or {}
    return got if isinstance(got, dict) else {}


def which(got: dict, last: dict, off: bool):
    """What Claude is asked for now: "judge", "one" or None."""
    W = got["W"]
    if off or not W["have"]:
        return None
    if not W["old"] and last.get("mark") != judge.digest(got["figs"]):
        return "judge"
    if not got["opened"] and last.get("asked") != got["today"].isoformat():
        return "one"
    return None


def ask_doc(kind: str, got: dict) -> dict:
    """{"ask", "data"} within MOST. A page of very many goals leaves the last ones out of what Claude reads."""
    figs = dict(got["figs"])
    while True:
        doc = {"ask": judge.ask(figs, kind, fresh=got["W"]["fresh"]), "data": figs}
        if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) <= MOST or not figs.get("goals"):
            return doc
        figs = dict(figs, goals=figs["goals"][:-1])


def _count(n: int, one: str) -> str:
    return f"{n} {one}" + ("" if n == 1 else "s")


def _offered(answer: dict, kind: str) -> int:
    if kind == "one":
        return len(answer.get("questions") or [])
    return (answer.get("headline") is not None) + len(answer.get("lines") or {}) + \
        len((answer.get("suggestions") or [])[:6]) + len((answer.get("questions") or [])[:6])


def shape_problem(answer, kind: str) -> str:
    """Why an answer isn't the shape its ask gave, in words, or ""."""
    if not isinstance(answer, dict):
        return SHAPE
    keys = ("questions",) if kind == "one" else ("headline", "lines", "suggestions", "questions")
    if not any(k in answer for k in keys):
        return SHAPE
    for k, kinds in (("headline", (str, type(None))), ("lines", dict), ("suggestions", list), ("questions", list)):
        if k in keys and k in answer and not isinstance(answer[k], kinds):
            return SHAPE
    return ""


def redraw(rec, root, now, got: dict, kept: dict, answered: list) -> bool:
    """say.json, home.json and the page again, from what the last read worked out and what the review kept."""
    W, before = got["W"], got["before"] or {}
    notes = [(i["text"], i["why"]) for i in before.get("insights") or [] if isinstance(i, dict) and i.get("block") == "connections"]
    say.write(rec, say.compose(W, kept, got["mine"], got["as_of"], AT, notes, answered, got["done"]))
    old = common.load_json(rec / "home.json", {}) or {}
    move = old.get("move") if isinstance(old, dict) and isinstance(old.get("move"), dict) else None
    home.build(rec, root, now, move, W=W)
    try:
        page.build(rec, root, now, page.last_run(rec), W=W, move=move or "")
        return True
    except (page.NoKit, ValueError, OSError, KeyError):
        return False


def save(rec, root, now, text: str) -> tuple:
    """(exit code, its one line): the review's answer checked, and what passes kept and drawn."""
    if len(text.encode("utf-8")) > ANSWER_MOST:
        return 2, f"That answer is longer than {common.TITLE} takes. Write the short lines its ask gives."
    try:
        answer = json.loads(text)
    except ValueError:
        return 2, f"That isn't JSON. Write the one JSON object {common.TITLE}'s ask shows."
    off = judge.review_off(root)
    if off:
        return 2, "The morning review is off, so nothing was saved."
    got, last = worked(rec, root, now), judged(rec)
    W, figs, today = got["W"], got["figs"], got["today"].isoformat()
    kind = which(got, last, off)
    if kind is None and W["have"] and not W["old"] and last.get("on") == today and last.get("mark") == judge.digest(figs):
        kind = "judge"   # today's judgment once more, as Claude puts right a line that was left out
    if kind is None:
        return 2, f"{common.TITLE} has nothing to review now, so nothing was saved."
    problem = shape_problem(answer, kind)
    if problem:
        return 2, problem
    if kind == "one":
        answer = {"questions": answer["questions"]}
    elif not W["fresh"]:
        answer = dict(answer, lines={})   # lines are asked for only while the newest day read is today
    goal_ids = {g["id"] for g in got["mine"]}
    kept = judge.keep(answer, judge.allowed_numbers(W, figs), goal_ids, [c["id"] for c in W["cards"]])
    new = kept["questions"][:1] if kind == "one" else kept["questions"]
    shown = len(new) if kind == "one" else (kept["headline"] is not None) + len(kept["lines"]) + len(kept["suggestions"]) + len(new)
    if _offered(answer, kind) and not shown:
        return 2, f"Nothing could be kept: {kept['why'][0]}. Write it again from the data's figures."
    if kind == "one":
        before = last.get("kept") if isinstance(last.get("kept"), dict) else judge.keep(None, set(), set())
        asked = [q for q in before.get("questions") or [] if isinstance(q, dict)
                 and judge.question_id(str(q.get("text", ""))) not in got["done"]]
        doc = dict(last, kept={k: before.get(k) for k in ("headline", "lines", "suggestions")} | {"questions": asked + new},
                   asked=today)
        answered = got["answered"]
        line = "Saved one new question." if new else "Saved: no new question today."
    else:
        doc = {"mark": judge.digest(dict(figs, answers=[])),   # the answers are used now, so the next mark has none
               "kept": {k: kept[k] for k in ("headline", "lines", "suggestions", "questions")},
               "on": today, "to": W["today"], "asked": today}
        answered = []   # the answers were handed over, so their questions are done
        said = (["a headline"] if kept["headline"] else []) + \
            [_count(len(kept[k]), w) for k, w in (("lines", "line"), ("suggestions", "suggestion"), ("questions", "question")) if kept[k]]
        line = "Saved: " + (", ".join(said[:-1]) + " and " + said[-1] if len(said) > 1 else said[0] if said else "nothing new to add today") + "."
    common.write_json(common.folder(rec / "store") / "judged.json", doc)
    drawn = redraw(rec, root, now, got, judge.standing(doc, W, figs, goal_ids, got["today"], off), answered)
    if kept["dropped"]:
        line += f" Left out {_count(kept['dropped'], 'line')}: {kept['why'][0]}."
    if not drawn:
        line += f" {common.TITLE}'s page shows it after its next read."
    return 0, line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{common.TITLE}'s part in the morning review: its ask, and its save.")
    ap.add_argument("--input", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--part")
    ap.add_argument("--done", action="store_true")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    if a.input == a.save:
        print("think: give --input or --save.", file=sys.stderr)
        return 2
    rec = common.record_dir(a.record)
    root = common.root_of(rec)
    now = common.now(a.now)
    out = sys.stdout.buffer
    if a.input:
        got = worked(rec, root, now) if rec.is_dir() else None
        kind = which(got, judged(rec), judge.review_off(root)) if got else None
        out.write((json.dumps(ask_doc(kind, got) if kind else {}, ensure_ascii=False) + "\n").encode("utf-8"))
        return 0
    if a.done:
        code, line = 0, f"Nothing to finish: {common.TITLE}'s answer comes whole."
    elif a.part is not None:
        code, line = 2, f"{common.TITLE}'s answer comes whole, with no parts. Save it without --part."
    elif not rec.is_dir():
        code, line = 2, f"{common.TITLE} isn't set up here, so nothing was saved."
    else:
        try:
            code, line = save(rec, root, now, sys.stdin.buffer.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 (whatever went wrong, the review hears it in one line)
            traceback.print_exc()   # to stderr, which Hydra-OS doesn't pass on
            code, line = 2, f"{common.TITLE} couldn't save it this time."
    out.write((line + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
