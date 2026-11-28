"""The panel's files, `<root>/hydra/panel/`. Home's server writes focus, requests and notes
from its own pages; Claude writes the pointer through `hydra panel`; the prompt hook reads them and writes the log and
seen. Nothing here holds a word the person typed into a page, except a note's own text."""
import datetime
import json
import os
import re
import secrets

from . import files, health, registry

POINTER_MOST = datetime.timedelta(minutes=2)
FOCUS_FRESH = datetime.timedelta(minutes=10)
FRONT_FRESH = datetime.timedelta(seconds=10)  # a page in front polls once a second (the kit's app.js)
FRONT_KEEP = datetime.timedelta(seconds=5)  # front.json is written again at most this often for the same page
REQUEST_SHOWN = datetime.timedelta(hours=24)
PREVIEW_KEPT = datetime.timedelta(minutes=30)
SKEW = datetime.timedelta(seconds=5)  # a reader's clock a moment behind the writer's
KINDS = ("connect", "add-app", "repair", "about", "review", "helpers-off", "helpers-on", "setup", "update", "remove")
# about: "Ask Claude about it" on a Shop card; review: Help's "Turn on" for the morning review; helpers-off and
# helpers-on: Help's button for the background helpers; setup: Set up on a page just added; update: Update on Home, for
# Hydra-OS itself; remove: "Remove Hydra-OS…" on Help
NO_APP = ("review", "helpers-off", "helpers-on", "update", "remove")  # the kinds that name no app
MAY_NAME_NONE = ("add-app", "repair")  # Add on Home before it names a page; Repair on Help, for Hydra-OS itself
APPEARANCE = ("sun", "light", "dark", "system")
LOG_KINDS = ("asked", "kept", "undone")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
NOT_ON_PAGE = "That isn't something on this page."


class Refused(ValueError):
    """A plain-words reason nothing was written."""


def folder(root):
    return os.path.join(root, "hydra", "panel")


def _p(root, name):
    return os.path.join(folder(root), name)


def _iso(now):
    return now.replace(microsecond=0).isoformat()


def _when(value):
    """An ISO time as an aware datetime, or None. Times are compared as times, never as strings, so a clock change
    can't reorder them."""
    try:
        t = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


def _fresh(at, now, most):
    """Written at `at`, under `most` ago, and not in the future beyond a moment's skew."""
    return at is not None and -SKEW <= now - at < most


def _id(value):
    return isinstance(value, str) and bool(ID.fullmatch(value))


def record_of(root, app):
    """An app's record folder from the registry: its own, or `<root>/hydra/<app>` for the main app's own apps (Home,
    Dreams). None for an app that isn't installed."""
    if not _id(app):
        return None
    for a in registry.read(root).get("apps", []):
        if a.get("kind") == "main":
            if app in (a.get("apps") or []):
                return os.path.join(root, "hydra", app)
        elif a.get("id") == app:
            return a.get("record") or None
    return None


def summary(root, app):
    """The app's `page/summary.json`, or None."""
    rec = record_of(root, app)
    doc = files.read_json(os.path.join(rec, "page", "summary.json"), {}) if rec else {}
    return doc if isinstance(doc, dict) and doc.get("contract") == "summary/v1" else None


def _label(doc, block, item):
    """The label the summary gives a block (item "") or one of its items, or None when it lists neither."""
    for b in doc.get("blocks") or []:
        if isinstance(b, dict) and b.get("id") == block:
            if item == "":
                return str(b.get("title") or block)
            for it in b.get("items") or []:
                if isinstance(it, dict) and it.get("id") == item:
                    return str(it.get("label") or item)
            return None
    return None


def focus(root, app, block, item, now):
    """POST /api/focus: write focus.json with the label from the app's summary, never from the request. Raises Refused
    for an app that isn't installed, or a block or item its summary doesn't list. The once-a-second limit is the
    server's."""
    if not (_id(app) and _id(block) and (item == "" or _id(item))):
        raise Refused(NOT_ON_PAGE)
    doc = summary(root, app)
    label = _label(doc, block, item) if doc else None
    if label is None:
        raise Refused(NOT_ON_PAGE)
    value = {"app": app, "block": block, "item": item, "label": " ".join(label.split())[:80], "at": _iso(now)}
    files.write_json(_p(root, "focus.json"), value)
    return value


def read_focus(root, now):
    """focus.json when it's under ten minutes old, else None."""
    f = files.read_json(_p(root, "focus.json"))
    at = _when(f.get("at")) if isinstance(f, dict) else None
    return f if _fresh(at, now, FOCUS_FRESH) else None


def front(root, page, now):
    """GET /api/panel?page=<id>, from the page in front: front.json {"page", "at"},
    written when the page changes, or again once its last write is a few seconds old. `home`, or an installed app's
    id; anything else is left out."""
    if not isinstance(page, str) or not (page == "home" or (_id(page) and registry.app(root, page))):
        return
    cur = files.read_json(_p(root, "front.json"), {})
    if isinstance(cur, dict) and cur.get("page") == page and _fresh(_when(cur.get("at")), now, FRONT_KEEP):
        return
    files.write_json(_p(root, "front.json"), {"page": page, "at": _iso(now)})


def read_front(root, now):
    """The page in front of them, `home` or an app's id, when one polled in the last ten seconds, or None."""
    cur = files.read_json(_p(root, "front.json"), {})
    if not isinstance(cur, dict) or not isinstance(cur.get("page"), str):
        return None
    return cur["page"] if _fresh(_when(cur.get("at")), now, FRONT_FRESH) else None


def point(root, app, block="", items=(), say="", now=None):
    """`hydra panel point|go`: write pointer.json, its until 2 minutes on. `point` needs a block; `go` may name only
    the app, to open its page. Every id is checked against the registry and the app's summary."""
    now = now or datetime.datetime.now().astimezone()
    items = list(items or [])
    doc = summary(root, app)
    if not doc:
        raise Refused("That app isn't installed, or its page isn't built yet, so nothing was pointed at.")
    go = False  # `go` is gone; pointer.json keeps its shape
    if read_front(root, now) != app:  # only on the page in front of them
        raise Refused("That page isn't the one in front of them, so nothing was pointed at. Open it first.")
    if block == "" and (not go or items):
        raise Refused("Say which block of the page to point at.")
    if block != "" and (not _id(block) or _label(doc, block, "") is None):
        raise Refused("That isn't on that app's page, so nothing was pointed at.")
    if any(not _id(i) or _label(doc, block, i) is None for i in items):
        raise Refused("That isn't on that app's page, so nothing was pointed at.")
    say = " ".join(str(say or "Claude is talking about this").split())
    if len(say) > 60 or CONTROL.search(say):
        raise Refused("What the outline says is one line of at most 60 characters.")
    value = {"app": app, "block": block, "items": items, "say": say, "go": bool(go), "until": _iso(now + POINTER_MOST)}
    files.write_json(_p(root, "pointer.json"), value)
    return value


def clear(root):
    """`hydra panel clear`."""
    try:
        os.unlink(_p(root, "pointer.json"))
    except FileNotFoundError:
        pass


def read_pointer(root, now):
    """pointer.json until its until, and never one that claims more than 2 minutes from now."""
    p = files.read_json(_p(root, "pointer.json"))
    until = _when(p.get("until")) if isinstance(p, dict) else None
    return p if until and now < until <= now + POINTER_MOST + SKEW else None


def via_names(via):
    """The services an app's `home.via` names: "Gmail and Google Calendar, or a file" -> the names."""
    return [n.strip() for n in re.split(r",|\bor\b|\band\b", str(via or "")) if n.strip()]


def request(root, kind, app, now, service=""):
    """POST /api/request: an open request, or the open one for the same kind, app and service with its `at`
    refreshed. `connect` and `repair` are for an installed app, `add-app` for one from the store; `repair` naming
    none, Help's Repair, is for Hydra-OS itself. `needs` comes from the app's `home.needs` in the registry, and a
    `service` must be one of its `home.via` names, in any case: a row drawn "A file" from "a file" is taken, and the
    request keeps the name as `home.via` spells it."""
    if kind not in KINDS or not (_id(app) or (kind in MAY_NAME_NONE + NO_APP and app == "")) or \
            (kind in NO_APP and app != ""):
        raise Refused("That isn't a request Claude takes.")
    entry = registry.app(root, app)
    if kind == "about":
        from . import catalog
        if not catalog.title(root, app):
            raise Refused("That page isn't in the Shop.")
    elif kind not in ("add-app",) + NO_APP and app and not entry:
        raise Refused("That app isn't installed.")
    elif kind == "setup" and entry.get("kind") == "main":
        raise Refused("That isn't a request Claude takes.")  # Hydra-OS itself is set up by its own setup
    home = (entry or {}).get("home") or {}
    service = " ".join(str(service or "").split())
    if service:
        named = {n.casefold(): n for n in via_names(home.get("via"))}
        if kind != "connect" or service.casefold() not in named:
            raise Refused("That isn't one of the services this app names.")
        service = named[service.casefold()]
    needs = str(home.get("needs") or "")[:24] if kind == "connect" else ""
    for r in open_requests(root, now):
        if r["kind"] == kind and r["app"] == app and r.get("service", "") == service:
            line = dict(r, at=_iso(now))
            files.append_line(_p(root, "requests.jsonl"), line)
            return line
    line = {"id": "r-" + secrets.token_hex(6), "at": _iso(now), "kind": kind, "app": app, "needs": needs,
            "service": service}
    files.append_line(_p(root, "requests.jsonl"), line)
    return line


def open_requests(root, now):
    """The requests not done and under 24 hours old, each its newest line, oldest first."""
    newest, done_ids = {}, set()
    for line in files.read_lines(_p(root, "requests.jsonl")):
        rid = line.get("id")
        if not isinstance(rid, str):
            continue
        if line.get("done") is True:
            done_ids.add(rid)
        elif line.get("kind") in KINDS and isinstance(line.get("app"), str):
            newest[rid] = line
    out = []
    for rid, r in newest.items():
        at = _when(r.get("at"))
        if rid not in done_ids and _fresh(at, now, REQUEST_SHOWN):
            out.append((at, r))
    return [r for _, r in sorted(out, key=lambda pair: pair[0])]


def done(root, request_id, now):
    """`hydra panel done <id>`: close an open request. Returns True when it was open."""
    if not any(r["id"] == request_id for r in open_requests(root, now)):
        return False
    files.append_line(_p(root, "requests.jsonl"), {"id": request_id, "at": _iso(now), "done": True})
    return True


def done_for(root, kind, app, now):
    """Close every open request of a kind for an app (`hydra sources add` closes the app's connect requests)."""
    n = 0
    for r in open_requests(root, now):
        if r["kind"] == kind and r["app"] == app:
            n += done(root, r["id"], now)
    return n


def note(root, text, now):
    """POST /api/notes: one line of 1 to 280 characters, with no control character."""
    if not isinstance(text, str) or "\n" in text.strip() or "\r" in text.strip():
        raise Refused("A note is one line of at most 280 characters.")
    text = " ".join(text.split())
    if not 1 <= len(text) <= 280 or CONTROL.search(text):
        raise Refused("A note is one line of at most 280 characters.")
    line = {"at": _iso(now), "text": text}
    files.append_line(_p(root, "notes.jsonl"), line)
    return line


def remove_note(root):
    """POST /api/notes/remove: take the newest off. Returns True when there was one."""
    rows = files.read_lines(_p(root, "notes.jsonl"))
    if not rows:
        return False
    rows = rows[:-1]
    if rows:
        files.write_text(_p(root, "notes.jsonl"), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    else:
        os.unlink(_p(root, "notes.jsonl"))
    return True


def unseen_notes(root):
    """The notes newer than seen.json's, oldest first."""
    seen = files.read_json(_p(root, "seen.json"), {})
    since = _when(seen.get("notes")) if isinstance(seen, dict) and seen.get("notes") else None
    out = []
    for n in files.read_lines(_p(root, "notes.jsonl")):
        at = _when(n.get("at"))
        if at and isinstance(n.get("text"), str) and (since is None or at > since):
            out.append(n)
    return out


def mark_seen(root, notes):
    """Move seen.json on to the newest of the notes just shown."""
    times = [(_when(n.get("at")), n.get("at")) for n in notes]
    times = [t for t in times if t[0]]
    if times:
        files.write_json(_p(root, "seen.json"), {"notes": max(times, key=lambda t: t[0])[1]})


def log(root, kind, now, app="", block=""):
    """One line of log.jsonl for Dreams: when, what kind, which app and which block, and nothing else, so it never
    holds the person's words."""
    if kind not in LOG_KINDS:
        raise ValueError("a log line is asked, kept or undone")
    line = {"at": _iso(now), "kind": kind, "app": app if _id(app) else "", "block": block if _id(block) else ""}
    files.append_line(_p(root, "log.jsonl"), line)
    return line


def read_preview(root, now):
    """preview.json while it's under 30 minutes old by its file's time, else None."""
    path = _p(root, "preview.json")
    p = files.read_json(path)
    try:
        at = datetime.datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
    except OSError:
        return None
    return p if isinstance(p, dict) and _fresh(at, now, PREVIEW_KEPT) else None


def built(root):
    """Each page's `built_at` from its summary, Home's and Dreams' included: {app: ISO}."""
    out = {}
    for a in registry.read(root).get("apps", []):
        for app in (a.get("apps") or []) if a.get("kind") == "main" else [a.get("id")]:
            s = summary(root, app)
            if s and isinstance(s.get("built_at"), str):
                out[app] = s["built_at"]
    return out


LATE_AFTER = (9, 30)  # local time past which a review on and not run today is said
LATE = "This morning's review hasn't run yet. It runs while the Claude app is open."


def review(root, now):
    """The morning review's state for Home, or None while it's off or not asked yet (Help's row says those):
    {"state": "ran", "at"} once hydra think ran today; {"state": "late", "said": LATE} once it's past 09:30 with no run
    today, since the task runs while the Claude app is open; else {"state": "due"}. Hydra-OS says it "didn't run" only
    with a reason it knows, and it knows none yet."""
    doc = files.read_json(os.path.join(root, "yours", "settings.json"), {})
    if not isinstance(doc, dict) or doc.get("review") is not True:
        return None
    ran = files.read_json(os.path.join(root, "hydra", "think", "ran.json"), {})
    try:
        at = datetime.datetime.fromisoformat(str(ran.get("at"))) if isinstance(ran, dict) else None
    except ValueError:
        at = None
    if at is not None and at.tzinfo and at.astimezone(now.tzinfo).date() == now.date():
        return {"state": "ran", "at": at.isoformat(timespec="seconds")}
    if (now.hour, now.minute) >= LATE_AFTER:
        return {"state": "late", "said": LATE}
    return {"state": "due"}


def answer(root, now):
    """GET /api/panel: focus, pointer, preview, built, seat, appearance and the morning review's state, and each step a
    button started (hydralib/work.py) while it works or for 10 minutes after: "update", "helpers", "repair"."""
    f = read_focus(root, now)
    settings = files.read_json(os.path.join(root, "yours", "settings.json"), {})
    appearance = settings.get("appearance") if isinstance(settings, dict) else None
    return {"focus": {k: f.get(k) for k in ("app", "block", "label", "at")} if f else None,
            "pointer": read_pointer(root, now),
            "preview": read_preview(root, now),
            "built": built(root),
            "seat": "off",  # kept for readers of an older answer: there's no seat
            "appearance": appearance if appearance in APPEARANCE else "sun",
            "review": review(root, now), **_steps(root, now)}


def _steps(root, now):
    from . import work
    try:
        return work.shown(root, now)
    except Exception:  # a broken step file never stops Home's answer
        return {}
