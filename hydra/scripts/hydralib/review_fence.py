"""The morning review's fence. From the moment a session
runs `hydra think` until it saves the review's last part, or 30 minutes pass, that session may use only two things:
hydra think's own commands, and the exact connector reads hydra think listed for it. The main plugin's PreToolUse
hook (hooks/review_fence.py) refuses every other tool with REFUSED, so outside text a read returns, such as a merchant's name
or a memo, can't reach the person's other tools. The person's own chat, open at the same time, isn't touched: the
fence is kept by session id. Finance's lock still refuses every money tool not on its allowlist.

  <root>/hydra/think/fence.json    {"sessions": {<session id>: {"began", "last"}}}: the sessions under the fence, when
                                   each began and its last listed call
  <root>/hydra/think/listed.json   {"at", "pages", "saved", "reads", "steps", "searches"}: what hydra think gave last

A session comes under the fence twice over: the hook puts it there when it sees one of its Bash commands start hydra
think, and hydra think does, from CLAUDE_CODE_SESSION_ID, which Claude Code gives every command it runs. The fence
lifts once every page given has saved (hydra think save <id> without --part, or hydra think done <id>), and for a
session 30 minutes after its last listed call, so a long review is never let out while a page is unsaved.

A web search passes only as WebSearch with exactly a query hydra think
listed, which the search guard (search_guard.py) passed in code before Claude saw it: no field but the query and
"mode", which is "standard" if given. Anything else is refused with SEARCH_REFUSED, and WebFetch and every MCP search
tool with REFUSED, as every unlisted tool is.

A read is matched as Finance's lock matches a tool (plugins/finance/scripts/lock.py), in both name forms,
mcp__<server>__<tool>, where the Claude app names a claude.ai connector's server by its id rather than its name. A read
hydra think listed passes with exactly its arguments. A tool a step names, whose arguments come from an earlier
answer, passes by its name, and Finance's lock still checks what it's given. ToolSearch passes too: it only loads a
tool the app holds back, so a listed read can be called, and reaches nothing.

  bind(root, session)                        a session under the fence, from now
  listed(root, pages, reads, steps, ...)     what hydra think gave; with no page to save, the fence lifts
  saved(root, page)                          a page saved whole; with every page saved, the fence lifts
  decide(root, event)                        the hook's (allowed, why) for one tool call
"""
import datetime
import os
import re
import unicodedata

from . import files, settings

MINUTES = 30
REFUSED = "During the morning review, Claude uses only hydra think and the reads it lists."
SEARCH_REFUSED = "During the morning review, Claude searches only for exactly what a page listed."
# a save in any other form (the general line didn't say what was wrong)
SAVE_REFUSED = ("During the morning review, write each answer with the Write tool to the path hydra think named, then "
                "save it with hydra think save <its id> on its own, with --part <its id> for a part, or hydra think "
                "done <its id>.")
# a Write anywhere but an answer's own path
WRITE_REFUSED = "During the morning review, Claude writes only each page's answer, to the path hydra think named for it."
WRITE = "Write"
WRITE_FIELDS = ("file_path", "content")
WRITE_MOST = 8 * 1024 * 1024  # think.STDIN_MOST: a large read's answer
SEARCH = "WebSearch"
SEARCH_FIELDS = ("query", "mode")
FREE = ("ToolSearch",)
DELETE_TASK = "mcp__scheduled-tasks__delete_scheduled_task"  # the Claude app's own tool
TOOL = re.compile(r"^mcp__(.+?)__(.+)$")
# lock.py's _ID: the Claude app names a claude.ai connector's server by its id, a UUID, with underscores allowed for
# the dashes, should a later version turn them into underscores as it does other characters.
ID = re.compile(r"(?i)(?:^|[^0-9a-f])[0-9a-f]{8}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{12}(?:$|[^0-9a-f])")
NAMED = re.compile(r"\bmcp__[A-Za-z0-9_-]+?__[A-Za-z0-9_-]+")  # a tool a step's sentence names
START = re.compile(r"(?:^|[^\w.-])hydra[\"']?\s+think\b(?!\s+(?:save|done)\b)")  # wider than the commands that pass
SAVING = re.compile(r"""^\s*(?:"[^"]*/hydra"|'[^']*/hydra'|(?:\S*/)?hydra)\s+think\s+(?:save|done)\b""")  # a save, any form
PAGE = r"[a-z][a-z0-9-]{0,23}"
PART = r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}"
PAGE_ID = re.compile(PAGE)


def fence_path(root):
    return os.path.join(root, "hydra", "think", "fence.json")


def listed_path(root):
    return os.path.join(root, "hydra", "think", "listed.json")


def root_for(cwd=None, env=None):
    """The Hydra-OS folder a session works in, as the hooks find it: $HYDRA_ROOT, else the nearest folder above the
    working folder, then above the session's project folder, that holds hydra/config.json; else None."""
    env = os.environ if env is None else env
    if env.get("HYDRA_ROOT"):
        root = os.path.abspath(os.path.expanduser(env["HYDRA_ROOT"]))
        return root if os.path.isfile(os.path.join(root, "hydra", "config.json")) else None
    for start in (cwd, env.get("CLAUDE_PROJECT_DIR")):
        here = os.path.abspath(start) if start else None
        while here:
            if os.path.isfile(os.path.join(here, "hydra", "config.json")):
                return here
            up = os.path.dirname(here)
            here = None if up == here else up
    return None


def _now(now=None):
    return now or datetime.datetime.now().astimezone()


def _when(text):
    try:
        t = datetime.datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return t if t.tzinfo else None


def _sessions(root):
    """{session: {"began", "last"}}: when its fence began, and its last listed call (an older fence.json's one time is
    both)."""
    doc = files.read_json(fence_path(root), None)
    sessions = doc.get("sessions") if isinstance(doc, dict) else None
    out = {}
    for k, v in (sessions.items() if isinstance(sessions, dict) else ()):
        v = {"began": v, "last": v} if isinstance(v, str) else v
        if isinstance(v, dict) and _when(v.get("began")) and _when(v.get("last")):
            out[str(k)] = {"began": v["began"], "last": v["last"]}
    return out


def lift(root):
    """The fence off for every session: the review is over."""
    for path in (fence_path(root), listed_path(root)):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def bind(root, session, now=None):
    """A session under the fence from now, or from now again when it runs hydra think again."""
    if not session:
        return
    sessions = _sessions(root)
    t = _now(now).isoformat(timespec="seconds")
    sessions[str(session)] = {"began": t, "last": t}
    files.write_json(fence_path(root), {"sessions": sessions})


def touch(root, session, now=None):
    """A listed call made: the session's 30 minutes start again from now, so a long review is never let out mid-way
    (the fence lifts 30 minutes after the session's last listed call)."""
    sessions = _sessions(root)
    if session in sessions:
        sessions[session]["last"] = _now(now).isoformat(timespec="seconds")
        files.write_json(fence_path(root), {"sessions": sessions})


def listed(root, pages, reads=(), steps=(), now=None, session=None, searches=(), search_ids=()):
    """What hydra think gave: the pages it asked an answer of, the connector reads it listed ({"tool", "input"}), the
    tools its steps name and the queries the search guard passed. A session hydra think knows is put under the fence.
    With no page to save, the review is over, so the fence lifts."""
    now = _now(now)
    if session:
        bind(root, session, now)
    if not pages:
        lift(root)
        return
    files.write_json(listed_path(root), {"at": now.isoformat(timespec="seconds"), "pages": list(pages), "saved": [],
                                         "reads": list(reads), "steps": sorted(set(steps)),
                                         "searches": [q for q in searches if isinstance(q, str)],
                                         # each search's page and id, so its answer is kept for its page
                                         "search_ids": [dict(s) for s in search_ids if isinstance(s, dict)]})


def listed_search(doc, args):
    """Whether a WebSearch call is exactly one hydra think listed: its query, character for character, in standard mode,
    with no other field, so no domain or any other string of Claude's leaves with it."""
    if not isinstance(args, dict) or not set(args) <= set(SEARCH_FIELDS) or args.get("mode", "standard") != "standard":
        return False
    query = args.get("query")
    return isinstance(query, str) and query in [q for q in doc.get("searches") or [] if isinstance(q, str)]


def saved(root, page):
    """A page's answer saved whole (hydra think save without --part, or hydra think done). With every page given
    saved, the review is over and the fence lifts."""
    doc = files.read_json(listed_path(root), None)
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
        return
    done = [p for p in doc.get("saved") or [] if isinstance(p, str)]
    if page in doc["pages"] and page not in done:
        done.append(page)
    if all(p in done for p in doc["pages"]):
        lift(root)
    else:
        files.write_json(listed_path(root), dict(doc, saved=done))


def under(root, session, now=None):
    """When this session's fence began, or None when it isn't under one. A fence 30 minutes past its last listed call
    ends here."""
    if not session:
        return None
    now = _now(now)
    sessions = _sessions(root)
    mine = sessions.get(session)
    if mine is None:
        return None
    if now - _when(mine["last"]) < datetime.timedelta(minutes=MINUTES):
        return _when(mine["began"])
    live = {s: t for s, t in sessions.items() if now - _when(t["last"]) < datetime.timedelta(minutes=MINUTES)}
    if live:
        files.write_json(fence_path(root), {"sessions": live})
    else:
        lift(root)
    return None


def release(root, session):
    """A session that ended leaves the fence (the main plugin's SessionEnd hook): out of fence.json,
    and with no session left the fence lifts. True when it was under one."""
    sessions = _sessions(root)
    if not session or str(session) not in sessions:
        return False
    sessions.pop(str(session))
    if sessions:
        files.write_json(fence_path(root), {"sessions": sessions})
    else:
        lift(root)
    return True


def live(root, now=None):
    """Whether any session is under the fence now: a review under way, which an update never runs beneath. Reading
    changes nothing."""
    now = _now(now)
    return any(now - _when(t["last"]) < datetime.timedelta(minutes=MINUTES) for t in _sessions(root).values())


def think_command(command, root):
    """Whether a Bash command is one of hydra think's own, exactly: hydra think, hydra think done <id>, or hydra think
    save <id> [--part <id>] with its answer in one quoted heredoc or one single-quoted --answer. Nothing may follow,
    so no other command rides along, and a quoted heredoc's body is never run."""
    nfc = lambda t: unicodedata.normalize("NFC", t)  # an accented root, spelled either way, is one path
    own = re.escape(nfc(os.path.join(root, "hydra", "bin", "hydra")))
    hydra = r"(?:hydra|%s|\"%s\"|'%s')" % (own, own, own)
    save = r"%s think save %s(?: --part %s)?" % (hydra, PAGE, PART)
    text = nfc(command.strip())
    if re.fullmatch(r"%s think|%s think done %s|%s(?: --answer '[^']*')?" % (hydra, hydra, PAGE, save), text):
        return True  # a save on its own takes the answer the Write tool put at its path (think.answer_path)
    lines = text.split("\n")
    head = re.fullmatch(r"%s <<\s?(['\"])([A-Za-z_][A-Za-z0-9_]*)\1" % save, lines[0].rstrip())
    if not head or len(lines) < 2:
        return False
    end = head.group(2)
    return lines[-1] == end and end not in lines[1:-1]


def answer_write(root, args, doc):
    """Whether a Write is a page's answer, exactly: to <root>/hydra/think/answers/<id>.json, or <id>/<part>.json, for a
    page this review gave, with no field but file_path and content, and content at most WRITE_MOST."""
    if not isinstance(args, dict) or set(args) - set(WRITE_FIELDS) or not isinstance(args.get("file_path"), str) or \
            not isinstance(args.get("content"), str) or len(args["content"].encode("utf-8")) > WRITE_MOST:
        return False
    nfc = lambda t: unicodedata.normalize("NFC", t)
    base = nfc(os.path.join(root, "hydra", "think", "answers"))
    path = nfc(args["file_path"])
    if os.path.normpath(path) != path or not path.startswith(base + os.sep):
        return False
    rest = path[len(base) + 1:].split(os.sep)
    pages = [p for p in doc.get("pages") or [] if isinstance(p, str)]
    if len(rest) == 1:
        return rest[0].endswith(".json") and rest[0][:-5] in pages
    return len(rest) == 2 and rest[0] in pages and rest[1].endswith(".json") and \
        bool(re.fullmatch(PART, rest[1][:-5]))


def same_tool(called, listed_tool):
    """Whether a call's tool is a listed one, in either name form, as Finance's lock tells them: the same tool, on the
    same server or on a server named by an id."""
    a, b = TOOL.match(called or ""), TOOL.match(listed_tool or "")
    if not a or not b or a.group(2) != b.group(2):
        return False
    return a.group(1) == b.group(1) or bool(ID.search(a.group(1))) or bool(ID.search(b.group(1)))


def decide(root, event, now=None):
    """(allowed, why) for one tool call. Only a session under the fence is checked."""
    now = _now(now)
    session = str(event.get("session_id") or "")
    name = str(event.get("tool_name") or "")
    args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    command = args.get("command") if name == "Bash" and isinstance(args.get("command"), str) else None
    if command is not None and START.search(command):
        bind(root, session, now)
    since = under(root, session, now)
    if since is None or name in FREE:
        return True, ""
    if command is not None:
        if think_command(command, root):
            touch(root, session, now)
            return True, ""
        return False, SAVE_REFUSED if SAVING.match(command) else REFUSED
    doc = files.read_json(listed_path(root), {})
    doc = doc if isinstance(doc, dict) else {}
    at = _when(doc.get("at"))
    if name == SEARCH:
        ok = at is not None and at >= since and listed_search(doc, event.get("tool_input"))
        if ok:
            touch(root, session, now)
        return (True, "") if ok else (False, SEARCH_REFUSED)
    if name == WRITE:
        ok = at is not None and at >= since and answer_write(root, args, doc)
        if ok:
            touch(root, session, now)
        return (True, "") if ok else (False, WRITE_REFUSED)
    if name == DELETE_TASK and settings.read(root).get("review") is False:
        return True, ""  # with the review off, its own task may delete itself (think.OFF), and nothing else
    if name.startswith("mcp__") and at is not None and at >= since:
        for read in doc.get("reads") or []:
            if isinstance(read, dict) and same_tool(name, str(read.get("tool") or "")) and args == read.get("input"):
                touch(root, session, now)
                return True, ""
        if any(same_tool(name, str(t)) for t in doc.get("steps") or []):
            touch(root, session, now)
            return True, ""
    return False, REFUSED
