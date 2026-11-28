"""Which pages can count which goals, read from data, never from a list in Goals' code. Each page declares `fits` in
its column.json. The registry copies it into the page's entry, and the page's catalog card carries it too. Goals
reads it from the registry for the pages installed (else from the page's own column.json, while the registry's copy
is on its way), and from the catalog for the pages on sale. A new page plugs in by its `fits` alone.

    "fits": {"units": ["swims", "runs"], "script": "scripts/goals.py", "what": "swims and runs from your Health data"}

`units` are the goal units it counts, as goals.json's `unit` holds them; `script`, its own goals script, answers
`--check '{"text","unit"}'` and `--count`; `what` is "What counts your goals"' words after its name and a colon.
"""
from __future__ import annotations

import os
import pathlib
import re

import common

UNIT_MAX, UNITS_MOST, WHAT_MAX = 16, 16, 120  # the limits for `fits`, which the registry's copy keeps too
SCRIPT = re.compile(r"scripts/[a-z0-9_]+\.py")
OLD_SCRIPT = "scripts/goals.py"  # a page with a goals check from before `fits`, answered as one
NOT_PAGES = (common.ID, "hydra")  # Goals itself and the main app count no goal
NONE = {"units": [], "script": "", "what": ""}


def fits_of(obj):
    """`fits` as Goals reads it, {"units", "script", "what"}, or None when it isn't one. A unit is matched as given,
    lowercase; anything past the limits is left out."""
    if not isinstance(obj, dict) or not isinstance(obj.get("units"), list):
        return None
    units = []
    for u in obj["units"]:
        u = u.strip().lower() if isinstance(u, str) else ""
        if 0 < len(u) <= UNIT_MAX and u not in units and len(units) < UNITS_MOST:
            units.append(u)
    script = obj.get("script") if isinstance(obj.get("script"), str) and SCRIPT.fullmatch(obj["script"]) else ""
    what = " ".join(obj["what"].split()) if isinstance(obj.get("what"), str) else ""
    return {"units": units, "script": script, "what": what if 0 < len(what) <= WHAT_MAX else ""}


def _registry(root) -> list:
    reg = common.load_json(pathlib.Path(root) / "hydra" / "registry.json", None)
    apps = reg.get("apps") if isinstance(reg, dict) else None
    return [a for a in apps or [] if isinstance(a, dict) and isinstance(a.get("id"), str)]


def installed(root) -> list:
    """The pages installed that can count goals, in the registry's order: [{"id", "title", "root", "fits"}]. Their
    `fits` is the registry's copy, else their own column.json's, else, for a page with a goals check from before
    `fits`, that check alone."""
    out = []
    for a in _registry(root):
        if a["id"] in NOT_PAGES or a.get("kind") == "main":
            continue
        home = a["root"] if isinstance(a.get("root"), str) and a["root"] else ""
        column = common.load_json(pathlib.Path(home) / "column.json", None) if home and "fits" not in a else None
        if "fits" in a:  # the registry's copy, `null` for a page that counts no goal by matching
            fits = fits_of(a["fits"])
        elif isinstance(column, dict) and "fits" in column:  # its own column.json, while the copy is on its way
            fits = fits_of(column["fits"])
        else:  # a page from before `fits`: its goals check alone, when it has one
            fits = dict(NONE, script=OLD_SCRIPT) if home and (pathlib.Path(home) / OLD_SCRIPT).is_file() else None
        title = a["title"] if isinstance(a.get("title"), str) and a["title"].strip() else a["id"].capitalize()
        out.append({"id": a["id"], "title": title, "root": home, "fits": fits or dict(NONE)})
    return out


def main_root(root):
    """The main plugin's folder: the kit's own, as Goals reaches it (common.load_kit), else the registry's entry."""
    if os.environ.get("HYDRA_KIT"):
        return pathlib.Path(os.environ["HYDRA_KIT"]).parent
    if os.environ.get("HYDRA_PLUGINS"):
        return pathlib.Path(os.environ["HYDRA_PLUGINS"]) / "hydra"
    hydra = next((a for a in _registry(root) if a["id"] == "hydra"), {})
    return pathlib.Path(hydra["root"]) if isinstance(hydra.get("root"), str) and hydra["root"] else None


def catalog(root) -> list:
    """The catalog in force, as shop.catalog(root) has it: the daily read's copy, <root>/hydra/shop/catalog.json, when
    it's whole, else the main plugin's bundled home/catalog.json. Its pages: [{"id", "title", "fits"}]."""
    got = common.load_json(pathlib.Path(root) / "hydra" / "shop" / "catalog.json", None)
    if not (isinstance(got, dict) and isinstance(got.get("pages"), list)):
        main = main_root(root)
        got = common.load_json(main / "home" / "catalog.json", None) if main else None
    pages = got.get("pages") if isinstance(got, dict) and isinstance(got.get("pages"), list) else []
    return [{"id": p["id"], "title": p["title"].strip(), "fits": fits_of(p.get("fits")) or dict(NONE)} for p in pages
            if isinstance(p, dict) and isinstance(p.get("id"), str) and isinstance(p.get("title"), str) and p["title"].strip()]


def on_sale(root) -> list:
    """The catalog's pages that aren't installed, in its order."""
    here = {a["id"] for a in _registry(root)}
    return [p for p in catalog(root) if p["id"] not in here]


_LISTED = {}


def names(root) -> dict:
    """The names of pages that aren't installed, as the kit gives them: each catalog card's title, then the kit's own
    LISTED (a free page, like Wellbeing, that was removed). Read once a process."""
    key = str(main_root(root) or "")
    if key not in _LISTED:
        kit = common.load_kit(root)
        listed = getattr(kit, "LISTED", None) if kit is not None else None
        _LISTED[key] = {k: v for k, v in (listed or {}).items() if isinstance(k, str) and isinstance(v, str)}
    return {**_LISTED[key], **{p["id"]: p["title"] for p in catalog(root)}}


def unit_fits(fits: dict, unit) -> bool:
    return isinstance(unit, str) and unit.strip().lower() in (fits or NONE)["units"]


SIGNS = ("$", "\u20ac", "\u00a3")  # a sum's sign, as a goal's line reads one (scripts/reader.py's MONEY)


def claimed(root, unit) -> bool:
    """A unit that belongs to the pages whose `units` hold it, and no other page's check may take:
    a money sign, or a unit any page installed or on sale names. Another unit, like hours of sleep, any page's own
    check may take, as Wellbeing counts those hours as nights."""
    if not (isinstance(unit, str) and unit.strip()):
        return False
    return unit.strip() in SIGNS or any(unit_fits(p["fits"], unit) for p in installed(root) + catalog(root))
