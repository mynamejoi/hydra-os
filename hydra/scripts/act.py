#!/usr/bin/env python3
"""The main app's own answer path, used by setup's self-test only: setup writes a throwaway question in
`<root>/hydra/selftest/`, answers it
through Home's server as a page would, takes it back with Undo, and removes the folder, so nothing is left behind.

    python3 scripts/act.py questions --record <root>/hydra
    python3 scripts/act.py picks --record <root>/hydra --question=<id>
    python3 scripts/act.py answer|unanswer --record <root>/hydra --question=<id> [--pick=<id>] ... [--yes]

Its last line on stdout is one JSON object, ok and said, exit 0 or 2 (column.md). It writes only
selftest/answers.jsonl, as its column.json's `writes` says. Python 3.9 standard library only."""
import datetime
import json
import os
import sys

QUESTION = "q-setup"
PICKS = ["ok"]


def say(ok, said):
    print(json.dumps({"ok": ok, "said": said}))
    return 0 if ok else 2


def main(argv):
    if not argv:
        return say(False, "Say what to do.")
    verb, opts, yes, record = argv[0], {}, False, None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--record" and i + 1 < len(argv):
            record = argv[i + 1]
            i += 1
        elif a == "--yes":
            yes = True
        elif a.startswith("--") and "=" in a:
            k, v = a[2:].split("=", 1)
            opts[k] = v
        i += 1
    if not record or not os.path.isdir(record):
        return say(False, "Hydra-OS's own folder isn't there.")
    selftest = os.path.join(record, "selftest")
    asked = os.path.isfile(os.path.join(selftest, "question.json"))
    if verb == "questions":
        print(json.dumps([QUESTION] if asked else []))
        return 0
    if verb == "picks":
        print(json.dumps(PICKS if asked and opts.get("question") == QUESTION else []))
        return 0
    if verb not in ("answer", "unanswer"):
        return say(False, "That isn't something this takes.")
    if not asked or opts.get("question") != QUESTION or opts.get("pick") not in PICKS:
        return say(False, "That isn't the setup check's question.")
    if not yes:
        return say(True, "Answer the setup check." if verb == "answer" else "Take the setup check's answer back.")
    line = {"at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(), "question": QUESTION,
            "pick": opts["pick"], "by": os.environ.get("HYDRA_BY", "page")}
    if verb == "unanswer":
        line["undone"] = True
    fd = os.open(os.path.join(selftest, "answers.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return say(True, "Saved." if verb == "answer" else "Taken back.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
