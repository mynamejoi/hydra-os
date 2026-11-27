"""<root>/yours/settings.json: read whole and written whole, with only its own keys, so
one writer never drops another's: appearance, phone and suggestions (`hydra settings set`), and walkthrough, which Home's
first-open walkthrough sets to "seen" once it's skipped or done; and the first run's
tips, welcome and whats_new, which Home's server sets. Python 3.9 standard library only."""
import os
import re

from . import files

APPEARANCE = ("sun", "light", "dark", "system")
TIP = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")  # a tip's or connect ask's id
APP = re.compile(r"[a-z][a-z0-9-]{0,23}")
VERSION = re.compile(r"\d{1,4}(\.\d{1,4}){0,3}")
TIPS_MOST = 40  # seen ids kept for one app


def path(root):
    return os.path.join(root, "yours", "settings.json")


CONTRACT = "settings/v1"
KNOWN = ("contract", "appearance", "phone", "suggestions", "walkthrough", "review", "walkthroughs", "tips", "welcome",
         "whats_new")


def normal(doc):
    """settings/v1 from what's there: each key its default when it's missing or isn't one of its values, and each key
    it doesn't know kept as it is, so a newer Hydra-OS's own keys outlive a write by this one."""
    doc = doc if isinstance(doc, dict) and doc.get("contract") == CONTRACT else {}
    out = {"contract": CONTRACT, "appearance": doc.get("appearance") if doc.get("appearance") in APPEARANCE else "sun",
           "phone": False, "suggestions": doc.get("suggestions", True) is not False}
    if doc.get("walkthrough") == "seen":
        out["walkthrough"] = "seen"
    if isinstance(doc.get("review"), bool):  # the morning review, asked once in the first session
        out["review"] = doc["review"]
    pages = doc.get("walkthroughs")
    if isinstance(pages, list) and all(isinstance(p, str) for p in pages) and pages:
        out["walkthroughs"] = sorted(set(pages))[:40]
    tips = doc.get("tips")  # the first run's tips and connect asks already shown
    if isinstance(tips, dict):
        kept = {a: sorted({t for t in ids if isinstance(t, str) and TIP.fullmatch(t)})[:TIPS_MOST]
                for a, ids in tips.items() if isinstance(a, str) and APP.fullmatch(a) and isinstance(ids, list)}
        kept = {a: ids for a, ids in kept.items() if ids}
        if kept:
            out["tips"] = kept
    if doc.get("welcome") == "seen":  # Home's welcome sheet, continued
        out["welcome"] = "seen"
    if isinstance(doc.get("whats_new"), str) and VERSION.fullmatch(doc["whats_new"]):
        out["whats_new"] = doc["whats_new"]
    out.update({k: v for k, v in doc.items() if isinstance(k, str) and k not in KNOWN})
    return out


def read(root):
    return normal(files.read_json(path(root), {}))


def write(root, doc):
    files.refuse_newer(path(root), CONTRACT)
    files.write_json(path(root), normal(doc))


def mark_walkthrough(root, page=None):
    """Home's walkthrough seen ("walkthrough": "seen"), or another page's, by its app id, in "walkthroughs" (each page
    has its walkthrough, marked seen per page)."""
    doc = read(root)
    if page in (None, "home"):
        doc["walkthrough"] = "seen"
    else:
        doc["walkthroughs"] = sorted(set(doc.get("walkthroughs", [])) | {page})
    write(root, doc)


def mark_tip(root, app, tip):
    """A tip or connect ask shown, kept once in "tips". The caller checks the app declares it."""
    if not (APP.fullmatch(str(app)) and TIP.fullmatch(str(tip))):
        raise ValueError("not a tip's id")
    doc = read(root)
    tips = dict(doc.get("tips", {}))
    tips[app] = sorted(set(tips.get(app, [])) | {tip})[:TIPS_MOST]
    doc["tips"] = tips
    write(root, doc)


def mark_welcome(root):
    """Home's welcome sheet continued: "welcome": "seen"."""
    doc = read(root)
    doc["welcome"] = "seen"
    write(root, doc)


def mark_whats_new(root, version):
    """What's new closed for this version: "whats_new". Setup writes it at install too."""
    if not VERSION.fullmatch(str(version)):
        raise ValueError("not a version")
    doc = read(root)
    doc["whats_new"] = version
    write(root, doc)


def seen(root, page="home"):
    """True once that page's walkthrough has been seen."""
    doc = read(root)
    return doc.get("walkthrough") == "seen" if page == "home" else page in doc.get("walkthroughs", [])
