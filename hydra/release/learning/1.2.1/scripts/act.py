"""Research's saves, each with its Undo: a project named on the page or in the chat, a project's general topic set in
the chat, and a goal Research stops scouting. The page reaches this script through Hydra-OS's own server, and Claude
through `hydra act learning ...`; both run it the same way, with an argument list and never a shell.

    python3 scripts/act.py add-project --words=<its name> [--yes]
    python3 scripts/act.py unadd-project --project=<id> [--yes]
    python3 scripts/act.py set-topic --project=<id> --topic=<topic id> [--yes]
    python3 scripts/act.py unset-topic --project=<id> --topic=<the topic it had, or matched> [--yes]
    python3 scripts/act.py skip-goal --goal=<goal id> [--yes]
    python3 scripts/act.py unskip-goal --goal=<goal id> [--yes]
    python3 scripts/act.py projects | scouted | topics | was | goals | skipped   # the ids a field may take, as JSON

Every command takes --record DIR (else Research's own folder under HYDRA_ROOT) and, for tests, --now ISO.

Without --yes it's the check: it writes nothing and says what it would save. With --yes it's the save: it checks every
field again itself, writes store/projects.json or store/goals.json whole or not at all (0600), then draws say.json,
home.json, the angles offer and the page again, in code. Its last line on stdout is one JSON object, {"ok", "said"},
with "undo" when the save gives its Undo fields of its own. A refusal is {"ok": false, "said": <why>}, exit 2.

- A project's name stays in store/projects.json and on the page, never in say.json, home.json, a query or shared/.
  What's said back names its general topic, never its name.
- A topic's Undo puts back the topic the project had just before, or `matched`, the ones its own words match; a
  goal's, that it's scouted again.
- `by` is who saved a project, `page` or `chat`, from HYDRA_BY.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import json
import os
import re
import sys

import common
import draw
import search
import store

SAID_MOST = 200
LINK = re.compile(r"[a-z][a-z0-9+.-]*://|www\.|\b[\w-]+(\.[\w-]+)*\.[a-z]{2,}\b", re.I)
KEY = re.compile(r"[A-Za-z0-9_\-]{24,}")
FOLDER = re.compile(r"(^|\s)(~|/Users/|/home/)")
EMAIL = re.compile(r"\S+@\S+\.\S+")
PHONE = re.compile(r"\+?\(?\d[\d ().-]{6,}\d")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
FIELDS = {"add-project": ("words",), "unadd-project": ("project",), "set-topic": ("project", "topic"),
          "unset-topic": ("project", "topic"), "skip-goal": ("goal",), "unskip-goal": ("goal",)}
LISTS = ("projects", "scouted", "topics", "was", "goals", "skipped")
MATCHED = "matched"   # a topic's Undo to the ones the project's own words match
SAVES = tuple(FIELDS)


class Refused(Exception):
    """Why a save can't go ahead, in a person's words."""


def answer_line(ok: bool, said: str, **extra) -> int:
    print(json.dumps({"ok": ok, "said": " ".join(str(said).split())[:SAID_MOST], **extra}, ensure_ascii=False))
    return 0 if ok else 2


def parse(argv: list) -> tuple:
    """(verb, record, fields, yes, now): the verb, then --record, each of its fields at most once as --<field>=<value>,
    and --yes for the save. --now is for tests; the server never sends it."""
    if not argv or argv[0] not in SAVES + LISTS:
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
            if name not in FIELDS.get(verb, ()) or name in fields:
                raise Refused("That isn't one of this save's fields, each once.")
            fields[name] = value
        else:
            raise Refused("That isn't one of this save's fields, each once.")
    if any(k not in fields for k in FIELDS.get(verb, ())):
        raise Refused("This save is missing one of its fields.")
    return verb, record, fields, yes, now


def typed(text, most: int) -> str:
    """The person's own line, as it's kept: one line of 1 to `most` characters, with no link, address, key, folder,
    phone number or control character."""
    if not isinstance(text, str) or CONTROL.search(text):
        raise Refused("That needs to be one line of plain text.")
    line = " ".join(text.split())
    if not 1 <= len(line) <= most:
        raise Refused(f"That needs to be 1 to {most} characters.")
    if LINK.search(line) or EMAIL.search(line):
        raise Refused("That can't hold a link or an address.")
    if KEY.search(line):
        raise Refused("That can't hold a key or a code.")
    if FOLDER.search(line):
        raise Refused("That can't hold a folder's path.")
    if any(sum(c.isdigit() for c in m.group()) >= 10 for m in PHONE.finditer(line)):
        raise Refused("That can't hold a phone number.")
    return line


def by() -> str:
    return "chat" if os.environ.get("HYDRA_BY") == "chat" else "page"


def topic_words(tid: str) -> str:
    return search.topics(search.load()).get(tid, "")


def redraw(rec, root, now) -> None:
    draw.everything(rec, root, now)


def scouted(rec, root) -> dict:
    return {p["id"]: p for p in store.all_projects(rec, root)}


def goal_ids(root, rec, scouting: bool) -> list:
    skip = store.skipped(rec)
    return [g["id"] for g in store.active_goals(root) if (g["id"] not in skip) == scouting]


def do_add_project(rec, root, f: dict, yes: bool, now) -> int:
    name = typed(f["words"], store.NAME)
    if any(p["name"].lower() == name.lower() for p in store.all_projects(rec, root)):
        raise Refused("That project is already on your list.")
    if len(store.projects(rec)) >= store.MOST_PROJECTS:
        raise Refused(f"{common.TITLE} scouts {store.MOST_PROJECTS} projects at most. Take one off first.")
    if not yes:
        return answer_line(True, "Add it to your projects. Research scouts it each Monday.")
    try:
        p = store.add_project(rec, name, now, by())
    except ValueError as e:
        raise Refused(str(e)) from None
    redraw(rec, root, now)
    got = scouted(rec, root).get(p["id"], {}).get("topics") or []
    said = (f"Added to your projects. Research scouts it as {topic_words(got[0])}." if got
            else "Added to your projects. No general topic matches its name yet.")
    return answer_line(True, said, undo={"project": p["id"]})


def do_unadd_project(rec, root, f: dict, yes: bool, now) -> int:
    if not store.ID.fullmatch(f["project"]) or store.project(rec, f["project"]) is None:
        raise Refused("That isn't one of the projects you added.")
    if not yes:
        return answer_line(True, "Take it off your projects.")
    store.remove_project(rec, f["project"])   # projects.json is there only while it holds a project
    redraw(rec, root, now)
    return answer_line(True, "Taken off your projects.")


def do_set_topic(rec, root, f: dict, yes: bool, now) -> int:
    p = scouted(rec, root).get(f["project"]) if store.ID.fullmatch(f["project"]) else None
    if p is None:
        raise Refused("That isn't one of the projects Research scouts.")
    words = topic_words(f["topic"])
    if not words:
        raise Refused("That isn't one of Research's general topics.")
    if not yes:
        return answer_line(True, f"Scout it as {words} from now on.")
    old = put_topic(rec, p, [f["topic"]])
    redraw(rec, root, now)
    return answer_line(True, f"Research scouts it as {words} from now on.",
                       undo={"project": p["id"], "topic": old[0] if old else MATCHED})


def put_topic(rec, p: dict, topic_ids: list) -> list:
    """A scouted project's topic set, in projects.json for a named one and goals.json for a goal; the ones it had."""
    if p.get("from_goal") and store.project(rec, p["id"]) is None:
        return store.set_goal_topics(rec, p["from_goal"], topic_ids)
    return store.set_topics(rec, p["id"], topic_ids)


def do_unset_topic(rec, root, f: dict, yes: bool, now) -> int:
    p = scouted(rec, root).get(f["project"]) if store.ID.fullmatch(f["project"]) else None
    if p is None:
        raise Refused("That isn't one of the projects Research scouts.")
    if f["topic"] != MATCHED and not topic_words(f["topic"]):
        raise Refused("That isn't one of Research's general topics.")
    if not yes:
        return answer_line(True, "Put its topic back as it was.")
    put_topic(rec, p, [] if f["topic"] == MATCHED else [f["topic"]])
    redraw(rec, root, now)
    return answer_line(True, "Its topic is back as it was.")


def do_skip_goal(rec, root, f: dict, yes: bool, now) -> int:
    if f["goal"] not in goal_ids(root, rec, scouting=True):
        raise Refused("That isn't one of the goals Research scouts.")
    if not yes:
        return answer_line(True, "Stop scouting this goal.")
    store.skip_goal(rec, f["goal"])
    redraw(rec, root, now)
    return answer_line(True, "Research won't scout this goal.", undo={"goal": f["goal"]})


def do_unskip_goal(rec, root, f: dict, yes: bool, now) -> int:
    if f["goal"] not in goal_ids(root, rec, scouting=False):
        raise Refused("That isn't a goal Research stopped scouting.")
    if not yes:
        return answer_line(True, "Scout this goal again.")
    store.unskip_goal(rec, f["goal"])
    redraw(rec, root, now)
    return answer_line(True, "Research scouts this goal again.")


def lists(rec, root, verb: str) -> int:
    if verb == "projects":
        out = [p["id"] for p in store.projects(rec)]
    elif verb == "scouted":
        out = list(scouted(rec, root))
    elif verb in ("topics", "was"):
        out = list(search.topics(search.load())) + ([MATCHED] if verb == "was" else [])
    else:
        out = goal_ids(root, rec, scouting=verb == "goals")
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
    root = common.root_of(rec)
    if verb in LISTS:
        return lists(rec, root, verb)
    try:
        return {"add-project": do_add_project, "unadd-project": do_unadd_project, "set-topic": do_set_topic,
                "unset-topic": do_unset_topic, "skip-goal": do_skip_goal,
                "unskip-goal": do_unskip_goal}[verb](rec, root, f, yes, common.now(at))
    except Refused as e:
        return answer_line(False, str(e))
    except OSError:
        return answer_line(False, "Nothing was saved: Research couldn't write its folder.")


if __name__ == "__main__":
    sys.exit(main())
