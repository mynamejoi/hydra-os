"""Everything Research draws from what its folder holds, in one place, so a run, a save and the morning review all
write the same files the same way: say.json, home.json with the angles offer, and the page.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import home
import page
import say as say_file


def everything(rec, root, now, run: str = "") -> bool:
    """Write say.json, home.json and shared/angles.json, then the page. False when the page couldn't be drawn."""
    doc = say_file.compose(rec, root, now)
    say_file.write(rec, doc)
    home.build(rec, root, now, doc)
    try:
        page.build(rec, root, now, run or page.last_run(rec))   # its header leads with the week's first move
        return True
    except Exception:  # noqa: BLE001  (the kit's own KitError included: the run's line says the page wasn't drawn)
        return False
