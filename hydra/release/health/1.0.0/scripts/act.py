#!/usr/bin/env python3
"""Health's saves: an answer to one of Claude's questions, and a meal typed into "Log a meal", the food block's one
entry, each with its Undo. The page reaches this script through Hydra-OS's own server, and Claude through `hydra act health ...`; both run
it the same way, with an argument list and never a shell.

    python3 scripts/act.py answer --question=<id> [--words=<their words> | --pick=<id> [--on=yes|no]] [--yes]
    python3 scripts/act.py unanswer --question=<id> [--pick=<id>] [--yes]
    python3 scripts/act.py log-meal --words=<their line> [--yes]
    python3 scripts/act.py unlog-meal --meal=<id> [--yes]
    python3 scripts/act.py questions | picks --question=<id> | meals        # the ids a field may take, as a JSON list

Every command takes --record DIR (else Health's own folder under HYDRA_ROOT) and, for tests, --now ISO.

Without --yes it's the check: it writes nothing and says what it would save. With --yes it's the save: it checks every
field again itself, writes answers.jsonl or store/meals.jsonl whole or not at all (0600), then writes say.json's
question and home.json again and draws the page again, in code. Its last line on stdout is one JSON object, {"ok",
"said"}, with "undo" when the save gives the Undo its own fields. A refusal is {"ok": false, "said": <why>}, exit 2.

- An answer adds one line to answers.jsonl, and its Undo takes that line back out, so the file is byte for byte as it
  was. The next run reads the answer that stands
  (answers.py), then drops the question and never asks it again.
- The typed words stay in answers.jsonl and the meal log, in Health's own folder. say.json, home.json, shared/ and
  the page's summary carry only that a question was answered, and a meal only as the marks Health could place. The
  page itself shows the person their own answer.
- `by` is who saved it, `page` or `chat`, from HYDRA_BY.

Health's lock: a save keeps the person's own words and choices, and every `said` is a fixed line, never advice. It
starts no shell, no model and no request.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys

import answers
import common
import home
import meals
import page
import say

SAID_MOST = 200
WORDS_MOST = 120
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
# what typed words may never hold, as Hydra-OS's own route refuses it (plugins/hydra/scripts/hydralib/act.py), and a
# bare domain too: a link or an address, a key or a code, a folder's path, or a phone number
LINK = re.compile(r"https?://|www\.|[\w.+-]+@[\w-]+\.[\w.-]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}\b(?![.\w-])", re.I)
KEY = re.compile(r"[A-Za-z0-9_\-.=+/]{24,}")
FOLDER = re.compile(r"(^|[\s(\"'])(~/|/Users/|/home/)")
WHEN = re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2})?|\d{1,2}:\d{2}")
PHONE = re.compile(r"\+?\(?\d[\d ().-]{6,}\d")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
FIELDS = {"answer": ("question", "pick", "on", "words"), "unanswer": ("question", "pick"),
          "log-meal": ("words",), "unlog-meal": ("meal",), "picks": ("question",), "questions": (), "meals": ()}
NEEDS = {"answer": ("question",), "unanswer": ("question",), "log-meal": ("words",), "unlog-meal": ("meal",),
         "picks": ("question",), "questions": (), "meals": ()}
LISTS = ("questions", "picks", "meals")


class Refused(Exception):
    """Why a save can't go ahead, in a person's words."""


def answer_line(ok: bool, said: str, **extra) -> int:
    print(json.dumps({"ok": ok, "said": " ".join(str(said).split())[:SAID_MOST], **extra}, ensure_ascii=False))
    return 0 if ok else 2


def parse(argv: list) -> tuple:
    """(verb, record, fields, yes, now): the verb, then --record, each of its fields at most once as --<field>=<value>,
    and --yes for the save. --now is for tests; the server never sends it."""
    if not argv or argv[0] not in FIELDS:
        raise Refused(f"{common.TITLE} has no such save.")
    verb, rest = argv[0], list(argv[1:])
    record, now, yes, fields = None, None, False, {}
    while rest:
        a = rest.pop(0)
        if a == "--yes":
            yes = True
        elif a in ("--record", "--now"):
            if not rest:
                raise Refused("That save is missing a value.")
            if a == "--record":
                record = rest.pop(0)
            else:
                now = rest.pop(0)
        elif a.startswith("--record="):
            record = a.split("=", 1)[1]
        elif a.startswith("--now="):
            now = a.split("=", 1)[1]
        elif a.startswith("--") and "=" in a:
            name, value = a[2:].split("=", 1)
            if name not in FIELDS[verb] or name in fields:
                raise Refused("That isn't one of this save's fields, each once.")
            fields[name] = value
        else:
            raise Refused("That isn't one of this save's fields, each once.")
    if any(k not in fields for k in NEEDS[verb]):
        raise Refused("This save is missing one of its fields.")
    return verb, record, fields, yes, now


def typed(text) -> str:
    """The person's own line, as it's kept: one line of 1 to 120 characters, with no link, address or control character."""
    if not isinstance(text, str) or CONTROL.search(text):
        raise Refused("That needs to be one line of plain text.")
    line = " ".join(text.split())
    if not 1 <= len(line) <= WORDS_MOST:
        raise Refused(f"That needs to be 1 to {WORDS_MOST} characters.")
    if LINK.search(line):
        raise Refused("That can't hold a link or an address.")
    if KEY.search(line):
        raise Refused("That can't hold a key or a code.")
    if FOLDER.search(line):
        raise Refused("That can't hold a folder's path.")
    if any(sum(c.isdigit() for c in m.group()) >= 10 for m in PHONE.finditer(WHEN.sub(" ", line))):
        raise Refused("That can't hold a phone number.")
    return line


def by() -> str:
    return "chat" if os.environ.get("HYDRA_BY") == "chat" else "page"


# ---- the questions say.json holds ----

def questions(rec) -> dict:
    doc = say.load(rec) or {}
    return {q["id"]: q for q in doc.get("questions") or []
            if isinstance(q, dict) and isinstance(q.get("id"), str) and ID.match(q["id"])}


def pick_ids(q: dict) -> list:
    got = [p["id"] for p in q.get("picks") or [] if isinstance(p, dict) and isinstance(p.get("id"), str)]
    only = q.get("only")
    return got + ([only["id"]] if isinstance(only, dict) and isinstance(only.get("id"), str) else [])


def redraw(rec, root, now) -> None:
    """The page again, so an open one sees the newer build and shows the save in place, with the run's move whole: its
    line, and for an old export its button to the drop place."""
    old = common.load_json(rec / "home.json", {}) or {}
    move = old.get("move") if isinstance(old, dict) and isinstance(old.get("move"), dict) else ""
    try:
        page.build(rec, root, now, page.last_run(rec), move=move)
    except (page.NoKit, ValueError, OSError, KeyError):
        pass   # the save stands; Hydra-OS's server draws the page again when it's asked for


def mark(rec, root, now) -> None:
    """say.json's questions as answers.jsonl now has them, then home.json: an answered question carries only that it
    was answered, never the words."""
    doc = say.load(rec)
    if doc is None:
        return
    standing = answers.state(rec)
    for q in doc.get("questions") or []:
        if not isinstance(q, dict):
            continue
        q.pop("answer", None)
        got = answers.marker(q, standing.get(q.get("id")))
        if got:
            q["answer"] = got
    say.write(rec, doc)
    old = common.load_json(rec / "home.json", {}) or {}
    move = old.get("move") if isinstance(old.get("move"), dict) else None
    home.build(rec, root, now, move)
    redraw(rec, root, now)


def do_answer(rec, root, f: dict, yes: bool, now) -> int:
    qs = questions(rec)
    q = qs.get(f["question"])
    if q is None:
        raise Refused(f"That question isn't one {common.TITLE} is asking.")
    kind = q.get("kind", "words")
    row = {"at": common.iso(now), "question": q["id"]}
    if kind == "words":
        if "pick" in f or "on" in f or "words" not in f:
            raise Refused("This question takes your own words.")
        row["words"] = typed(f["words"])
        most = int(q.get("max") or WORDS_MOST)
        if len(row["words"]) > most:
            raise Refused(f"That needs to be {most} characters or fewer.")
    else:
        if "words" in f or f.get("pick") not in pick_ids(q):
            raise Refused("This question takes one of its own answers.")
        if kind == "one" and "on" in f:
            raise Refused("This question takes one answer.")
        if f.get("on", "yes") not in ("yes", "no"):
            raise Refused("An answer is on or off.")
        row["pick"] = f["pick"]
    row["on"] = f.get("on", "yes") == "yes"
    row["by"] = by()
    if not yes:
        return answer_line(True, "Save your answer. Claude reads it tomorrow morning.")
    common.append_line(rec / "answers.jsonl", row)
    mark(rec, root, now)
    undo = {"question": q["id"]}
    if "pick" in row:
        undo["pick"] = row["pick"]
    return answer_line(True, "Saved. Claude reads it tomorrow morning.", undo=undo)


def do_unanswer(rec, root, f: dict, yes: bool, now) -> int:
    if f["question"] not in questions(rec):
        raise Refused(f"That question isn't one {common.TITLE} is asking.")
    if not yes:
        return answer_line(True, "Take your answer back.")
    path, pick = rec / "answers.jsonl", f.get("pick")
    try:
        raw = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        raw = []
    for i in range(len(raw) - 1, -1, -1):   # the newest line for this question (and pick): the one its save added
        try:
            row = json.loads(raw[i])
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("question") == f["question"] and (pick is None or row.get("pick") == pick):
            del raw[i]
            if raw:
                common.write_atomic(path, "".join(raw))
            else:
                path.unlink()   # the file wasn't there before the first answer
            break
    # with nothing to take back it changes nothing, so an Undo pressed twice is harmless
    mark(rec, root, now)
    return answer_line(True, "Taken back.")


# ---- Log a meal ----

def todays(rec, now) -> list:
    """The meals that can be taken back: the latest day's, so a meal just logged always is, and "the dinner I logged
    last night" too, but never an older day's."""
    got = meals.load(rec)
    last = max((m["day"] for m in got if m["day"] <= meals.owners_day(now).isoformat()), default=None)
    return [m for m in got if m["day"] == last]


def read_back(m: dict) -> str:
    """How a meal was read, in one fixed shape: the meal, its time, and only the words Health could place."""
    hour, minute = int(m["at"][:2]), m["at"][3:]
    parts = [f"{m['meal']} at {hour % 12 or 12}:{minute} {'am' if hour < 12 else 'pm'}"]
    parts += [x for x in (m.get("where"), m.get("size")) if x]
    parts += [f"{k}: {m[field]}" for k, field in (("protein", "protein"), ("vegetables", "veg"), ("drinks", "drinks")) if m.get(field)]
    if m.get("none"):
        parts.append("no drinks")
    return ", ".join(parts) + "."


def do_log_meal(rec, root, f: dict, yes: bool, now) -> int:
    line = typed(f["words"])
    got = meals.read_line(line, now)
    meal = {"id": "m-" + secrets.token_hex(6), "day": meals.owners_day(now).isoformat(), **got, "words": line, "by": by(),
            "saved_at": common.iso(now)}
    if not yes:
        return answer_line(True, "Save this meal: " + read_back(meal))
    common.folder(rec / "store")
    common.append_line(rec / "store" / "meals.jsonl", meal)
    redraw(rec, root, now)
    return answer_line(True, "Saved. " + read_back(meal), undo={"meal": meal["id"]})


def do_unlog_meal(rec, root, f: dict, yes: bool, now) -> int:
    if not ID.match(f["meal"]) or f["meal"] not in [m["id"] for m in todays(rec, now)]:
        raise Refused("That isn't one of your latest meals, so it stays.")
    if not yes:
        return answer_line(True, "Take this meal back.")
    path = rec / "store" / "meals.jsonl"
    keep = [raw for raw in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if not raw.strip() or (json.loads(raw).get("id") != f["meal"])]
    if keep:
        common.write_atomic(path, "".join(keep))
    else:
        path.unlink()
    redraw(rec, root, now)
    return answer_line(True, "Taken back.")


def lists(rec, verb: str, f: dict, now) -> int:
    """The ids a field may take, as a JSON list. Writes nothing."""
    if verb == "questions":
        out = sorted(questions(rec))
    elif verb == "picks":
        out = pick_ids(questions(rec).get(f["question"]) or {})
    else:
        out = [m["id"] for m in todays(rec, now)]
    print(json.dumps(out))
    return 0


def main(argv=None) -> int:
    try:
        verb, record, f, yes, at = parse(sys.argv[1:] if argv is None else argv)
    except Refused as e:
        return answer_line(False, str(e))
    rec = common.record_dir(record)
    if not rec.is_dir():
        return answer_line(False, f"{common.TITLE} isn't set up on this Mac yet.")
    now = common.now(at)
    if verb in LISTS:
        return lists(rec, verb, f, now)
    try:
        return {"answer": do_answer, "unanswer": do_unanswer, "log-meal": do_log_meal,
                "unlog-meal": do_unlog_meal}[verb](rec, common.root_of(rec), f, yes, now)
    except Refused as e:
        return answer_line(False, str(e))


if __name__ == "__main__":
    sys.exit(main())
