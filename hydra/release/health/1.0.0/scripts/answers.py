"""Health's answers.jsonl: one line a save. An answer's Undo takes its
line back out, so the file is byte for byte as before.

    {"at": "<ISO>", "question": "q-...", "words": "<their words>", "on": true, "by": "page"}   a typed answer
    {"at": "<ISO>", "question": "q-...", "pick": "<id>", "on": true|false, "by": "page"}       a pick, on or off

Where a question stands is its lines read in order: the newest typed answer counts, and a pick is on until a line
turns it off. A line marked "undone" takes back what was there. The typed words
stay in this file, in Health's own folder: say.json, home.json and the page's summary carry only that a question was
answered.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import common


def lines(rec) -> list:
    """Every sound line, oldest first."""
    return [a for a in common.read_jsonl(rec / "answers.jsonl")
            if isinstance(a.get("question"), str) and common.parse_time(a.get("at"))]


def state(rec) -> dict:
    """{question id: {"at", "words", "pick", "picks"}} for every question whose lines leave an answer standing.
    `at` is when the newest line that left it so was written."""
    out = {}
    for a in lines(rec):
        s = out.setdefault(a["question"], {"at": None, "words": None, "pick": None, "picks": []})
        pick = a.get("pick") if isinstance(a.get("pick"), str) else None
        if a.get("undone") is True:
            if pick is None:
                s.update(words=None, pick=None, picks=[])
            else:
                s["picks"] = [p for p in s["picks"] if p != pick]
                s["pick"] = None if s["pick"] == pick else s["pick"]
        elif isinstance(a.get("words"), str) and a["words"].strip():
            s["words"] = a["words"].strip()
        elif pick is not None and a.get("on") is False:
            s["picks"] = [p for p in s["picks"] if p != pick]
            s["pick"] = None if s["pick"] == pick else s["pick"]
        elif pick is not None:
            s["pick"] = pick
            s["picks"] = [p for p in s["picks"] if p != pick] + [pick]
        s["at"] = a["at"]
    return {q: s for q, s in out.items() if s["words"] or s["pick"] or s["picks"]}


def handed(rec, before) -> tuple:
    """(what the morning review is handed, the questions answered and not yet used, as say.json holds them, and every
    question with an answer standing). before: the last say.json, whose questions the answers are to."""
    asked = {q["id"]: q for q in (before or {}).get("questions") or [] if isinstance(q, dict) and isinstance(q.get("id"), str)}
    standing = state(rec)
    given = [{"question": asked[qid]["text"], "answer": s["words"][:120]} for qid, s in standing.items()
             if qid in asked and s["words"]]
    kept = []
    for qid, s in standing.items():
        mark = marker(asked[qid], s) if qid in asked else None
        if mark:
            kept.append(dict({k: v for k, v in asked[qid].items() if k != "answer"}, answer=mark))
    return given, kept, set(standing)


def marker(q: dict, s) -> dict | None:
    """What say.json holds for an answered question of its kind: never the typed words."""
    if not s:
        return None
    at = common.iso(common.parse_time(s["at"]))
    kind = q.get("kind", "words")
    if kind == "words" and s["words"]:
        return {"at": at, "words": True}
    if kind == "one" and s["pick"]:
        return {"at": at, "pick": s["pick"]}
    if kind == "multi" and s["picks"]:
        return {"at": at, "picks": list(s["picks"])}
    return None
