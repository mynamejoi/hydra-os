"""`<root>/yours/sources.json`, sources/v1: which source feeds which app, as names only.

Only `hydra sources add` and `remove` write it. The connect kit's older shape, keyed by app with no contract, is read
as the same entries and rewritten as sources/v1 on the next write."""
import datetime
import os
import re

from . import files

CONTRACT = "sources/v1"
VIA = ("connector", "api", "mac", "browser", "file", "typed")
SECRET = re.compile(r"[A-Za-z0-9_\-.=+/]{24,}")
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
APP = re.compile(r"[a-z][a-z0-9-]{0,31}")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+")
LINK = re.compile(r"(?i)[a-z][a-z0-9+.-]*://|\bwww\.")
# An account is the person's own word for it ("personal", "work"): letters and digits, with spaces, hyphens and
# apostrophes, so never an address, a domain or a link.
ACCOUNT = re.compile(r"[^\W_][\w '\u2019-]{0,23}")


class Refused(ValueError):
    """A plain-words reason nothing was written."""


def path(root):
    return os.path.join(root, "yours", "sources.json")


def read(root):
    """[entry, ...] in sources/v1's shape, from either shape on disk; [] when there's none."""
    doc = files.read_json(path(root), {})
    if not isinstance(doc, dict):
        return []
    if doc.get("contract") == CONTRACT:
        rows = doc.get("sources")
        return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    out = []  # the connect kit's shape: {"<app>": [{"source", "via", "reads", "since"}]}
    for app, rows in doc.items():
        if not isinstance(rows, list) or not isinstance(app, str) or not APP.fullmatch(app):
            continue
        for r in rows:
            if isinstance(r, dict) and isinstance(r.get("source"), str):
                out.append({"app": app, "id": "", "source": r["source"], "via": r.get("via", ""),
                            "reads": r.get("reads", ""), "since": r.get("since", "")})
    return out


def for_app(root, app):
    return [r for r in read(root) if r.get("app") == app]


def _text(value, what, most):
    value = " ".join(str(value or "").split())
    if not value or len(value) > most or CONTROL.search(value):
        raise Refused(f"{what} is one line of at most {most} characters.")
    if SECRET.search(value):
        raise Refused("That looks like a key or token. sources.json keeps names only; a secret belongs in Terminal or on the service's own page.")
    if EMAIL.search(value) or LINK.search(value):
        raise Refused("sources.json keeps names only, never an address or a link.")
    return value


def _account(value):
    value = _text(value, "The account's word", 24)
    if not ACCOUNT.fullmatch(value) or sum(ch.isdigit() for ch in value) >= 7:
        raise Refused("An account is your own word for it, such as personal or work, never an address.")
    return value


VIA_KINDS = {"file": ("upload", "file"), "connector": ("connector",), "api": ("api",), "mac": ("mac",),
             "browser": ("browser",), "typed": ("typed",)}


def declared_id(source, via, server, declared):
    """The id of the source in the app's column.json that this one fills, or "".
    declared: the app's column.json sources, or their ids alone. With their kinds known, only a source of the kind the
    way in fills is a match: a file fills the app's upload source, a connector the one with its server, an API the one
    with its service, and one of the kind when the app declares only one. With ids alone, the name decides."""
    items = [d if isinstance(d, dict) else {"id": d} for d in declared if isinstance(d, (dict, str))]
    items = [d for d in items if isinstance(d.get("id"), str) and d["id"]]
    kinds_known = any("kind" in d for d in items)
    pool = [d for d in items if d.get("kind") in VIA_KINDS.get(via, ())] if kinds_known else items
    sid = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    for d in pool:
        if d["id"] == sid or d["id"].startswith(sid + "-") or (sid and sid.startswith(d["id"])):
            return d["id"]
    if via == "connector" and server:
        for d in pool:
            if d.get("server") == server:
                return d["id"]
    if via == "api":
        for d in pool:
            if str(d.get("service") or "").lower() == source.lower():
                return d["id"]
    return pool[0]["id"] if kinds_known and len(pool) == 1 else ""


def add(root, app, source, via, reads, installed, declared=(), server="", listed=(), account="", today=None):
    """Record one source for an app, after the connect guide checked a read. installed: the installed apps' ids;
    declared: the app's column.json sources (or their ids); listed: the servers `claude mcp list` shows. Returns the
    entry, or raises Refused with the reason in plain words."""
    if app not in installed:
        raise Refused(f"{app} isn't installed, so nothing was recorded.")
    if via not in VIA:
        raise Refused("How it's reached is one of: " + ", ".join(VIA) + ".")
    entry = {"app": app, "id": "", "source": _text(source, "The source", 40), "via": via}
    if via == "connector":
        server = _text(server, "The connector's server", 80)
        if server not in listed:
            raise Refused(f"{server} isn't connected yet, so nothing was recorded. Connect it first.")
        entry["server"] = server
    entry["id"] = declared_id(entry["source"], via, entry.get("server", ""), declared)
    if account:
        entry["account"] = _account(account)
    entry["reads"] = _text(reads, "What it reads", 120)
    entry["since"] = (today or datetime.date.today()).isoformat()
    rows = [r for r in read(root) if not (r.get("app") == app and r.get("source", "").lower() == entry["source"].lower()
                                          and r.get("account", "") == entry.get("account", ""))]
    rows.append(entry)
    files.refuse_newer(path(root), CONTRACT)
    files.write_json(path(root), {"contract": CONTRACT, "sources": rows})
    return entry


def remove(root, app, source, account=""):
    """Take one source off an app. Returns True when one was there."""
    rows = read(root)
    keep = [r for r in rows if not (r.get("app") == app and r.get("source", "").lower() == str(source).lower()
                                    and (not account or r.get("account", "") == account))]
    if len(keep) == len(rows):
        return False
    files.refuse_newer(path(root), CONTRACT)
    if keep:
        files.write_json(path(root), {"contract": CONTRACT, "sources": keep})
    else:
        os.unlink(path(root))
    return True


def names(root):
    """{(page id, source id): name}: each installed page's declared sources as people know them, so a recorded source
    shows by its page's name for its id, and a setup made under an older release reads
    right after an update: a Finance set up on 0.21.0 recorded "upload", which reads "Your bank"."""
    from . import registry  # registry reads this module, so it's taken here
    out = {}
    for entry in registry.read(root).get("apps", []):
        if not isinstance(entry.get("root"), str) or not entry["root"]:
            continue
        col = files.read_json(os.path.join(entry["root"], "column.json"), {})
        for s in (col.get("sources") if isinstance(col, dict) else None) or []:
            if isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("name"), str) and s["name"].strip():
                out[(entry.get("id"), s["id"])] = " ".join(s["name"].split())[:40]
    return out


def label(row, known):
    """A recorded source as people know it: its page's declared name for its id, else the text it was recorded with,
    for an id the page doesn't declare."""
    return known.get((row.get("app"), row.get("id"))) or str(row.get("source", ""))
