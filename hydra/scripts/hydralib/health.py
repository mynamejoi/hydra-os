"""`<root>/hydra/health.json`, health/v1, and the plain-words statuses."""
import os

from . import files

CONTRACT = "health/v1"
RUN_STATES = ("ran", "due", "running", "missed", "failed", "waiting")
SIGN_IN = ("ok", "lost", "unknown")
SEAT = ("on", "off", "down")

SAID = {
    # Hydra-OS puts each back when it's opened again, since its app runs setup again without them
    "python-missing": "Part of Hydra-OS is missing from this Mac. Open Hydra-OS again to put it back.",
    "claude-missing": "The part of Claude that runs your daily routines is missing from this Mac. Open Hydra-OS again to put it back.",
    "claude-old": "Claude needs updating before runs can start.",
    "signed-out": "Sign in to your Claude account, so your daily routines can run.",
    "source-missing": "{app} can't see {source}. Connect it in Claude.",
    "source-signed-out": "{source} needs signing in again, in Claude.",
    "folder-blocked": "{app} can't read {folder} from a scheduled run.",
    "disk-low": "This Mac is low on space.",
    "limit": "Claude's limit is reached. Runs resume at {time}.",
    "offline": "No connection at {time}. Trying again.",
    "caught-up": "Ran at {time}, after this Mac woke.",
    "seat-down": "Claude's panel isn't reaching this Mac. Reconnect it.",
    "lock-changed": "{app}'s files changed outside an update.",  # a page draws Repair beside it ("repair")
    "unfinished": "{app}'s run didn't finish. It runs again tomorrow.",
}


def said(code, **fill):
    return SAID[code].format(**fill)


def clock(when):
    """A local time as a person reads it: "9:15", "14:05"."""
    return f"{when.hour}:{when.minute:02d}"


def path(root):
    return os.path.join(root, "hydra", "health.json")


def read(root):
    doc = files.read_json(path(root), {})
    return doc if isinstance(doc, dict) and doc.get("contract") == CONTRACT else {}


def write(root, checked_at, sign_in, seat, runs):
    """Write health.json whole. sign_in: {"state", "plan", "said"}; seat: {"state", "said"}; runs: each
    {"app", "due", "state", "at", "caught_up", "said"}, with "repair": true when a page draws Repair beside its said."""
    if sign_in.get("state") not in SIGN_IN or seat.get("state") not in SEAT:
        raise ValueError("a sign-in or seat state outside install.md's")
    for r in runs:
        if r.get("state") not in RUN_STATES:
            raise ValueError("a run state outside install.md's")
    doc = {"contract": CONTRACT, "checked_at": checked_at.replace(microsecond=0).isoformat(),
           "sign_in": {"state": sign_in["state"], "plan": sign_in.get("plan", ""), "said": sign_in.get("said", "")},
           "seat": {"state": seat["state"], "said": seat.get("said", "")},
           "runs": [{"app": r["app"], "due": r.get("due", ""), "state": r["state"], "at": r.get("at", ""),
                     "caught_up": bool(r.get("caught_up")), "said": r.get("said", ""),
                     **({"repair": True} if r.get("repair") is True else {})} for r in runs]}
    files.write_json(path(root), doc)
    return doc
