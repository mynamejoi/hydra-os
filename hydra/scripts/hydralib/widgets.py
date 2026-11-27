"""Add a widget: an installed app's offers on Home, kept in the person's own layer,
<root>/yours/layouts/home.json's `added`, which updates never touch. Claude adds one after their yes (`hydra widget
add`); Claude or Home's own page takes one away (`hydra widget remove`, POST /api/widget/remove).

  add(root, app, offer)      the line to say; ValueError with why when it can't
  remove(root, app, offer)   the same
  added(root)                ["<app>.<offer>", ...], in the order added
"""
import os

from . import files, registry


def path(root):
    return os.path.join(root, "yours", "layouts", "home.json")


def _doc(root):
    doc = files.read_json(path(root), {})
    return dict(doc) if isinstance(doc, dict) and doc.get("contract") in (None, "yours/v1") else {}


def _list(doc):
    return [a for a in (doc.get("added") or []) if isinstance(a, dict) and isinstance(a.get("id"), str)]


def added(root):
    return [a["id"] for a in _list(_doc(root))]


def _entry(root, app):
    entry = registry.app(root, app)
    if not entry or entry.get("kind") == "main":
        raise ValueError("That app isn't installed, so nothing was changed.")
    return entry


def _write(root, doc, items):
    files.refuse_newer(path(root), "yours/v1")
    doc["contract"] = "yours/v1"
    doc["version"] = (doc["version"] if isinstance(doc.get("version"), int) else 0) + 1
    doc["added"] = items
    files.write_json(path(root), doc)


def add(root, app, offer):
    entry = _entry(root, app)
    home = files.read_json(os.path.join(entry.get("record") or "", "home.json"), {})
    offers = {o.get("id"): o for o in (home.get("offers") or []) if isinstance(o, dict)} if isinstance(home, dict) else {}
    if offer not in offers:
        raise ValueError("%s doesn't offer that as a widget now." % str(entry.get("title") or app))
    doc = _doc(root)
    items, wid = _list(doc), "%s.%s" % (app, offer)
    if any(a["id"] == wid for a in items):
        return "It's on Home already."
    _write(root, doc, items + [{"id": wid}])
    return "Added. %s is on Home now." % str(offers[offer].get("title") or offer)


def remove(root, app, offer):
    _entry(root, app)
    doc = _doc(root)
    items, wid = _list(doc), "%s.%s" % (app, offer)
    if not any(a["id"] == wid for a in items):
        raise ValueError("That widget isn't on Home.")
    _write(root, doc, [a for a in items if a["id"] != wid])
    return "Taken off Home."
