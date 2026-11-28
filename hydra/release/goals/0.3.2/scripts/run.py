"""Goals' run, the launcher the tick starts.
Code only: it starts no `claude`, makes no request, and reads no source of its own.

    python3 scripts/run.py [--trigger schedule|manual|test] [--record DIR] [--now ISO]

It reads <root>/yours/goals.json, the registry, yours/sources.json and each measuring app's say.json, through the
one reading, and writes Goals' own record: say.json, home.json, STATUS.md and the page, then one line in runs.jsonl,
then the doctor's doctor.json.
It never writes under yours/. It prints one line, with counts only.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import build
import common
import doctor
import goalsfile
import page


def tilde(path) -> str:
    s, home = str(path), str(pathlib.Path.home())
    return "~" + s[len(home):] if s == home or s.startswith(home + "/") else s


def run_line(started, finished, trigger: str, ok: bool) -> dict:
    """The run's line: a run that starts no model has no tokens and no servers."""
    return {"started_at": common.iso(started), "finished_at": common.iso(finished), "trigger": trigger,
            "how": "tick" if trigger == "schedule" else "terminal", "unattended": trigger == "schedule", "ok": ok,
            "state": "ran" if ok else "failed", "waiting_permission": False, "denied": 0, "sources": {},
            "model": False, "mcp_servers": [], "tokens": None}


def checked(root, record, now) -> None:
    """The doctor, as every run's last step: doctor.json written, nothing printed. A doctor
    that can't check never fails the run."""
    try:
        doctor.write(record, doctor.check(root, record, now))
    except Exception:  # noqa: BLE001
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Goals' run: how each goal stands, from the pages that count them.")
    ap.add_argument("--trigger", choices=("schedule", "manual", "test"), default="manual")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    try:
        root = common.root_of(a.record)
        now = common.now(a.now)
    except (common.NotSetUp, ValueError) as e:
        print(f"run: not started: {e}", file=sys.stderr)
        return 1
    record = common.folder(common.record_of(root, a.record))
    why = ""
    try:
        said = build.write(root, record, now)
        common.write_whole(record / "STATUS.md", build.status(root, now, said))
        page.build(root, record, now, common.iso(now))
    except goalsfile.Broken:
        why = "the goals couldn't be read"
    except page.NoKit:
        why = "its page couldn't be drawn, since Hydra-OS's own files aren't in reach"
    except OSError as e:
        why = type(e).__name__
    except Exception as e:  # noqa: BLE001  (the page's builder: only its kind, since its words might hold a goal's)
        why = f"its page couldn't be drawn ({type(e).__name__})"
    if why:
        common.append_line(record / "runs.jsonl", run_line(now, common.now(a.now), a.trigger, False))
        checked(root, record, now)
        print(f"run: not finished: {why}", file=sys.stderr)
        return 1
    common.append_line(record / "runs.jsonl", run_line(now, common.now(a.now), a.trigger, True))
    checked(root, record, now)
    c = build.counts(build.readings(root, now)["goals"])
    print(f"run: wrote {tilde(record)} ({build.plural(c['hand'], 'goal')} in hand)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
