#!/usr/bin/env python3
"""Hydra-OS's own files, moved from one version to the next. hydra update backs everything up first, then runs the new
core's copy of this, and puts
everything back when it exits 2.

    python3 scripts/migrate.py --root DIR [--check]

- Each file below carries its contract and version (FILES). An older one is moved one version at a time, by the step
  for its contract and version (STEPS), and each file moved is written whole: a temporary file, then a rename.
- A file from a newer version is kept as it is, never read or reset, and said; so is one whose contract isn't its own.
- --check moves nothing and says what would move.

1.0.0 is every file's first version, so there are no steps yet. It prints one line, counts only, and exits 0, or 2
with why. Python 3.9 standard library only."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hydralib import files  # noqa: E402

FILES = {  # each file, relative to <root>: its contract's name and the version this core writes
    os.path.join("hydra", "config.json"): ("install", 1),
    os.path.join("yours", "settings.json"): ("settings", 1),
    os.path.join("yours", "sources.json"): ("sources", 1),
    os.path.join("yours", "layouts", "home.json"): ("yours", 1),
    os.path.join("hydra", "shop", "bought.json"): ("bought", 1),
}
STEPS = {}  # {(contract name, from version): a function from that version's document to the next one's}; none at 1.0.0


class Stopped(Exception):
    """A step that failed: nothing after it moves, and the update puts everything back."""


def plan(root, files_=None, steps=None):
    """[(path, name, from, to)] for each file this core moves, and [path] for each from a newer version."""
    files_, steps = FILES if files_ is None else files_, STEPS if steps is None else steps
    moves, newer = [], []
    for rel, (name, version) in sorted(files_.items()):
        doc = files.read_json(os.path.join(root, rel), None)
        have = files.contract_of(doc.get("contract")) if isinstance(doc, dict) else None
        if not have or have[0] != name:
            continue  # missing, or not one this core keeps in that file: left as it is
        if have[1] > version:
            newer.append(rel)
        elif have[1] < version:
            moves.append((rel, name, have[1], version))
    return moves, newer


def run(root, check=False, files_=None, steps=None):
    """Each move made, one version at a time, whole file by whole file; Stopped at the first that can't be."""
    steps = STEPS if steps is None else steps
    moves, newer = plan(root, files_, steps)
    if check:
        return moves, newer
    for rel, name, start, end in moves:
        path = os.path.join(root, rel)
        doc = files.read_json(path, None)
        for v in range(start, end):
            step = steps.get((name, v))
            if step is None:
                raise Stopped("Hydra-OS has no step from %s/v%d." % (name, v))
            try:
                doc = step(doc)
            except Exception:
                raise Stopped("%s couldn't be moved to its next version." % rel)
            if not isinstance(doc, dict) or files.contract_of(doc.get("contract")) != (name, v + 1):
                raise Stopped("%s's step didn't give its next version." % rel)
        files.write_json(path, doc)
    return moves, newer


def line(moves, newer, check=False):
    said = ("%d %s would move." if check else "%d %s moved.") % (len(moves), "file" if len(moves) == 1 else "files") \
        if moves else "Nothing to move."
    if newer:
        said += " %d %s from a newer Hydra-OS, kept as %s." % (len(newer), "file is" if len(newer) == 1 else "files are",
                                                                "it is" if len(newer) == 1 else "they are")
    return said


def main(argv=None):
    ap = argparse.ArgumentParser(description="Move Hydra-OS's own files to this version")
    ap.add_argument("--root", required=True)
    ap.add_argument("--check", action="store_true", help="move nothing, and say what would move")
    args = ap.parse_args(argv)
    try:
        moves, newer = run(os.path.abspath(args.root), check=args.check)
    except Stopped as e:
        print(str(e))
        return 2
    except OSError:
        print("Hydra-OS's files couldn't be moved.")
        return 2
    print(line(moves, newer, args.check))
    return 0


if __name__ == "__main__":
    sys.exit(main())
