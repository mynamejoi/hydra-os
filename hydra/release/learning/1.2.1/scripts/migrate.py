"""Research's record, moved from one version to the next.
Hydra-OS's update backs the record up first, then runs this with Research's new release, and rolls everything back when
it exits 2.

    python3 scripts/migrate.py [--record DIR] [--check]

- Every file Research keeps in store/ carries its contract and version ("research-projects/v1"). Each is moved one
  version at a time, by the step for that file and version (STEPS), whole or not at all: a temporary file, then a
  rename.
- A file from a newer version of Research is kept as it is, never read or reset; the doctor's store line names it.
- A file with no version Research knows is kept as it is too, and said.
- --check moves nothing and says what would move.

1.0.0 is every file's first version, 1.1.0 adds store/goals.json at its first version, and no version has changed a
file's contract, so there are no steps yet. Prints one line and exits 0, or 2 with why.
Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import re
import sys

import common
import store

CONTRACT = re.compile(r"(research-[a-z]+)/v(\d+)")
STEPS = {}   # {("projects.json", 1): function taking the v1 document and giving the v2 one}; none yet


def version(contract: str) -> int:
    m = CONTRACT.fullmatch(contract or "")
    return int(m.group(2)) if m else 0


def pending(rec) -> list:
    """[(file, from version, to version)] for every store file this release moves."""
    out = []
    for name, contract in store.FILES.items():
        doc = common.load_json(store.path(rec, name), None)
        if not isinstance(doc, dict):
            continue
        have, want = version(str(doc.get("contract", ""))), version(contract)
        if 0 < have < want:
            out.append((name, have, want))
    return out


def run(rec) -> tuple:
    moved, kept = 0, []
    for name, have, want in pending(rec):
        doc = common.load_json(store.path(rec, name), None)
        for v in range(have, want):
            step = STEPS.get((name, v))
            if step is None:
                return 2, f"migrate: no step moves {name} from version {v}, so nothing was moved"
            doc = step(doc)
        common.write_json(store.path(rec, name), doc)
        moved += 1
    kept = store.newer(rec)
    return 0, f"migrate: {moved} file{'' if moved == 1 else 's'} moved" + (f", {len(kept)} from a newer version kept as they are" if kept else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"Move {common.TITLE}'s record to this release's versions.")
    ap.add_argument("--record")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    if not rec.is_dir():
        print(f"migrate: {common.TITLE}'s folder isn't there, so there's nothing to move")
        return 0
    if a.check:
        p = pending(rec)
        print(f"migrate: {len(p)} file{'' if len(p) == 1 else 's'} would move")
        return 0
    try:
        code, said = run(rec)
    except (OSError, ValueError, KeyError, TypeError) as e:
        code, said = 2, f"migrate: a step failed ({type(e).__name__}), so the update rolls back"
    print(said)
    return code


if __name__ == "__main__":
    sys.exit(main())
