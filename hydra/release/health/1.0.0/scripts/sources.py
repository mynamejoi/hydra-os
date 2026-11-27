"""Which source feeds Health, as the person chose it: Health's entries in <root>/yours/sources.json. Health only reads
that file. `hydra sources add` and `remove` are its one writer.

A run reads every entry for Health whose `id` is a source Health's own column.json declares, and nothing else. An
entry it doesn't declare (`id` "") is the person's choice that Health can't read yet: the page says so, and nothing is
read from it. No device is assumed: with no entry, nothing is read at all.

The connect kit's older shape, keyed by app with no contract, is read as the same entries.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import common

VIA = ("connector", "api", "mac", "browser", "file", "typed")


def declared() -> dict:
    """{id: the source as column.json declares it}, for the sources Health can read."""
    out = {}
    for s in common.MANIFEST.get("sources") or []:
        if isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("kind"), str):
            out[s["id"]] = s
    return out


def _guess(source: str, via: str) -> str:
    """The id an older entry meant, from its words: only where it's plain."""
    if via == "file":
        return "upload"
    return ""


def _entry(e, app=None):
    if not isinstance(e, dict):
        return None
    source, via = e.get("source"), e.get("via")
    if not (isinstance(source, str) and source.strip() and via in VIA):
        return None
    out = {"app": app or e.get("app"), "id": e.get("id") if isinstance(e.get("id"), str) else _guess(source, via),
           "source": source.strip()[:40], "via": via,
           "reads": e.get("reads") if isinstance(e.get("reads"), str) else "",
           "since": e.get("since") if isinstance(e.get("since"), str) else ""}
    for k in ("server", "account"):
        if isinstance(e.get(k), str) and e[k].strip():
            out[k] = e[k].strip()
    return out


def entries(root) -> list:
    """Health's entries, in the file's order, in sources/v1's shape, from either shape on disk; [] when there's none."""
    doc = common.load_json(root / "yours" / "sources.json", None)
    if not isinstance(doc, dict):
        return []
    if doc.get("contract") == "sources/v1":
        rows = [_entry(e) for e in doc.get("sources") or [] if isinstance(e, dict) and e.get("app") == common.ID]
    else:  # the connect kit's shape: {"health": [{"source", "via", "reads", "since"}]}
        mine = doc.get(common.ID)
        rows = [_entry(e, common.ID) for e in mine] if isinstance(mine, list) else []
    return [r for r in rows if r]


def chosen(root) -> tuple:
    """(the entries Health reads, the entries it can't read yet), each in the file's order."""
    known = declared()
    reads, waits = [], []
    for e in entries(root):
        (reads if e["id"] in known else waits).append(e)
    return reads, waits
