"""Research's queries, written in code from its shipped public words and checked before any is listed. Claude never
writes a query: the morning review runs exactly
the ones listed here, and Hydra-OS's guard and fence check each again.

- **The shipped words** are search.json's (search/v1): the phrases for each question, each holding {topic} once, and the
  closed list of general topics. A word is a run of the letters a to z, as re.findall(r"[a-z]+", s.lower()) finds it,
  the one way Hydra-OS's guard reads them too.
- **A query** is a phrase with {topic} filled, a space, the month in words, a space and the year: "how to price handmade
  ceramics November 2026". Never a day, a name or anything typed.
- **The check,** the guard's own rule, before a query is listed:
  - plain text: letters and single spaces, and no digit but the lone year;
  - every word is a shipped word, a month or the year;
  - no word, alone or joined to the words beside it, is the person's own: their name, their city, or any word of
    theirs that isn't a shipped word (a goal's words, a project's name and line, a note's words). Their name and city
    win over shipped words.
  A query that fails is never listed.
- **A project's general topics** are matched here, on this Mac, from its own words (best_topics): every topic whose
  own words all appear in it, the most specific first, up to three; else the one topic that shares a rare word with it
  and scores clearly best; else none. Ordinary words ("a", "the", "for") never count, and words too general to pick a
  topic alone ("open", "start", "grow") count only beside the rest of a topic's words.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt
import math
import pathlib
import re

import common

FILE = common.ROOT / "scripts" / "search.json"
QUESTIONS = ("learn", "sell", "new", "opportunities", "gaps", "skills")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
WORD = re.compile(r"[a-z]+")
PLAIN = re.compile(r"[A-Za-z]+(?: [A-Za-z]+)* (?:19|20)\d\d")
JOIN = 3   # words joined to their neighbours, at most: "craft fair" joined is "craftfair"
FUNCTION = frozenset("a an and as at by for from in into of on or the to with my our your their its this that".split())
GENERIC = frozenset("open start build make grow learn sell write launch run get better new first next more own help up "
                    "pop life work over after early self personal high basic basics one".split())
MOST_TOPICS = 3
RARE = 2   # a word in at most this many topics is rare enough to pick one alone


def load(path: pathlib.Path = FILE) -> dict:
    doc = common.load_json(path, {}) or {}
    if not isinstance(doc, dict) or doc.get("contract") != "search/v1":
        raise ValueError("search.json isn't search/v1")
    return doc


def words_of(text: str) -> list:
    return WORD.findall(str(text).lower())


def shipped(doc: dict) -> set:
    """Every word Research ships for its queries."""
    out = set()
    for ps in (doc.get("phrases") or {}).values():
        for p in ps:
            out.update(words_of(p))
    for t in doc.get("topics") or []:
        out.update(words_of(t.get("words", "")))
    return out


def topics(doc: dict) -> dict:
    """{topic id: its words}, in search.json's order."""
    return {t["id"]: t["words"] for t in doc.get("topics") or [] if isinstance(t, dict) and t.get("id")}


def stem(w: str) -> str:
    """A word without its plural ending: "classes" is "class", "stories" is "story", "mugs" is "mug"."""
    if len(w) <= 3:
        return w
    for end, put in (("ies", "y"), ("sses", "ss"), ("xes", "x"), ("ches", "ch"), ("shes", "sh")):
        if w.endswith(end):
            return w[: -len(end)] + put
    return w[:-1] if w.endswith("s") and not w.endswith(("ss", "us", "is")) else w


def forms(w: str) -> set:
    """A word and its -ing forms, so "hike" meets "hiking", "run" meets "running" and "write" meets "writing"."""
    out = {w}
    if len(w) >= 3 and not w.endswith("ing"):
        out.add(w + "ing")
        if w.endswith("e") and not w.endswith("ee"):
            out.add(w[:-1] + "ing")
        if len(w) <= 4 and w[-1] not in "aeiouwxy" and w[-2] in "aeiou" and w[-3] not in "aeiou":
            out.add(w + w[-1] + "ing")
    return out


def topic_index(doc: dict) -> tuple:
    """({topic id: its own words, each without its plural ending}, {word: how rare it is among the topics})."""
    own = {tid: {stem(w) for w in words_of(words) if w not in FUNCTION} for tid, words in topics(doc).items()}
    count = {}
    for ws in own.values():
        for w in ws:
            count[w] = count.get(w, 0) + 1
    return own, count


def best_topics(text: str, doc: dict) -> list:
    """The general topics a project's own words match, as ids, at most three, best first (the module's note)."""
    own, count = topic_index(doc)
    order = list(own)
    base = [stem(w) for w in words_of(text) if w not in FUNCTION]
    have = {f for w in base for f in forms(w)}
    full = [t for t in order if own[t] and own[t] <= have]
    weight = {w: math.log(len(own) / n) for w, n in count.items()}
    if full:
        full.sort(key=lambda t: (-len(own[t]), -sum(weight[w] for w in own[t]), order.index(t)))
        return full[:MOST_TOPICS]
    rare = {f for w in base if w not in GENERIC for f in forms(w)}
    scored = []
    for t in order:
        shared = own[t] & rare
        if shared and min(count[w] for w in shared) <= RARE:
            scored.append((sum(weight[w] for w in shared), order.index(t), t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0] + 1e-9):
        return [scored[0][2]]
    return []


def query(phrase: str, topic_words: str, day: dt.date) -> str:
    return f"{phrase.replace('{topic}', topic_words)} {common.month_words(day)}"


def own_words(root: pathlib.Path, rec: pathlib.Path, extra=()) -> tuple:
    """(the person's name and city words, which win over shipped words; every other word of theirs Research can see):
    you.json's name and city, the goals' words, and Research's own store of what they typed (projects, notes)."""
    you = common.load_json(root / "hydra" / "home" / "you.json", {}) or {}
    strong = set(words_of(you.get("name", ""))) if isinstance(you, dict) else set()
    place = you.get("place") if isinstance(you, dict) else None
    if isinstance(place, dict):
        strong.update(words_of(place.get("city", "")))
    weak = set()
    goals = common.load_json(root / "yours" / "goals.json", {}) or {}
    for g in goals.get("goals") or [] if isinstance(goals, dict) else []:
        if isinstance(g, dict):
            weak.update(words_of(g.get("text", "")))
    import store  # noqa: PLC0415  (store imports search for its topics)
    for p in store.all_projects(rec, root):
        weak.update(words_of(p.get("name", "")))
        weak.update(words_of(p.get("line", "")))
    for n in store.notes(rec):
        weak.update(words_of(n.get("title", "")))
    for text in extra:
        weak.update(words_of(text))
    return strong, weak


def problem(q: str, doc: dict, own: tuple, year: int | None = None) -> str:
    """Why a query can't be listed, in words, or "" when it can."""
    if not isinstance(q, str) or not PLAIN.fullmatch(q) or q != " ".join(q.split()):
        return "it isn't plain words and a year"
    parts = q.split(" ")
    if year is not None and parts[-1] != str(year):
        return "its year isn't this one"
    ws = [w.lower() for w in parts[:-1]]
    allowed = shipped(doc)
    for w in ws:
        if w not in allowed and w not in MONTHS:
            return "a word isn't one Research ships"
    strong, weak = own
    mine = strong | (weak - allowed)
    for i in range(len(ws)):
        for n in range(1, JOIN + 1):
            joined = "".join(ws[i:i + n])
            if i + n <= len(ws) and joined in mine:
                return "a word is the person's own"
    return ""
