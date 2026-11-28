"""Research's part in the morning review, the one step of Research's that needs Claude
(column.json's `think`). The tick's run reads release notes and
notes in code; once a week the "Hydra-OS morning review" task runs `hydra think`, which runs these from Research's
plugin with Hydra-OS's Python:

    python3 scripts/think.py --input --record DIR                  # {"ask", "data"}, or {} with nothing to search
    python3 scripts/think.py --save --part s01 --record DIR < one search's answer, as Hydra-OS hands it in
    python3 scripts/think.py --save --part finds --record DIR < the finds, as JSON
    python3 scripts/think.py --save --done --record DIR            # the page, Home's facts and the offer, drawn again

- **--input** gives the week's searches (plan.py) as data.searches, [{"id", "query"}], at most 6, each written in code
  from Research's shipped words. Claude runs exactly those. With them, each project's id and its general topics, given
  as data: never a project's name, a goal's words or anything else the person typed. It prints {} when there's
  nothing to search: no project has a topic, this week's scout is done, or the morning review is off.
- **--save --part s01** keeps one search's links. Hydra-OS's hook keeps WebSearch's own result for each listed search
  and hands it in just before done as {"query", "answer", "kept"}, so web text never passes
  through Claude's typing; Claude's own {"tool": "WebSearch", "input": {"query"}, "answer"} is taken too. The query must
  be exactly the one listed for that id (case and spacing evened). Only the https links are kept, none of the text. A
  search that wasn't run writes nothing, so it's searched again the next morning.
- **--save --part finds** takes up to six finds, each about one project and one of the six questions, in plain words,
  with no one's name, no city, no project's name and no advice. A find that fails is left out and why is said; the rest
  are held, and saved again, the newest stand.
- **--save --done** keeps each held find whose sources all came back from this week's searches, marks the scout done,
  takes the searches' links out of think/, and draws say.json, home.json, the angles offer and the page again. Its line
  says when any search that didn't come back runs again, and that there's nothing more to do this morning, so a
  review whose searches didn't come back doesn't run them again the same morning.

Each prints one line and exits 0, or 2 with why nothing was saved. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

import common
import plan as planner
import search
import store

PART = re.compile(r"s(0[1-9]|1[0-2])")   # up to s12, which a week planned before the cap of six may list
MOST = 8 * 1024 * 1024
MOST_FINDS = 6
HELD = "held.json"   # the finds saved before done, each kept at done if its sources came back from this week's searches
QUESTIONS = search.QUESTIONS
FIELDS = ("who", "pay", "where", "else")
LIMITS = {"line": 80, "short": 30, "move": 100, "why": 140}
URL = re.compile(r"https://[^\s\"'<>\\)\]}]+")
MARKUP = re.compile(r"<[A-Za-z!/?]|&#?[A-Za-z0-9]+;")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
ADVICE = re.compile(r"\b(invest\w*|stocks?|shares|crypto\w*|trad(e|ing) (stocks|options)|diagnos\w*|dosage|doses?|"
                    r"supplements?|medicines?|medication\w*|prescri\w*|you should|lawsuit|legal advice)\b", re.I)
# The ask names Research's id, learning, and asks for one save, its finds, the way the review's own guidance says,
# which is Hydra-OS's to set. Hydra-OS's hook keeps each listed search's result and hands it in before done, so
# Claude never copies web text into a save. The id is spelled out, since a model left to name the page can take its
# title instead. The tests hold the guidance's printed form, so a change there shows here.
ASK = ("Research's weekly scout. Its page id is learning: use it, never the title. First, for each search in "
       "data.searches, one at a time, run WebSearch with exactly its query, in standard mode and with no domain filter. "
       "Hydra-OS keeps what each search returns for Research, so don't save the searches. Then, from those results "
       "alone, write up to six finds, each one thing worth doing for one of data.projects, about one of data.questions: "
       "{\"project\": \"<its id>\", \"question\": \"<the question's key>\", \"field\": \"<for sell only: who, pay, "
       "where or else>\", \"line\": \"<what it changes for them, one plain sentence of at most 80 characters>\", "
       "\"short\": \"<a few words for a table cell, at most 30 characters>\", \"move\": \"<one thing to do, at most "
       "100 characters>\", \"why\": \"<why, from the result, at most 140 characters>\", \"sources\": [\"<the "
       "result's https link>\"]}. Plain words, no one's name, no city, nothing about money to invest, health treatment "
       "or the law. Save them as Research's part finds, the way this review's guidance says: {\"finds\": [...]}. Then "
       "mark Research done, as the guidance says. Use no tool but WebSearch and that save.")
QUESTION_WORDS = {"learn": "what to learn next", "sell": "how it could sell: who buys, what they pay, where they are, "
                  "who else sells it", "new": "what's new around it", "opportunities": "grants, competitions, "
                  "partnerships or openings", "gaps": "what it's missing that others have", "skills": "Claude skills "
                  "or tools worth using for it"}


class Refused(Exception):
    """Why nothing was saved, in one plain line."""


def folder(rec: pathlib.Path) -> pathlib.Path:
    return rec / planner.THINK


def searched(rec: pathlib.Path) -> set:
    return {p.stem for p in folder(rec).glob("s*.json") if PART.fullmatch(p.stem)} if folder(rec).is_dir() else set()


def due(rec: pathlib.Path, root: pathlib.Path, now) -> list:
    """The searches to offer now: this week's, made if none was, or one catch-up of the missing ones the next morning."""
    if common.review_off(root):
        return []
    p = planner.this_week(rec, now)
    today = now.astimezone().date().isoformat()
    if not p:
        if not any(x.get("topics") for x in store.all_projects(rec, root)):
            return []
        p = planner.make(rec, root, now)
        return p["searches"]
    have = set(p.get("searched") or []) | searched(rec)
    missing = [s for s in p["searches"] if s["id"] not in have]
    if not p.get("done"):
        return missing
    made = str(p.get("made_at", ""))[:10]
    if missing and today > made and not p.get("caught_up"):
        p["caught_up"] = today
        p["done"] = False
        planner.save(rec, p)
        return missing
    return []


def ask_doc(rec: pathlib.Path, root: pathlib.Path, now) -> dict:
    todo = due(rec, root, now)
    if not todo:
        return {}
    doc = search.load()
    names = search.topics(doc)
    pids = list(dict.fromkeys(s["project"] for s in planner.this_week(rec, now).get("searches") or []))
    projects = []
    for p in store.all_projects(rec, root):
        if p["id"] in pids:
            projects.append({"id": p["id"], "topics": [names[t] for t in p.get("topics") or [] if t in names]})
    return {"ask": ASK, "data": {"searches": [{"id": s["id"], "query": s["query"]} for s in todo], "projects": projects,
                                 "questions": QUESTION_WORDS, "most": MOST_FINDS}}


def same(a: str, b: str) -> bool:
    return " ".join(str(a).lower().split()) == " ".join(str(b).lower().split())


def links_of(answer) -> list:
    """The https links in a search's answer, whatever its shape: WebSearch's own result isn't documented, so it's read
    as text. Only the links are kept; none of the web text is."""
    try:
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    except (TypeError, ValueError):
        return []
    return sorted({u.rstrip(".,;:") for u in URL.findall(text)})


def save_search(rec: pathlib.Path, now, part: str, text: str) -> str:
    """One listed search's answer, as its part. Two shapes: the main plugin's, {"query", "answer", "kept"}, as its hook
    kept WebSearch's result and hands it in before done, the review's way; and Claude's own,
    {"tool": "WebSearch", "input": {"query"}, "answer"}. Either way only the links are kept. A search that wasn't run
    writes nothing, so it's searched again the next morning."""
    p = planner.this_week(rec, now)
    want = next((s for s in p.get("searches") or [] if s["id"] == part), None)
    if want is None:
        raise Refused(f"{part} isn't one of this week's searches.")
    try:
        got = json.loads(text)
    except ValueError:
        raise Refused("That isn't JSON. Save the search's answer as the ask shows.") from None
    if isinstance(got, dict) and "kept" in got:   # the main plugin's
        if set(got) - {"query", "answer", "kept"} or not isinstance(got.get("query"), str):
            raise Refused("A kept search is {\"query\", \"answer\", \"kept\"}.")
        if not same(got["query"], want["query"]):
            raise Refused(f"That isn't the query listed for {part}.")
        if got.get("kept") is not True or got.get("answer") is None:
            return f"{part} wasn't run, so it's searched again the next morning."
    elif isinstance(got, dict) and got.get("tool") == "WebSearch" and isinstance(got.get("input"), dict):   # Claude's
        if set(got["input"]) != {"query"} or not same(got["input"].get("query", ""), want["query"]):
            raise Refused(f"That isn't the query listed for {part}.")
    else:
        raise Refused("A search's answer is {\"query\", \"answer\", \"kept\"}, as Hydra-OS keeps it.")
    urls = links_of(got.get("answer"))
    common.folder(folder(rec))
    common.write_json(folder(rec) / f"{part}.json", {"query": want["query"], "urls": urls, "at": common.iso(now)})
    return f"Saved {part}: {len(urls)} links."


def markers(rec: pathlib.Path, root: pathlib.Path) -> tuple:
    """(the person's name and city words, the phrases a find may never hold: each project's name and each note's title)."""
    strong, _ = search.own_words(root, rec)
    phrases = [" ".join(search.words_of(p.get("name", ""))) for p in store.all_projects(rec, root)]
    phrases += [" ".join(search.words_of(n.get("title", ""))) for n in store.notes(rec)]
    return strong, [x for x in phrases if x]


def plain(s, most: int) -> bool:
    return (isinstance(s, str) and 0 < len(s) <= most and s == " ".join(s.split()) and not MARKUP.search(s)
            and not EMOJI.search(s) and "—" not in s and "–" not in s)


def problem(f, plan: dict, urls, mark: tuple) -> str:
    """Why a find can't be kept, in words, or "". urls None: every check but whether each source is a link this week's
    searches returned, which done makes once the searches are in."""
    if not isinstance(f, dict):
        return "it isn't a find"
    pids = {s["project"] for s in plan.get("searches") or []}
    if f.get("project") not in pids:
        return "its project isn't one this week's scout searched for"
    if f.get("question") not in QUESTIONS:
        return "its question isn't one of the six"
    if f.get("question") == "sell" and f.get("field") not in (None, "", *FIELDS):
        return "its field isn't who, pay, where or else"
    for k, most in LIMITS.items():
        if not plain(f.get(k), most):
            return f"its {k} isn't one plain line of at most {most} characters"
    src = f.get("sources")
    if not isinstance(src, list) or not 1 <= len(src) <= 3 or not all(isinstance(u, str) for u in src):
        return "it needs one to three sources"
    if not all(u.rstrip(".,;:").startswith("https://") for u in src):
        return "a source isn't an https link"
    if urls is not None and not all(u.rstrip(".,;:") in urls for u in src):
        return "a source isn't a link this week's searches returned"
    text = " ".join(str(f.get(k)) for k in LIMITS)
    if ADVICE.search(text):
        return "it reads as advice about money, health or the law"
    ws = search.words_of(text)
    strong, phrases = mark
    if any(w in strong for w in ws):
        return "it holds a name or a place of the person's"
    joined = " " + " ".join(ws) + " "
    if any(f" {p} " in joined for p in phrases):
        return "it holds one of the person's own names for a project or a note"
    return ""


def save_finds(rec: pathlib.Path, root: pathlib.Path, now, text: str) -> str:
    p = planner.this_week(rec, now)
    if not p:
        raise Refused("There's no scout this week to keep finds for.")
    try:
        got = json.loads(text)
    except ValueError:
        raise Refused("That isn't JSON. Save {\"finds\": [...]} as the ask shows.") from None
    items = got.get("finds") if isinstance(got, dict) else None
    if not isinstance(items, list):
        raise Refused("Save {\"finds\": [...]} as the ask shows.")
    mark = markers(rec, root)
    doc = search.load()
    kept, why = [], []
    for f in items[:MOST_FINDS]:
        bad = problem(f, p, None, mark)   # each source against this week's links at done, once Hydra-OS hands them in
        if bad:
            why.append(bad)
            continue
        topic = next((s["topic"] for s in p["searches"] if s["project"] == f["project"] and s["question"] == f["question"]),
                     next(s["topic"] for s in p["searches"] if s["project"] == f["project"]))
        sources = [{"url": u.rstrip(".,;:"), "site": re.sub(r"^www\.", "", u.split("/")[2])} for u in f["sources"]]
        kept.append({"id": store.new_id("f", p["week"], f["project"], f["question"], f["line"]), "week": p["week"],
                     "project": f["project"], "topic": topic if topic in search.topics(doc) else "",
                     "question": f["question"], "field": f.get("field") or "", "line": f["line"], "short": f["short"],
                     "move": f["move"], "why": f["why"], "sources": sources, "kept_at": common.iso(now)})
    common.folder(folder(rec))
    common.write_json(folder(rec) / HELD, {"week": p["week"], "finds": kept, "at": common.iso(now)})
    said = f"Took {len(kept)} of {len(items[:MOST_FINDS])} finds. Each is kept at done if its sources came back from this week's searches."
    return said + (f" Left out: {'; '.join(dict.fromkeys(why))}." if why else "")


def week_links(rec: pathlib.Path) -> set:
    urls = set()
    for part in sorted(folder(rec).glob("s*.json")):
        if PART.fullmatch(part.stem):
            got = common.load_json(part, {})
            urls.update(u for u in (got.get("urls") if isinstance(got, dict) else None) or [] if isinstance(u, str))
    return urls


def done(rec: pathlib.Path, root: pathlib.Path, now) -> str:
    p = planner.this_week(rec, now)
    if not p:
        raise Refused("There's no scout this week to finish.")
    held = common.load_json(folder(rec) / HELD, None)
    dropped = 0
    if isinstance(held, dict) and held.get("week") == p["week"] and isinstance(held.get("finds"), list):
        urls = week_links(rec)   # the searches Hydra-OS handed in just before this step
        good = [f for f in held["finds"] if isinstance(f, dict) and f.get("sources")
                and all(isinstance(s, dict) and s.get("url") in urls for s in f["sources"])]
        dropped = len(held["finds"]) - len(good)
        store.keep_finds(rec, dt.date.fromisoformat(p["week"]), good)
    p["searched"] = sorted(set(p.get("searched") or []) | searched(rec))
    p["done"] = True
    p["finished_at"] = common.iso(now)
    planner.save(rec, p)
    if folder(rec).is_dir():
        for part in folder(rec).glob("s*.json"):
            if PART.fullmatch(part.stem):
                part.unlink()
        (folder(rec) / HELD).unlink(missing_ok=True)
    import draw  # noqa: PLC0415
    draw.everything(rec, root, now)
    kept = sum(1 for f in store.finds(rec) if f.get("week") == p["week"])
    missing = len(p["searches"]) - len(p["searched"])
    later = ("" if not missing else " The searches that didn't come back run again tomorrow morning."
             if not p.get("caught_up") else " The searches that didn't come back wait for next Monday's scout.")
    return (f"Done: {len(p['searched'])} of {len(p['searches'])} searches, {kept} finds kept."
            + (f" {dropped} left out: a source didn't come back from this week's searches." if dropped else "")
            + later + " Nothing more to do for Research this morning.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{common.TITLE}'s part in the morning review.")
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
    if a.input:
        doc = ask_doc(rec, root, now) if rec.is_dir() else {}
        sys.stdout.buffer.write((json.dumps(doc, ensure_ascii=False) + "\n").encode("utf-8"))
        return 0
    try:
        if not rec.is_dir():
            raise Refused(f"{common.TITLE} isn't set up here, so nothing was saved.")
        if common.review_off(root):
            raise Refused("The morning review is off, so nothing was saved.")
        if a.done:
            line = done(rec, root, now)
        else:
            text = sys.stdin.read(MOST + 1)
            if len(text.encode("utf-8")) > MOST:
                raise Refused("That answer is longer than Research takes.")
            if a.part == "finds":
                line = save_finds(rec, root, now, text)
            elif a.part and PART.fullmatch(a.part):
                line = save_search(rec, now, a.part, text)
            else:
                raise Refused("Save each search with --part s01 to s12, then the finds with --part finds.")
    except Refused as e:
        print(str(e))
        return 2
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
