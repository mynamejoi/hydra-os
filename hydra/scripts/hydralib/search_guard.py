"""The morning review's search guard. A page that
searches the web declares `think.search` in its column.json: the path, from its root, of one file it ships, search/v1,
whose phrases and topics' words are its public words. Its input lists at most 12 queries in `data.searches`,
[{"id", "query"}], each one of its phrases holding one of its topics, then the month and the year, written by its code.
Claude never writes a query. Before Claude sees anything, `hydra think` lists only the
queries this guard passes, in code:

- plain: no control, format (zero-width, bidi, soft hyphen), private-use or unassigned character, and, folded (NFKC,
  casefold, accents dropped), only a-z, 0-9, spaces and - ' & , . ? in at most 200 characters;
- every word one of the page's shipped words or a month, and a digit only as a lone year, 1900 to 2099;
- no word, and no two or three neighbours joined, is the person's own: a word of their name or city (you.json), even
  one the page ships, or a word of yours/, of a page's quoted input or of a page's kept reads or store
  (<record>/think/, <record>/store/) that isn't a shipped word or a month. A word matches its plural and its possessive.

The review's fence (review_fence.py) then passes WebSearch only for exactly a listed query, so what leaves the Mac is
a general topic, "how to price handmade ceramics November 2026", never a name, a figure or anything typed.

  private_words(root, quoted=None)  {"always": their name's and city's words, "theirs": every other word of theirs}
  shipped(entry)                    a page's public words, from its think.search file; none when it has none
  check(root, page, query, ...)     (ok, why) for one query of a page's
  keep(root, entry, searches, ...)  the searches hydra think lists, [{"id", "query"}], and how many it left out
"""
import json
import os
import re
import subprocess
import unicodedata

from . import files, registry, you

MOST = 12  # searches a page lists in one review
LONGEST = 200  # characters in one query
FILE_MOST = 1024 * 1024  # a page's search file, and each file of theirs read for its words
KEPT_MOST = 8 * 1024 * 1024  # a page's kept reads, all together
MONTHS = frozenset(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                    "october", "november", "december"))
YEAR = re.compile(r"(?:19|20)[0-9]{2}")
PLAIN = re.compile(r"[a-z0-9 ,.?&'\-]+")
TOKEN = re.compile(r"[a-z]+|[0-9]+")
LETTERS = re.compile(r"[a-z]+")
SEARCH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")  # as think.save takes a part's id
HIDDEN = ("Cc", "Cf", "Co", "Cs", "Cn")  # control, format, private use, surrogate, unassigned
YOURS = ("sources.json", "goals.json", "settings.json")  # yours/, with layouts/ and claude.md


def fold(text):
    """A query as the guard reads it, or None when it holds a hidden character: NFKC, casefold, then accents dropped,
    so a full-width or decomposed letter reads as the letter itself."""
    if not isinstance(text, str) or any(unicodedata.category(c) in HIDDEN for c in text):
        return None
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def words(text):
    """Every run of letters in a text of theirs, folded as a query is. A hidden character in it is taken out, and a
    line break or a tab parts the words either side."""
    if not isinstance(text, str):
        return []
    text = "".join(" " if unicodedata.category(c) == "Cc" else "" if unicodedata.category(c) in HIDDEN else c
                   for c in text)
    return LETTERS.findall(fold(text) or "")


def stems(word):
    """A word and the forms it's matched by, so "bakers" and "baker's" match "baker", and "baker" matches them: its
    plural's singular, with the possessive's s a word of its own."""
    out = {word}
    if len(word) > 3 and word.endswith("s"):
        out.add(word[:-1])
    if len(word) > 4 and word.endswith("es"):
        out.add(word[:-2])
    if len(word) > 4 and word.endswith("ies"):
        out.add(word[:-3] + "y")
    return out


def _stemmed(found):
    return set().union(*(stems(w) for w in found)) if found else set()


def search_file(entry):
    """The path of a page's shipped search file, its column.json's think.search, or None: a .json path inside the
    page's own folder."""
    top = entry.get("root") if isinstance(entry, dict) else None
    if not isinstance(top, str) or not top:
        return None
    col = files.read_json(os.path.join(top, "column.json"), {})
    think = col.get("think") if isinstance(col, dict) else None
    rel = think.get("search") if isinstance(think, dict) else None
    if not isinstance(rel, str) or not rel.endswith(".json") or rel.startswith("/") or "\\" in rel \
            or ".." in rel.split("/"):
        return None
    path = os.path.join(top, rel)
    return path if files.within(path, top) else None


def shipped(entry):
    """A page's public words: every run of letters in its search file's phrases and its topics' words, split as the
    page's own code splits them (search/v1: re.findall(r"[a-z]+", text.lower())). None at all when the page declares
    no file, or its file isn't search/v1, so every query of its is left out."""
    path = search_file(entry)
    doc = files.read_json(path, None, cap=FILE_MOST) if path else None
    if not isinstance(doc, dict) or doc.get("contract") != "search/v1":
        return frozenset()
    texts = []
    phrases = doc.get("phrases")
    if isinstance(phrases, dict):
        texts += [p for some in phrases.values() if isinstance(some, list) for p in some if isinstance(p, str)]
    texts += [t["words"] for t in doc.get("topics") or [] if isinstance(t, dict) and isinstance(t.get("words"), str)]
    return frozenset(w for t in texts for w in re.findall(r"[a-z]+", t.lower()))


def _strings(value, out):
    """Every word of every string in a JSON value, its keys too, into out."""
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            out.update(words(v))
        elif isinstance(v, dict):
            stack += list(v.keys()) + list(v.values())
        elif isinstance(v, list):
            stack += v


def _text(path, most=FILE_MOST):
    try:
        if os.path.getsize(path) > most:
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _layouts(yours):
    """yours/layouts/<app>.json and each kept version of it, as paths."""
    out = []
    for top, _dirs, names in os.walk(os.path.join(yours, "layouts")):
        out += [os.path.join(top, n) for n in sorted(names) if n.endswith(".json")]
    return out


def _kept(record, inner="think"):
    """A page's kept files, <record>/<inner>/*.json, as JSON values, up to KEPT_MOST in all: in think/, People's and
    Inbox's planned reads, kept by their hook, and any answer a page keeps there; in store/, what a page keeps of them
    after its review clears think/, as Inbox's senders, subjects and events."""
    folder = os.path.join(record, inner)
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError:
        return []
    out, total = [], 0
    for n in names:
        path = os.path.join(folder, n)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if not os.path.isfile(path) or total + size > KEPT_MOST:
            continue
        total += size
        out.append(files.read_json(path, None, cap=KEPT_MOST))
    return out


def _inputs(root):
    """Each taking part page's input, {page id: its JSON}, run now as hydra think runs it, by page code alone."""
    from . import config as cfg, think  # loaded here, so think's own import of this module stays one way
    try:
        conf = cfg.load(root)
    except Exception:
        return {}
    out = {}
    for entry, spec in think.pages(root):
        try:
            code, text = think._run(conf, entry, spec["input"])
            doc = json.loads(text) if code == 0 and len(text) <= think.INPUT_MOST else None
        except (OSError, subprocess.SubprocessError, ValueError):
            doc = None
        if isinstance(doc, dict):
            out[entry["id"]] = doc
    return out


def private_words(root, quoted=None):
    """The words that never go in a search, for this home, folded as a query is read:
    "always": every word of the person's name and city (<root>/hydra/home/you.json), which no shipped word makes public;
    "theirs": every word of yours/ (its sources, goals, settings, layouts and claude.md), of each page's quoted input
    (quoted, {page id: its input}, or each page's input run now, as hydra think runs it) and of each installed page's
    kept reads and store (<record>/think/*.json and <record>/store/*.json)."""
    always = set()
    place = you.place(root) or {}
    for text in (you.name(root), place.get("city") if isinstance(place, dict) else None):
        always.update(words(text))
    theirs = set()
    yours = os.path.join(root, "yours")
    for name in YOURS:
        _strings(files.read_json(os.path.join(yours, name), None, cap=FILE_MOST), theirs)
    for path in _layouts(yours):
        _strings(files.read_json(path, None, cap=FILE_MOST), theirs)
    theirs.update(words(_text(os.path.join(yours, "claude.md"))))
    for doc in (quoted if quoted is not None else _inputs(root)).values():
        _strings(doc, theirs)
    for entry in registry.read(root).get("apps", []):
        record = entry.get("record") if isinstance(entry, dict) else None
        if entry.get("kind") != "main" and isinstance(record, str) and record:
            for doc in _kept(record) + _kept(record, "store"):
                _strings(doc, theirs)
    return {"always": frozenset(always), "theirs": frozenset(theirs)}


class _Lists:
    """One page's lists, made once for all its queries: its shipped words, and the stems of their words a query is
    refused for: their name's and city's always, every other word of theirs only when no shipped word or month shares
    its stem."""

    def __init__(self, words_shipped, private):
        self.shipped = frozenset(words_shipped)
        public = _stemmed(self.shipped) | set(MONTHS)
        self.always = _stemmed(private.get("always") or ())
        self.theirs = _stemmed([w for w in private.get("theirs") or () if not stems(w) & public])


def _verdict(query, lists):
    if not isinstance(query, str) or not query.strip():
        return False, "no query"
    if len(query) > LONGEST:
        return False, "longer than a search holds"
    folded = fold(query)
    if folded is None:
        return False, "a hidden character"
    if not PLAIN.fullmatch(folded):
        return False, "a character a search never holds"
    run = []  # the query's words in order, None where a year parts them
    for t in TOKEN.findall(folded):
        if t.isdigit():
            if not YEAR.fullmatch(t):
                return False, "a digit that isn't a lone year"
            run.append(None)
            continue
        if stems(t) & lists.always:
            return False, "a word of their own: %s" % t
        if t not in lists.shipped and t not in MONTHS:
            return False, "a word the page doesn't ship: %s" % t
        run.append(t)
    if not any(run):
        return False, "no word"
    mine = lists.always | lists.theirs
    for n in (2, 3):
        for i in range(len(run) - n + 1):
            part = run[i:i + n]
            if None not in part and stems("".join(part)) & mine:
                return False, "words of their own, joined: %s" % " ".join(part)
    return True, ""


def check(root, page, query, private=None, words_shipped=None):
    """(ok, why) for one query of an installed page's: whether hydra think may list it. private is private_words(root),
    made once for many queries, and words_shipped the page's shipped words, read from it when not given."""
    if words_shipped is None:
        entry = registry.app(root, page)
        words_shipped = shipped(entry) if entry and entry.get("kind") != "main" else frozenset()
    return _verdict(query, _Lists(words_shipped, private if private is not None else private_words(root)))


def keep(root, entry, searches, private):
    """The searches hydra think lists for a page, [{"id", "query"}] in the page's order, and how many it left out: each
    a {"id", "query"} with an id of a part's form, its query passing the guard, neither one a repeat, at most MOST."""
    lists = _Lists(shipped(entry), private)
    given = searches if isinstance(searches, list) else []
    kept, ids, queries = [], set(), set()
    for s in given:
        if len(kept) == MOST:
            break
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not SEARCH_ID.fullmatch(s["id"]):
            continue
        query = s.get("query")
        if s["id"] in ids or query in queries or not _verdict(query, lists)[0]:
            continue
        kept.append({"id": s["id"], "query": query})
        ids.add(s["id"])
        queries.add(query)
    return kept, len(given) - len(kept)
