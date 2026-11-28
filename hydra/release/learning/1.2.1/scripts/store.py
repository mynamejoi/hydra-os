"""Research's own store, in its record folder (<root>/learning/store/), each file written whole, 0600 in a 0700 folder,
and each carrying its contract and version, so migrate.py can move it one version at a time:

- projects.json  research-projects/v1  the projects named on the page or in the chat: each {"id", "name", "line",
                 "topics", "from_goal", "added", "by"}. "name" and "line" are the person's own words: they stay here and
                 on the page, and never go into say.json, home.json, a query, the morning review or the shared file.
                 "topics" is the one id from search.json's closed list set in the chat, or [] for the ones its own words
                 match (search.best_topics).
- goals.json     research-goals/v1     what was said about the person's goals, which Research scouts by default:
                 {"skipped": [goal id], "scouted": [goal id], "topics": {goal id: [topic id]}}, each key only while it
                 holds something, and the file only while any does.
- finds.json     research-finds/v1     what each scout kept: {"id", "week", "project", "topic", "question", "line",
                 "move", "sources": [{"url", "site"}], "kept_at"}, the last twelve weeks.
- notes.json     research-notes/v1     the notes the person dropped on the page: {"id", "title", "file", "topics",
                 "added"}. Each note's file stays in inbox/ as it came, on this Mac only (notes.py).
- releases.json  research-releases/v1  the public release notes read on the tick: each source's lines with the day each
                 was first seen, and the fingerprints of every line seen.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import pathlib
import re

import common
import search

FOLDER = "store"
FILES = {"projects.json": "research-projects/v1", "goals.json": "research-goals/v1", "finds.json": "research-finds/v1",
         "notes.json": "research-notes/v1", "releases.json": "research-releases/v1"}
GOAL_KEYS = ("skipped", "scouted", "topics")
KEEP_WEEKS = 12
NAME, LINE = 60, 120          # a project's name and line, at most, as the person typed them
MOST_PROJECTS = 12
ID = re.compile(r"[a-z]-[0-9a-f]{6}")
ID_GOAL = re.compile(r"g-[0-9a-f]{6}")


def path(rec: pathlib.Path, name: str) -> pathlib.Path:
    return rec / FOLDER / name


def read(rec: pathlib.Path, name: str, key: str) -> list:
    """A store file's list, or [] when it isn't there or isn't this version. A newer version is never read or reset."""
    doc = common.load_json(path(rec, name), {}) or {}
    if not isinstance(doc, dict) or doc.get("contract") != FILES[name]:
        return []
    got = doc.get(key)
    return [x for x in got if isinstance(x, dict)] if isinstance(got, list) else []


def newer(rec: pathlib.Path) -> list:
    """The store files written by a newer version of Research, which this one keeps as they are (the doctor names them)."""
    out = []
    for name, contract in FILES.items():
        doc = common.load_json(path(rec, name), None)
        if isinstance(doc, dict) and isinstance(doc.get("contract"), str) and doc["contract"] != contract:
            out.append(name)
    return out


def write(rec: pathlib.Path, name: str, key: str, items: list, extra: dict | None = None) -> None:
    if name in newer(rec):
        raise OSError(f"{name} is from a newer version of Research")
    common.folder(rec / FOLDER)
    common.write_json(path(rec, name), dict({"contract": FILES[name], key: items}, **(extra or {})))


def new_id(kind: str, *parts) -> str:
    return f"{kind}-" + hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:6]


# ---- projects ----

def projects(rec: pathlib.Path) -> list:
    return read(rec, "projects.json", "projects")


def project(rec: pathlib.Path, pid: str) -> dict | None:
    return next((p for p in projects(rec) if p.get("id") == pid), None)


def clean(text: str, most: int) -> str:
    return " ".join(str(text or "").split())[:most]


def add_project(rec: pathlib.Path, name: str, now, by: str, line: str = "", from_goal: str | None = None) -> dict:
    ps = projects(rec)
    name = clean(name, NAME)
    if not name:
        raise ValueError("A project needs a name.")
    if len(ps) >= MOST_PROJECTS:
        raise ValueError(f"{common.TITLE} scouts {MOST_PROJECTS} projects at most. Take one off first.")
    if any(p["name"].lower() == name.lower() for p in ps):
        raise ValueError("That project is already on your list.")
    if from_goal and any(p.get("from_goal") == from_goal for p in ps):
        raise ValueError("That goal is already one of your projects.")
    p = {"id": new_id("p", name.lower(), common.iso(now)), "name": name, "line": clean(line, LINE), "topics": [],
         "from_goal": from_goal, "added": common.iso(now), "by": by}
    write(rec, "projects.json", "projects", ps + [p])
    return p


def remove_project(rec: pathlib.Path, pid: str) -> dict | None:
    ps = projects(rec)
    gone = next((p for p in ps if p["id"] == pid), None)
    rest = [p for p in ps if p["id"] != pid]
    if gone and rest:
        write(rec, "projects.json", "projects", rest)
    elif gone:
        path(rec, "projects.json").unlink()   # there only while it holds a project, so an add and its Undo leave none
    return gone


def restore_project(rec: pathlib.Path, p: dict) -> None:
    ps = [x for x in projects(rec) if x["id"] != p["id"]]
    write(rec, "projects.json", "projects", ps + [p])


def set_topics(rec: pathlib.Path, pid: str, topic_ids: list) -> list:
    """A named project's topics, set in the chat, or [] for the ones its words match; the ones it had."""
    ps = projects(rec)
    old = []
    for p in ps:
        if p["id"] == pid:
            old = list(p.get("topics") or [])
            p["topics"] = list(dict.fromkeys(topic_ids))[:search.MOST_TOPICS]
    write(rec, "projects.json", "projects", ps)
    return old


# ---- the person's goals, scouted by default ----

def goal_doc(rec: pathlib.Path) -> dict:
    doc = common.load_json(path(rec, "goals.json"), {}) or {}
    if not isinstance(doc, dict) or doc.get("contract") != FILES["goals.json"]:
        return {}
    out = {}
    for k in ("skipped", "scouted"):
        if isinstance(doc.get(k), list):
            out[k] = [g for g in doc[k] if isinstance(g, str)]
    if isinstance(doc.get("topics"), dict):
        out["topics"] = {g: [t for t in v if isinstance(t, str)] for g, v in doc["topics"].items() if isinstance(v, list)}
    return out


def write_goal_doc(rec: pathlib.Path, doc: dict) -> None:
    """goals.json with only the keys that hold something, in one order, so an Undo leaves it byte for byte as it was;
    there only while any does."""
    if "goals.json" in newer(rec):
        raise OSError("goals.json is from a newer version of Research")
    kept = {k: doc[k] for k in GOAL_KEYS if doc.get(k)}
    if kept:
        common.folder(rec / FOLDER)
        common.write_json(path(rec, "goals.json"), dict({"contract": FILES["goals.json"]}, **kept))
    else:
        path(rec, "goals.json").unlink(missing_ok=True)


def active_goals(root: pathlib.Path) -> list:
    """The person's active goals that no other page counts (yours/goals.json), in their order."""
    doc = common.load_json(root / "yours" / "goals.json", {}) or {}
    out = []
    for g in doc.get("goals") or [] if isinstance(doc, dict) and isinstance(doc.get("goals"), list) else []:
        if isinstance(g, dict) and isinstance(g.get("id"), str) and ID_GOAL.fullmatch(g["id"]) \
                and g.get("measured_by") in (None, {"app": "goals"}) and g.get("status", "active") == "active":
            out.append(g)
    return out


def skipped(rec: pathlib.Path) -> set:
    """The goals the person said not to scout: each one skipped since, and each said no to before Research scouted
    every goal, unless they've said to scout it since."""
    doc = goal_doc(rec)
    said_no = {q[len("q-goal-"):] for q, pick in answered(rec).items() if q.startswith("q-goal-") and pick == "no"}
    return set(doc.get("skipped") or []) | (said_no - set(doc.get("scouted") or []))


def said_no(rec: pathlib.Path, gid: str) -> bool:
    return answered(rec).get(f"q-goal-{gid}") == "no"


def skip_goal(rec: pathlib.Path, gid: str) -> None:
    doc = goal_doc(rec)
    doc["scouted"] = [g for g in doc.get("scouted") or [] if g != gid]
    if not said_no(rec, gid):
        doc["skipped"] = [g for g in doc.get("skipped") or [] if g != gid] + [gid]
    write_goal_doc(rec, doc)


def unskip_goal(rec: pathlib.Path, gid: str) -> None:
    doc = goal_doc(rec)
    doc["skipped"] = [g for g in doc.get("skipped") or [] if g != gid]
    if said_no(rec, gid):
        doc["scouted"] = [g for g in doc.get("scouted") or [] if g != gid] + [gid]
    write_goal_doc(rec, doc)


def set_goal_topics(rec: pathlib.Path, gid: str, topic_ids: list) -> list:
    """A goal's topics, set in the chat, or [] for the ones its words match; the ones it had."""
    doc = goal_doc(rec)
    topics = dict(doc.get("topics") or {})
    old = list(topics.get(gid) or [])
    if topic_ids:
        topics[gid] = list(dict.fromkeys(topic_ids))[:search.MOST_TOPICS]
    else:
        topics.pop(gid, None)
    doc["topics"] = topics
    write_goal_doc(rec, doc)
    return old


# ---- every project, each with its topics ----

def answered(rec: pathlib.Path) -> dict:
    """{question id: its standing answer} from answers.jsonl, which holds what was answered before Research stopped
    asking: a project's line (q-about-), its topics (q-topics- and q-nofit-, a multi's picks as they stand: on yes adds,
    on no takes off, only clears the rest), and a goal's yes or no (q-goal-)."""
    out = {}
    for a in common.read_jsonl(rec / "answers.jsonl"):
        q, pick = a.get("question"), a.get("pick")
        if isinstance(q, str) and q.startswith("q-about-") and isinstance(a.get("words"), str):
            out[q] = a["words"]
            continue
        if not isinstance(q, str) or not isinstance(pick, str):
            continue
        if q.startswith(("q-topics-", "q-nofit-")):
            have = out.setdefault(q, [])
            if a.get("on") is False or a.get("on") == "no":
                out[q] = [x for x in have if x != pick]
            elif pick == "none":
                out[q] = ["none"]
            else:
                out[q] = [x for x in have if x != "none" and x != pick] + [pick]
        elif q.startswith("q-goal-"):
            out[q] = pick
    return out


def goal_pid(gid: str) -> str:
    return "p-" + hashlib.sha256(f"goal|{gid}".encode("utf-8")).hexdigest()[:6]


def all_projects(rec: pathlib.Path, root: pathlib.Path) -> list:
    """Every project Research scouts: the ones named on the page or in the chat (projects.json), then each active goal
    no other page counts, unless the person said not to scout it, named by its own words. Each with its topics: the
    ones set in the chat, else the ones picked in an answer before, else the ones its own words match, else none."""
    ans = answered(rec)
    doc_search = search.load()
    names = search.topics(doc_search)
    out = [dict(p) for p in projects(rec)]
    named = {p.get("from_goal") for p in out}
    doc, skip = goal_doc(rec), skipped(rec)
    for g in active_goals(root):
        if g["id"] not in skip and g["id"] not in named:
            out.append({"id": goal_pid(g["id"]), "name": clean(g.get("text", ""), NAME), "line": "",
                        "topics": list((doc.get("topics") or {}).get(g["id"]) or []), "from_goal": g["id"],
                        "added": "", "by": "goal"})
    for p in out:
        if not p.get("line") and isinstance(ans.get(f"q-about-{p['id']}"), str):
            p["line"] = clean(ans[f"q-about-{p['id']}"], LINE)
        given = [t for t in p.get("topics") or [] if t in names]
        if not given:
            picked = ans.get(f"q-topics-{p['id']}") or ans.get(f"q-nofit-{p['id']}") or []
            given = [t for t in picked if t in names][:search.MOST_TOPICS]
        p["topics"] = given or search.best_topics(f"{p.get('name', '')} {p.get('line', '')}", doc_search)
    return out


# ---- finds ----

def finds(rec: pathlib.Path) -> list:
    return read(rec, "finds.json", "finds")


def keep_finds(rec: pathlib.Path, week: dt.date, new: list) -> None:
    """This week's finds in place of any kept for the same week, and only the last twelve weeks."""
    w = week.isoformat()
    first = (week - dt.timedelta(weeks=KEEP_WEEKS - 1)).isoformat()
    kept = [f for f in finds(rec) if f.get("week") != w and str(f.get("week", "")) >= first]
    write(rec, "finds.json", "finds", kept + new)


# ---- notes ----

def notes(rec: pathlib.Path) -> list:
    return read(rec, "notes.json", "notes")


# ---- release notes ----

def releases(rec: pathlib.Path) -> dict:
    doc = common.load_json(path(rec, "releases.json"), {}) or {}
    if not isinstance(doc, dict) or doc.get("contract") != FILES["releases.json"]:
        return {}
    got = doc.get("sources")
    return {k: v for k, v in got.items() if isinstance(v, dict)} if isinstance(got, dict) else {}


def save_releases(rec: pathlib.Path, sources: dict) -> None:
    if "releases.json" in newer(rec):
        raise OSError("releases.json is from a newer version of Research")
    common.folder(rec / FOLDER)
    common.write_json(path(rec, "releases.json"), {"contract": FILES["releases.json"], "sources": sources})
