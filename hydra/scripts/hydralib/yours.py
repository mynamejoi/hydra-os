"""A page's layout, as the person wants it, in their own layer: `hydra yours`. Claude never edits a plugin's files: a
change is a preview first, drawn on
the page with Keep and Undo (the kit's layout-changed bar), and only Keep writes <root>/yours/layouts/<app>.json, which
updates never touch.

  preview(config, app, verb, args)   move, hide, show, widen, rename or add: <root>/hydra/panel/preview.json, its line
  keep(config, app)                  the preview checked against the kit's own rules, kept as the next version, the page
                                     built again; each kept version also in layouts/history/<app>/<version>.json
  drop(config, app)                  the preview taken away, the page built again
  back(config, app, version)         a kept version, as the next one
  stock(config, app)                 the person's layout set aside, never deleted, and the page drawn from stock
  expire(config, now=None)           a preview nobody answered in 30 minutes, dropped (the tick)

A change only new code could make gets NEW_CODE. Fixed blocks (header, goals, questions, connections) never move, hide
or take a new title. Python 3.9 standard library only."""
import datetime
import json
import os
import re

from . import files, registry

CONTRACT = "yours/v1"
TYPES = ("today", "suggestions", "chart", "note", "list", "table")  # the kit's blocks a person may add (kit.TYPES less fixed)
FIXED = ("header", "goals", "questions", "connections")
WIDTHS = ("full", "half", "third")
KEPT = datetime.timedelta(minutes=30)  # an unanswered preview, dropped after (panel.PREVIEW_KEPT)
TITLE_MOST = 40
BLOCK = re.compile(r"[A-Za-z0-9_-]{1,64}")
NEW_CODE = "That needs new code in the page, so your copy can't do it yet. You can ask for it from Help."
SHOWN = "It's on %s now, with Keep and Undo at the foot of the page."


class Refused(Exception):
    """One plain line on why nothing changed."""


def path(root, app):
    return os.path.join(root, "yours", "layouts", "%s.json" % app)


def preview_path(root):
    return os.path.join(root, "hydra", "panel", "preview.json")


def _entry(root, app):
    entry = registry.app(root, app)
    if not entry or entry.get("kind") == "main" or not BLOCK.fullmatch(str(app)):
        raise Refused("That isn't one of your pages.")
    return entry


def _stock(entry):
    doc = files.read_json(os.path.join(entry.get("root") or "", "layout.json"), None)
    if not isinstance(doc, dict) or not isinstance(doc.get("blocks"), list):
        raise Refused(NEW_CODE)  # a page with no stock layout draws no blocks of its own to change
    return doc


def _mine(root, app):
    doc = files.read_json(path(root, app), None)
    return doc if isinstance(doc, dict) and doc.get("contract") == CONTRACT else None


def _blank(entry, stock):
    return {"contract": CONTRACT, "stock": {"app": entry["id"], "layout": stock.get("contract", "layout/v1"),
                                            "release": str(entry.get("version") or "")},
            "version": 0, "order": [], "hidden": [], "widths": {}, "titles": {}, "added": []}


def _ids(stock, mine):
    """Each block the person may change, in the order the page draws them now: stock's and theirs, fixed ones out."""
    blocks = [b for b in stock.get("blocks") or [] if isinstance(b, dict) and isinstance(b.get("id"), str)]
    ids = [b["id"] for b in blocks if not b.get("fixed") and b.get("type") not in FIXED]
    ids += [a["id"] for a in mine.get("added") or [] if isinstance(a, dict) and isinstance(a.get("id"), str)]
    order = [i for i in mine.get("order") or [] if i in ids]
    return order + [i for i in ids if i not in order], {b["id"] for b in blocks if b.get("fixed") or b.get("type") in FIXED}


def _title(entry):
    return str(entry.get("title") or entry["id"])


def preview(config, app, verb, args):
    """A proposed layout for an app, written as its preview: nothing else changes until Keep."""
    root = config["root"]
    entry = _entry(root, app)
    stock = _stock(entry)
    mine = _mine(root, app) or _blank(entry, stock)
    new = json.loads(json.dumps(mine))
    for k, v in (("order", []), ("hidden", []), ("widths", {}), ("titles", {}), ("added", [])):
        new[k] = new.get(k) if isinstance(new.get(k), type(v)) else v
    ids, fixed = _ids(stock, new)
    block = args[0] if args else ""
    if verb in ("move", "hide", "show", "widen", "rename") and block in fixed:
        raise Refused("That part stays where it is on every page.")
    if verb in ("move", "hide", "show", "widen", "rename") and block not in ids:
        raise Refused("That page has no part named %s. Its parts are %s." % (block, ", ".join(ids) or "none yet"))
    if verb == "move" and len(args) == 3 and args[1] in ("before", "after") and args[2] in ids and args[2] != block:
        order = [i for i in ids if i != block]
        at = order.index(args[2]) + (1 if args[1] == "after" else 0)
        new["order"] = order[:at] + [block] + order[at:]
        change = "%s moves %s %s." % (block, args[1], args[2])
    elif verb == "hide" and len(args) == 1:
        new["hidden"] = sorted(set(new["hidden"]) | {block})
        change = "%s is hidden." % block
    elif verb == "show" and len(args) == 1:
        new["hidden"] = [i for i in new["hidden"] if i != block]
        change = "%s shows again." % block
    elif verb == "widen" and len(args) == 2 and args[1] in WIDTHS:
        new["widths"] = dict(new["widths"], **{block: args[1]})
        change = "%s is %s width." % (block, args[1])
    elif verb == "rename" and len(args) == 2 and 0 < len(args[1].strip()) <= TITLE_MOST and args[1].isprintable():
        new["titles"] = dict(new["titles"], **{block: " ".join(args[1].split())})
        change = "%s is called %s." % (block, " ".join(args[1].split()))
    elif verb == "add" and len(args) in (2, 3):
        kind, data = args[0], args[1]
        record = entry.get("record") or ""
        if kind not in TYPES or not BLOCK.fullmatch(data) or not os.path.isfile(
                os.path.join(record, "page", "data", data + ".json")):
            raise Refused(NEW_CODE)  # a block type the kit doesn't draw, or data the page doesn't make
        title = " ".join(args[2].split()) if len(args) == 3 else data.replace("-", " ").capitalize()
        if not 0 < len(title) <= TITLE_MOST:
            raise Refused("A part's name is at most %d characters." % TITLE_MOST)
        n = 1
        while "y-%s-%d" % (data, n) in ids:
            n += 1
        block = "y-%s-%d" % (data, n)
        new["added"] = new["added"] + [{"id": block, "type": kind, "width": "full", "title": title, "data": data}]
        change = "A %s of %s is added." % (kind, title)
    else:
        raise Refused(NEW_CODE)
    files.write_json(preview_path(root), {"app": app, "layout": new, "change": change, "blocks": [block],
                                          "from_version": int(mine.get("version") or 0)})
    _build(config, app)
    return SHOWN % _title(entry)


def _build(config, app):
    try:
        from . import pages
        pages.app(config, app, force=True)
    except Exception:
        pass  # the page is built at its next look


def _history(root, app, version):
    return os.path.join(root, "yours", "layouts", "history", app, "%d.json" % version)


def _write(root, app, doc):
    """A layout kept as the next version, and kept in its history too."""
    mine = _mine(root, app)
    doc = dict(doc, contract=CONTRACT, version=int((mine or {}).get("version") or 0) + 1)
    files.refuse_newer(path(root, app), CONTRACT)
    files.write_json(path(root, app), doc)
    files.write_json(_history(root, app, doc["version"]), doc)
    return doc["version"]


def keep(config, app):
    """The preview kept, when it's this app's and its layout still the one it changed: checked by the kit's own rules
    first, so a layout the page can't draw is refused with why."""
    root = config["root"]
    entry = _entry(root, app)
    doc = files.read_json(preview_path(root), None)
    if not isinstance(doc, dict) or doc.get("app") != app or not isinstance(doc.get("layout"), dict):
        raise Refused("There's no new layout waiting on that page.")
    if int(doc.get("from_version") or 0) != int((_mine(root, app) or {}).get("version") or 0):
        drop(config, app)
        raise Refused("That page's layout changed since, so the new one was dropped. Ask again.")
    try:
        import sys
        kit_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "kit")
        sys.path.insert(0, kit_dir)
        import kit
        kit.lay_out(_stock(entry), doc["layout"])
    except ImportError:
        pass
    except Exception as e:
        raise Refused("That layout can't be drawn: %s." % str(e).rstrip("."))
    version = _write(root, app, doc["layout"])
    os.unlink(preview_path(root))
    _build(config, app)
    return "Kept. %s's layout is version %d." % (_title(entry), version)


def drop(config, app=None):
    """The preview taken away: this app's, or any when app is None."""
    root = config["root"]
    doc = files.read_json(preview_path(root), None)
    if not isinstance(doc, dict) or (app is not None and doc.get("app") != app):
        return "There's no new layout waiting on that page."
    try:
        os.unlink(preview_path(root))
    except OSError:
        pass
    if isinstance(doc.get("app"), str):
        _build(config, doc["app"])
    return "Undone. The page is as it was."


def back(config, app, version):
    root = config["root"]
    entry = _entry(root, app)
    doc = files.read_json(_history(root, app, int(version)), None) if str(version).isdigit() else None
    if not isinstance(doc, dict) or doc.get("contract") != CONTRACT:
        raise Refused("That page has no kept layout of that version.")
    new = _write(root, app, {k: v for k, v in doc.items() if k != "version"})
    _build(config, app)
    return "%s is back as it was at version %s, kept as version %d." % (_title(entry), version, new)


def stock(config, app):
    root = config["root"]
    entry = _entry(root, app)
    mine = _mine(root, app)
    if mine is None:
        return "%s is drawn from stock already." % _title(entry)
    files.write_json(_history(root, app, int(mine.get("version") or 0)), mine)  # set aside, never deleted
    os.unlink(path(root, app))
    _build(config, app)
    return "%s is drawn from stock now. Your layout is kept, and hydra yours back brings it again." % _title(entry)


def expire(config, now=None):
    """A preview nobody answered in 30 minutes, dropped (yours.md, Layouts, step 5). True when one was."""
    p = preview_path(config["root"])
    try:
        age = (now or datetime.datetime.now()).timestamp() - os.path.getmtime(p)
    except OSError:
        return False
    if age < KEPT.total_seconds():
        return False
    drop(config)
    return True
