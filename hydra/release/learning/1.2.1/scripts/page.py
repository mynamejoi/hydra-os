"""Research's page: one page, a list of blocks, drawn by Hydra-OS's own kit. This script works
Research's datasets out in code and hands them to the kit, which draws the page from layout.json and say.json and
writes page/data/, page/index.html and page/summary.json. It makes no model call and no request.

    python3 scripts/page.py [--record DIR] [--now ISO] [--run ISO|by-hand]

The blocks: This week, the finds, a move a project; Your projects, a table of each project and its general topic by
the six questions, with the field that adds one and a goal's Don't scout; How to sell it, the project closest to
selling in five cells; What changed in Claude's tools, the newest release-note lines; Your notes; then Claude asks,
which stays quiet since Research asks nothing, and Where this comes from. A project's name and a note's title are the
person's own words: they show here, from Research's store, and never go in say.json or home.json.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import os
import sys

import common
import plan as planner
import say as say_file
import search
import store

SELL = (("who", "Who buys"), ("pay", "What they pay"), ("where", "Where they are"), ("else", "Who else sells it"),
        ("proof", "Proof"))
KEY = [{"state": "no", "label": "Not answered yet"}, {"state": "one", "label": "One source"},
       {"state": "two", "label": "Two or more"}]
NEVER = "Research never searches your name, your city or anything you typed."
# Empty states, plain, one idea a line: what shows here, then when it fills or what to do. The first block's is the
# next step.
WEEK_EMPTY = "Each Monday's finds show here, with one move for each project."
GOALS_NOTE = "Your goals are scouted too, each by its general topic. Don't scout takes one off."
ROWS = 8
PROJECT_ROWS = 20   # the kit's most for a table


class NoKit(Exception):
    pass


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


def site_of(url: str) -> str:
    host = url.split("/")[2] if url.count("/") >= 2 else url
    return host[4:] if host.startswith("www.") else host


def state_of(n: int) -> str:
    return "no" if n == 0 else "one" if n == 1 else "two"


def week_block(rec, root, now, ps: list) -> dict:
    finds, week = say_file.week_finds(rec, now)
    names = {p["id"]: p["name"] for p in ps}
    rows, seen = [], set()
    for f in finds:
        if f["project"] in seen or f["project"] not in names or len(rows) >= ROWS:
            continue
        seen.add(f["project"])
        src = next((s for s in f.get("sources") or [] if isinstance(s, dict)), {})
        row = {"id": f["id"], "title": names[f["project"]], "tag": say_file.QN[f["question"]], "line": f["line"],
               "move": {"text": f["move"], "why": f["why"]}, "when": common.day_words(dt.date.fromisoformat(f["week"]))}
        if str(src.get("url", "")).startswith("https://"):
            row["link"] = {"href": src["url"], "text": f"Source: {src.get('site') or site_of(src['url'])}"}
        rows.append(row)
    state = say_file.state_line(rec, root, now, ps, finds)
    off = common.review_off(root)   # then the header says it fills in once the review is back on, so this block doesn't
    line = WEEK_EMPTY if off else state or say_file.NOTHING
    empty = {"icon": "scope", "line": line, "via": "" if off else say_file.NEXT.get(line, "")}
    return {"rows": rows, "caption": f"{state} {say_file.NEXT.get(state, '')}".strip() if rows and state and not off else "",
            "empty": empty}


def cells_for(rec, p: dict) -> dict:
    """{question: how many sites the last twelve weeks' finds rest on} for one project."""
    out = {}
    for f in store.finds(rec):
        if f.get("project") == p["id"]:
            sites = out.setdefault(f.get("question"), set())
            sites.update(s.get("site") for s in f.get("sources") or [] if isinstance(s, dict))
    return {q: len(v) for q, v in out.items()}


def topic_label(p: dict, names: dict) -> str:
    """A project's row: its name, then its first general topic, or that it has none yet."""
    t = next((t for t in p.get("topics") or [] if t in names), None)
    words = names[t] if t else "no general topic yet"
    return f"{p['name']} · {words[:1].upper() + words[1:] if t else words}"


def projects_block(rec, ps: list) -> dict:
    names = search.topics(search.load())
    rows = []
    for p in ps[:PROJECT_ROWS]:
        n = cells_for(rec, p)
        row = {"id": p["id"], "label": topic_label(p, names),
               "cells": [{"state": state_of(n.get(q, 0))} for q in search.QUESTIONS]}
        if p.get("by") == "goal":   # a goal is scouted by default, so its row says how to stop
            row["acts"] = [{"action": "skip-goal", "words": "Don't scout", "fields": {"goal": p["from_goal"]}}]
        rows.append(row)
    known = sum(1 for r in rows for c in r["cells"] if c["state"] != "no")
    more = len(ps) - len(rows)
    caption = " ".join(x for x in (GOALS_NOTE if any(p.get("by") == "goal" for p in ps) else "",
                                   f"{more} more {'isn' if more == 1 else 'aren'}'t shown." if more > 0 else "") if x)
    return {"columns": [{"id": q, "label": say_file.QN[q]} for q in search.QUESTIONS], "rows": rows, "key": KEY,
            "label": (f"Your {len(ps)} project{'' if len(ps) == 1 else 's'} by the six questions: {known} of "
                      f"{6 * len(rows)} answered so far.") if rows else "No project yet.",
            "caption": caption,
            "entry": {"label": "Add a project", "placeholder": "Its name, then Return", "fixed": {}},
            "empty": {"icon": "scope", "line": "Your goals and each project you name get a row here.",
                      "via": "Its cells fill in as the scout finds answers."}}


def sell_block(rec, ps: list) -> dict:
    """The project closest to selling: the one whose sell finds fill the most of the five cells."""
    best, best_n, cells = None, -1, {}
    for p in ps:
        got = {}
        for f in sorted(store.finds(rec), key=lambda f: f.get("kept_at", "")):
            if f.get("project") == p["id"] and f.get("question") == "sell" and f.get("field") in ("who", "pay", "where", "else"):
                c = got.setdefault(f["field"], {"sites": set(), "text": ""})
                c["sites"].update(s.get("site") for s in f.get("sources") or [] if isinstance(s, dict))
                c["text"] = f.get("short", "")
        proof = [n for n in store.notes(rec) if set(n.get("topics") or []) & set(p.get("topics") or [])]
        if proof:
            got["proof"] = {"sites": {"note"}, "text": "From your own notes"}
        if len(got) > best_n:
            best, best_n, cells = p, len(got), got
    rows = []
    if best is not None:
        rows.append({"id": best["id"], "label": best["name"],
                     "cells": [dict({"state": state_of(len(cells[k]["sites"]))}, **({"text": cells[k]["text"]} if cells.get(k, {}).get("text") else {}))
                               if k in cells else {"state": "no"} for k, _ in SELL]})
    return {"columns": [{"id": k, "label": n} for k, n in SELL], "rows": rows, "key": KEY,
            "label": "How the project closest to selling could sell, in five parts." if rows else "No project yet.",
            "empty": {"icon": "store", "line": "How your closest project could sell, in five parts.",
                      "via": "It fills in from Monday's scout."}}


def releases_block(rec, now) -> dict:
    kept = store.releases(rec)
    rows = []
    for sid, s in kept.items():
        for line in [x for x in s.get("lines") or [] if isinstance(x, dict)]:
            fp = hashlib.sha256(f"{sid}|{line.get('text', '')}".encode("utf-8")).hexdigest()[:8]
            rows.append({"id": f"r-{fp}", "title": s.get("name", ""), "line": line.get("text", ""),
                         "when": common.day_words(dt.date.fromisoformat(line["seen"])) if line.get("seen") else "",
                         "link": {"href": s.get("link", ""), "text": f"Source: {site_of(s.get('link', ''))}"},
                         "_seen": line.get("seen", "")})
    rows.sort(key=lambda r: r["_seen"], reverse=True)
    rows = [{k: v for k, v in r.items() if k != "_seen"} for r in rows[:ROWS]]
    today = now.astimezone().date().isoformat()
    failed = [s for s in kept.values() if str(s.get("checked_at", ""))[:10] == today and not s.get("ok")]
    caption = ""
    if failed:
        last = max((str(s.get("read_at", ""))[:10] for s in kept.values() if s.get("read_at")), default="")
        caption = ("Couldn't reach the release notes this morning. These are from "
                   f"{common.day_words(dt.date.fromisoformat(last))}.") if last else "Couldn't reach the release notes this morning."
    return {"rows": rows, "caption": caption,
            "empty": {"icon": "notes", "line": "What changed in Claude's tools shows here.",
                      "via": "It's read each morning from the public release notes."}}


def notes_block(rec, ps: list) -> dict:
    scouted = {t for p in ps for t in p.get("topics") or []}
    rows = [{"id": n["id"], "title": n["title"], "tag": "Used" if set(n.get("topics") or []) & scouted else "Not used yet",
             "when": common.day_words(common.parse_time(n["added"]).date()) if common.parse_time(n.get("added")) else ""}
            for n in sorted(store.notes(rec), key=lambda n: n.get("added", ""), reverse=True)[:ROWS]]
    return {"rows": rows,
            "empty": {"icon": "file", "line": "Your notes back what the scout finds.",
                      "action": "drop", "drop": "Drop a note here: a .md or .txt file.",
                      "via": "Each note stays on this Mac."}}   # under the drop place, not as a hint, which the kit would show as one more tip


def connections(rec, now) -> dict:
    p = planner.load(rec)
    when = common.parse_time(p.get("finished_at")) if p else None
    foot = f"Scouted {common.day_words(when.date())}. {NEVER}" if when else NEVER
    return {"title": "Where this comes from",
            "rows": [{"line": "Claude's own web search, in general words from a fixed list of topics", "icon": "world"},
                     {"line": "Public release notes: Claude Code, the Claude app, the Claude API and the plugin marketplace",
                      "icon": "notes"},
                     {"line": "Your notes, kept on this Mac", "icon": "file"},
                     {"app": "goals", "what": "your goals that no other page counts, each by its general topic"}],
            "foot": foot, "drop": "Drop another note here: a .md or .txt file."}


def datasets(rec, root, now) -> dict:
    ps = store.all_projects(rec, root)
    header = {"line": say_file.OFF} if common.review_off(root) else {}   # one plain line, with no button
    return {"header": header, "week": week_block(rec, root, now, ps), "projects": projects_block(rec, ps),
            "sell": sell_block(rec, ps), "releases": releases_block(rec, now), "notes": notes_block(rec, ps),
            "questions": {}, "connections": connections(rec, now)}


def header_move(rec, root):
    """What the page leads with, in its header (every page leads in one place: the lead move right under the crumb,
    with its why under it): this week's first move and its why, as say.json has it, else nothing, so the header's line
    is the week's state alone. With suggestions off in their settings, the week's first find alone, with no move."""
    doc = say_file.load(rec) or {}
    first = next((s for s in doc.get("suggestions") or [] if isinstance(s, dict) and isinstance(s.get("text"), str)
                  and s["text"].strip()), None)
    if first is None:
        return None
    settings = common.load_json(root / "yours" / "settings.json", {}) or {}
    if isinstance(settings, dict) and settings.get("suggestions") is False:
        lead = next((i for i in doc.get("insights") or [] if isinstance(i, dict) and i.get("id") == "i-week"
                     and isinstance(i.get("text"), str) and i["text"].strip()), None)
        return {"text": lead["text"], "label": lead["text"]} if lead else None
    why = first.get("why") if isinstance(first.get("why"), str) else ""
    return {"text": first["text"], "why": why, "label": first["text"]}


def build(rec, root, now, run: str = "by-hand") -> dict:
    kit = load_kit(root)
    return kit.build(str(common.ROOT), str(rec), root=str(root), now=now, run=run, data=datasets(rec, root, now),
                     move=header_move(rec, root) or "")


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
        print(f"page: {common.TITLE}'s folder isn't there yet.", file=sys.stderr)
        return 1
    root = common.root_of(rec)
    now, run = common.now(a.now), a.run or last_run(rec)
    try:
        try:
            got = build(rec, root, now, run)
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ != "KitError":
                raise
            heal(rec, root, now)   # a say.json the kit won't draw is written again from the store, then drawn once more
            got = build(rec, root, now, run)
    except NoKit as e:
        print(f"page: not drawn: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ != "KitError":
            raise
        print(f"page: not drawn: the kit refused it: {e}", file=sys.stderr)
        return 1
    print(f"page: {common.tilde(got['path'])}: {got['blocks']} blocks")
    return 0


def heal(rec, root, now) -> None:
    """say.json, and home.json from it, written again from the store."""
    import home as home_file   # not at the top: home.py's own imports stay clear of the page
    doc = say_file.compose(rec, root, now)
    say_file.write(rec, doc)
    home_file.build(rec, root, now, doc)


if __name__ == "__main__":
    sys.exit(main())
