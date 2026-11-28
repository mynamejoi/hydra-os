"""Research's upload source (column.json, id "notes"): the notes the person drops on Research's page, which Hydra-OS's
server streams into <record>/inbox/. Each is a .md or .txt file, read in code on this Mac,
kept in store/notes.json by its title, the day it came and the general topics it matches, and never sent anywhere: not
to a search, not to the morning review, not to another page. The file itself stays in inbox/ as it came.

    python3 scripts/notes.py [--record DIR] [--now ISO]

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import re
import sys

import common
import search
import store

INBOX = "inbox"
ACCEPTS = (".md", ".txt")
MOST = 512 * 1024      # a note's bytes, at most
TITLE = 80


def waiting(rec) -> list:
    """The files in inbox/ not yet kept."""
    have = {n.get("file") for n in store.notes(rec)}
    box = rec / INBOX
    if not box.is_dir():
        return []
    return sorted(p for p in box.iterdir() if p.is_file() and not p.name.startswith(".")
                  and p.suffix.lower() in ACCEPTS and p.name not in have)


def title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = " ".join(re.sub(r"^[#>*\-\s]+", "", line).split())
        if line:
            return line[:TITLE]
    return fallback


def matched(text: str, doc: dict) -> list:
    """The general topics a note's words hold, every word of each, at most three, in the list's order."""
    have = set(search.words_of(text))
    return [tid for tid, words in search.topics(doc).items() if set(search.words_of(words)) <= have][:3]


def read(rec, now) -> dict:
    """Keep each new note: {"kept": n, "unread": n, "files": n}."""
    doc = search.load()
    kept, unread = list(store.notes(rec)), 0
    for p in waiting(rec):
        try:
            raw = p.read_bytes()
            if len(raw) > MOST:
                raise ValueError("too large")
            text = raw.decode("utf-8")
        except (OSError, ValueError, UnicodeDecodeError):
            unread += 1
            continue
        day = common.day_words(now.astimezone().date())
        kept.append({"id": store.new_id("n", p.name), "title": title_of(text, f"A note from {day}"), "file": p.name,
                     "topics": matched(text, doc), "added": common.iso(now)})
    if len(kept) != len(store.notes(rec)):
        store.write(rec, "notes.json", "notes", kept)
    box = rec / INBOX
    files = sum(1 for p in box.iterdir() if p.is_file() and not p.name.startswith(".")) if box.is_dir() else 0
    return {"kept": len(kept), "unread": unread, "files": files}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"Keep the notes dropped on {common.TITLE}'s page.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    if not rec.is_dir():
        print(f"notes: {common.TITLE}'s folder isn't there yet.", file=sys.stderr)
        return 1
    c = read(rec, common.now(a.now))
    print(f"notes: {c['kept']} kept, {c['unread']} couldn't be read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
