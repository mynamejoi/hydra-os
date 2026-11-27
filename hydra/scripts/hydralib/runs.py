"""Starting an app's run.

  Lock(root)                       <root>/hydra/tick.lock, held while a run is out: never two at once
  running(root)                    the app whose run is out, or None
  launcher(entry)                  the app's own `schedule.run`, from its column.json, checked
  start(config, entry, run, ...)   runs it with config.json's python, from its installed release
  today(record, at, now)           the newest scheduled run that started today at or after `at`
  tick_line(...)                   the line the tick writes for a run that didn't start, or that it stopped

A run's launcher writes its own runs.jsonl line. The tick writes one only for a run that never started (`missed` or
`waiting`), or that it had to stop (`failed`), each with `why` in install.md's plain words, at most once a day for each
app and reason. Nothing here reads what a run prints."""
import datetime
import fcntl
import json
import os
import re
import signal
import subprocess
import time

from . import config as cfg
from . import files

LOCK = "tick.lock"
RUN_MOST = 2 * 60 * 60  # seconds a run may take before the tick stops it
DONE = ("ran", "failed")
SCRIPT = re.compile(r"scripts/(?:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}/){0,3}[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.py")
ARG = re.compile(r"-{0,2}[A-Za-z0-9._][A-Za-z0-9._=:-]{0,63}")  # a flag or a plain word, never a space or a shell sign
AT = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


class Held(Exception):
    """Another run is out."""


class Lock:
    """flock on <root>/hydra/tick.lock, with the app whose run is out written in it while it's held."""

    def __init__(self, root, wait=0):
        self.path = os.path.join(root, "hydra", LOCK)
        self.fd = None
        self.wait = max(0, wait)  # seconds to wait for a run that's out, as a dropped file's run does; 0 never waits

    def __enter__(self):
        files.folder(os.path.dirname(self.path))
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        end = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= end:
                    os.close(fd)
                    raise Held()
                time.sleep(2)
        self.fd = fd  # made 0600 by os.open when it's new; one another run made keeps its mode
        self.note("", None)
        return self

    def note(self, app, now):
        """Say which app's run is out now ("" for none)."""
        body = json.dumps({"app": app, "since": now.replace(microsecond=0).isoformat() if now else ""}).encode("utf-8")
        os.ftruncate(self.fd, 0)
        os.pwrite(self.fd, body, 0)

    def __exit__(self, *exc):
        try:
            os.ftruncate(self.fd, 0)
        finally:
            os.close(self.fd)  # closing it lets the flock go
            self.fd = None


def running(root):
    """{"app", "since"} while a run is out, else None."""
    path = os.path.join(root, "hydra", LOCK)
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return None  # nobody holds it
        except BlockingIOError:
            pass
        try:
            doc = json.loads(os.pread(fd, 4096, 0).decode("utf-8") or "{}")
        except ValueError:
            doc = {}
        return {"app": str(doc.get("app") or ""), "since": str(doc.get("since") or "")}
    finally:
        os.close(fd)


def at_today(at, now):
    """Today's `schedule.at` as a local time, or None for one that isn't HH:MM."""
    m = AT.fullmatch(str(at or ""))
    return now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0) if m else None


def last_slot(at, now):
    """The newest time `at` came round at or before now: today's, or yesterday's while today's hasn't come yet, so a run
    missed across midnight is still caught up, once. None for one that isn't HH:MM."""
    slot = at_today(at, now)
    if slot is None or now >= slot:
        return slot
    return at_today(at, now - datetime.timedelta(days=1))


def launcher(entry):
    """[script, arguments...]: the app's `schedule.run` from its installed release's column.json, or None when it's
    not one of the release's own scripts with plain arguments."""
    col = files.read_json(os.path.join(entry.get("root") or "", "column.json"), {})
    sched = col.get("schedule") if isinstance(col, dict) and col.get("id") == entry.get("id") else None
    run = sched.get("run") if isinstance(sched, dict) else None
    if (not isinstance(run, list) or not 1 <= len(run) <= 12 or not isinstance(run[0], str)
            or not SCRIPT.fullmatch(run[0]) or not all(isinstance(a, str) and ARG.fullmatch(a) for a in run[1:])):
        return None
    root = os.path.realpath(entry["root"])
    script = os.path.realpath(os.path.join(root, run[0]))
    if not script.startswith(os.path.join(root, "scripts") + os.sep) or not os.path.isfile(script):
        return None
    return list(run)


def needs_claude(entry):
    col = files.read_json(os.path.join(entry.get("root") or "", "column.json"), {})
    sched = col.get("schedule") if isinstance(col, dict) else None
    return not (isinstance(sched, dict) and sched.get("needs_claude") is False)


def with_trigger(run, trigger):
    """The run's arguments with `--trigger <trigger>` in place of the one it declares, or added for a manual run."""
    args = list(run)
    if "--trigger" in args[1:]:
        i = args.index("--trigger", 1)
        if i + 1 < len(args):
            args[i + 1] = trigger
        else:
            args.append(trigger)
    elif trigger != "schedule":
        args += ["--trigger", trigger]
    return args


def start(config, entry, run, trigger="schedule", caught_up=False, most=RUN_MOST):
    """Run the launcher once and wait: its exit code, or None when it was stopped after `most` seconds (with anything
    it started). It runs with config.json's python, from the installed release, with run_env's environment and
    HYDRA_CAUGHT_UP=1 when the tick started it late; its output is never read."""
    python = config.get("python") or ""
    argv = [python, "-B", "-s"] + with_trigger(run, trigger)
    env = cfg.run_env(config, {"HYDRA_CAUGHT_UP": "1"} if caught_up else None)
    try:
        p = subprocess.Popen(argv, cwd=entry["root"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    except OSError:
        return -1
    try:
        return p.wait(timeout=most)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.wait()
        return None


def _when(value):
    try:
        t = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


def state_of(line):
    """A line's state; an old line with none reads `ok: true` as ran and `ok: false` as failed."""
    s = line.get("state")
    if s in ("ran", "failed", "waiting", "missed"):
        return s
    return "ran" if line.get("ok") is True else "failed"


def lines(record):
    return files.read_lines(os.path.join(record, "runs.jsonl"))


def today(record, since, now):
    """(the newest `schedule` line that started at or after `since`, its slot, and every such line), oldest first.
    `since` is the run's slot, today's or, across midnight, yesterday's, so a line of either date counts."""
    found = []
    for line in lines(record):
        t = _when(line.get("started_at"))
        if line.get("trigger") == "schedule" and t and since <= t:
            found.append((t, line))
    found.sort(key=lambda pair: pair[0])
    return (found[-1][1] if found else None), [line for _, line in found]


def newest(record):
    """The newest `schedule` line of any day, or None."""
    return newest_by(record, "schedule")


def newest_by(record, trigger):
    """The newest line of any day with this trigger, or None."""
    best = None
    for line in lines(record):
        t = _when(line.get("started_at"))
        if line.get("trigger") == trigger and t and (best is None or t > best[0]):
            best = (t, line)
    return best[1] if best else None


def tick_line(state, why, now, how="launchd", caught_up=False, trigger="schedule"):
    """The tick's own line for a run that didn't start, or that it stopped: as a launcher's stop line is, with no
    server fields."""
    stamp = now.replace(microsecond=0).isoformat()
    line = {"started_at": stamp, "finished_at": stamp, "trigger": trigger, "how": how, "unattended": trigger == "schedule",
            "ok": False, "state": state, "waiting_permission": False, "denied": 0, "sources": {}, "why": why,
            "tokens": None, "tokens_why": "The run didn't start." if state != "failed" else "It was stopped."}
    if caught_up:
        line["caught_up"] = True
    return line


def write_once(record, line, now):
    """Append the tick's line unless one with the same state and why is already there today. True when written."""
    for old in lines(record):
        t = _when(old.get("started_at"))
        if t and t.date() == now.date() and old.get("state") == line["state"] and old.get("why") == line["why"]:
            return False
    if not os.path.isdir(record):
        return False  # a record setup never made: nothing is written outside one
    files.append_line(os.path.join(record, "runs.jsonl"), line)
    return True
