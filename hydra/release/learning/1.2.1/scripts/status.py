"""Research's STATUS.md: the five headings, states and counts only, with `As of:` right
under `Updated:`. Never a query, a topic, a project's name, a find or a note.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt

import common


def clock(t: dt.datetime) -> str:
    t = t.astimezone()
    return f"{t:%a %b} {t.day}, {t:%H:%M}"


def compose(now: dt.datetime, as_of, facts: dict) -> str:
    """facts: {"now": line, "needs": [lines], "done": [lines], "next": [lines]}, each a state or a count."""
    head = [f"# STATUS: {common.TITLE}", "", f"Updated: {clock(now)}"]
    if as_of:
        head.append(f"As of: {clock(min(as_of, now))}")
    return "\n".join(head + [
        "", "## Now", "", facts.get("now") or "Idle.", "",
        "## Needs you", "", "\n".join(facts.get("needs") or []) or "Nothing.", "",
        "## Done (with proof)", "", "\n".join(facts.get("done") or []) or "- Nothing yet.", "",
        "## Next", "", "\n".join(facts.get("next") or []) or "- Nothing planned.", "",
        "## Signals for other pillars", "", "None.", ""])


def write(rec, now: dt.datetime, as_of, facts: dict) -> None:
    common.write_atomic(rec / "STATUS.md", compose(now, as_of, facts))
