#!/usr/bin/env python3
"""One tick. The job `tick.label` runs it every `tick.every_minutes` while `tick.on`:

1. it rebuilds `<root>/hydra/registry.json` from the pages already listed there and `yours/sources.json`;
2. it starts what's due, one app at a time, in the registry's order and Dreams last, holding `<root>/hydra/tick.lock`
   while a run is out, so a tick that finds it held starts nothing. An app is due once today's `schedule.at` has
   passed and no scheduled run has started since. After each app's run, each app whose schedule says `after: "each"`
   runs once more. A run that can't start, or that the tick has to stop, gets the tick's own runs.jsonl line;
3. it writes `<root>/hydra/health.json`, whole, before and after each run, so Home and the doctor see it running.

A run is caught up when the tick started more than `tick.every_minutes` plus five minutes after the run's `at`, and
the tick before it began before that `at`: a tick was missed while the Mac was off or asleep. The tick then sets
HYDRA_CAUGHT_UP=1 in the launcher's environment, and the launcher writes `caught_up` on its own line.

The tick never starts Claude Code, in any form: no model, no sign-in check and no plugin command. A run that needs
Claude is never one it starts.

  python3 tick.py [--root DIR] [--how launchd|terminal]
"""
import argparse
import datetime
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from hydralib import config as cfg  # noqa: E402
from hydralib import applog, files, health, registry, runs, shop, space  # noqa: E402

SLACK = datetime.timedelta(minutes=5)
RETRY_WAITING = datetime.timedelta(minutes=60)  # a run that stopped on a source is tried again after this


def now_local():
    """Now, on this Mac's clock. HYDRA_TEST_NOW, an ISO time, sets it, for tests only."""
    given = _when(os.environ.get("HYDRA_TEST_NOW")) if os.environ.get("HYDRA_TEST_NOW") else None
    return given or datetime.datetime.now().astimezone()


def _when(value):
    try:
        t = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _said_patterns():
    out = []
    for text in health.SAID.values():
        parts = re.split(r"(\{[a-z]+\})", text)
        out.append(re.compile("".join(".{1,40}" if p.startswith("{") else re.escape(p) for p in parts)))
    return out


SAID_LINES = _said_patterns()


def plain(why):
    """A line's `why`, kept only when it's one of install.md's plain-words statuses, filled in."""
    return why if isinstance(why, str) and any(p.fullmatch(why) for p in SAID_LINES) else ""


def scheduled(reg):
    """The apps the tick starts: each with a daily schedule at a real HH:MM, in the registry's order, Dreams last. A
    run that needs Claude is never one of them: a page's Claude step is in the morning review, the scheduled task the
    person said yes to."""
    apps = [a for a in reg.get("apps", []) if a.get("kind") != "main" and isinstance(a.get("schedule"), dict)
            and a["schedule"].get("days", "daily") == "daily" and runs.AT.fullmatch(str(a["schedule"].get("at") or ""))
            and not runs.needs_claude(a)]
    return sorted(apps, key=lambda a: a.get("id") == "dreams")


def follows(app):
    return (app.get("schedule") or {}).get("after") == "each"


class Tick:
    """One tick for one <root>. clock and start are the parts a test replaces."""

    def __init__(self, config, env=None, clock=now_local, how="launchd", start=runs.start, start_runs=True):
        self.config, self.root = config, config["root"]
        self.env = os.environ if env is None else env
        self.clock, self.how, self.start_run = clock, how, start
        self.running = None  # (app id, when it started, caught up)
        self.sign = {"state": "unknown", "plan": "", "said": ""}  # never read: nothing the tick starts needs it
        self.reg = {"apps": []}
        self.tried = set()
        self.lock = None
        self.began = self.prev = None
        self.start_runs = start_runs  # False for setup's self-test: the registry and health.json only

    # ---- one tick -------------------------------------------------------------------------------------------------

    def __call__(self):
        """"held" when another run is out (nothing is started or written), else "ticked"."""
        try:
            self.lock = runs.Lock(self.root).__enter__()
        except runs.Held:
            return "held"
        try:
            self.began = self.clock()
            self.prev = _when(health.read(self.root).get("checked_at"))
            self.reg = registry.build(self.config, self.began, self.env, listed=True)
            apps = scheduled(self.reg) if self.start_runs else []
            if self.start_runs:
                try:  # the shop's catalog, at most once in 20 hours, sending nothing
                    shop.read_catalog(self.config, self.began, env=self.env)
                except Exception:
                    pass
            try:  # what a part-done add or update left, put back as far as files go: Claude Code's part waits
                shop.recover(self.config, env=self.env, claude=False)  # for Home's server's start or the chat
            except Exception:
                pass
            try:  # a layout preview nobody answered in 30 minutes, dropped
                from hydralib import yours
                yours.expire(self.config)
            except Exception:
                pass
            self.write()
            for _ in range(len(apps) + 1):
                now = self.clock()
                due = [a for a in apps if a["id"] not in self.tried and self.due(a, now)]
                if not due:
                    break
                app = due[0]
                self.tried.add(app["id"])
                if self.start(app, self.caught_up(app)) and not follows(app):
                    for f in apps:
                        if follows(f) and f["id"] != app["id"]:
                            self.tried.add(f["id"])
                            self.start(f, False)
            self.write()
        finally:
            self.lock.__exit__(None, None, None)
        return "ticked"

    def run_now(self, app_id, wait=0):
        """`hydra run <app>`: that app's launcher once, as the tick would start it but with --trigger manual, then each
        after-each app. Refused while another run is out, unless it waits `wait` seconds for it, as a file dropped on a
        page does. Returns (started, said)."""
        try:
            self.lock = runs.Lock(self.root, wait).__enter__()
        except runs.Held:
            return False, "Another page is running now. Try again once it's done."
        try:
            self.began = self.clock()
            self.prev = _when(health.read(self.root).get("checked_at"))
            self.reg = registry.build(self.config, self.began, self.env, listed=True)
            apps = scheduled(self.reg)
            app = next((a for a in apps if a["id"] == app_id), None)
            if app is None:
                return False, "That page isn't installed, or it has no run to start."
            title = str(app.get("title") or app_id)
            if not self.start(app, False, trigger="manual"):
                self.write()
                return False, plain((runs.newest_by(app.get("record") or "", "manual") or {}).get("why")) or \
                    "%s's run couldn't start." % title
            if not follows(app):
                for f in apps:
                    if follows(f) and f["id"] != app_id:
                        self.start(f, False)
            self.write()
            return True, "%s's run is done." % title
        finally:
            self.lock.__exit__(None, None, None)

    # ---- the slot each app's run was started for (<root>/hydra/tick-slots.json) ---------------------------------
    # {"<app id>": "<the slot's ISO time>"}, kept once its scheduled run is back, so a slot never starts twice even
    # when no line of it is found: a launcher's line on another clock, as in a test, or a line that was lost.

    def started_slot(self, app):
        doc = files.read_json(os.path.join(self.root, "hydra", "tick-slots.json"), {})
        return doc.get(app["id"]) if isinstance(doc, dict) else None

    def note_slot(self, app, slot):
        if slot is None:
            return
        path = os.path.join(self.root, "hydra", "tick-slots.json")
        doc = files.read_json(path, {})
        doc = doc if isinstance(doc, dict) else {}
        doc[app["id"]] = slot.isoformat()
        files.write_json(path, doc)

    # ---- what's due ---------------------------------------------------------------------------------------------

    def due(self, app, now):
        at = runs.last_slot(app["schedule"]["at"], now)  # across midnight too: the newest slot that's come round
        if at is None:
            return False
        if at.date() != now.date() and not (self.prev and self.prev < at):
            return False  # yesterday's only when Hydra-OS ticked before it and slept through it, never on its first day
        newest, today = runs.today(app.get("record") or "", at, now)
        if any(runs.state_of(line) in runs.DONE for line in today):
            return False
        if newest is None and self.started_slot(app) == at.isoformat():
            return False  # started for this slot already, whatever clock its launcher's line keeps
        if newest is None or runs.state_of(newest) != "waiting":
            return True  # never started today, or missed: tried again, and its line isn't written twice
        since = _when(newest.get("finished_at")) or _when(newest.get("started_at"))
        sources = _mtime(os.path.join(self.root, "yours", "sources.json"))
        return bool(since and ((sources and sources > since.timestamp()) or now - since >= RETRY_WAITING))

    def caught_up(self, app):
        at = runs.last_slot(app["schedule"]["at"], self.began)
        every = datetime.timedelta(minutes=int((self.config.get("tick") or {}).get("every_minutes") or 15))
        return bool(at and self.prev and self.prev < at and self.began - at > every + SLACK)

    # ---- starting one ---------------------------------------------------------------------------------------------

    def start(self, app, caught_up, trigger="schedule"):
        """Start one app's run and wait for it. True when its launcher ran."""
        now = self.clock()
        record = app.get("record") or ""
        title = str(app.get("title") or app["id"])
        if space.free(self.root, self.env) < space.TICK_LOW:  # a run never fills the Mac
            runs.write_once(record, runs.tick_line("waiting", space.FULL_RUN % title, now, self.how, caught_up, trigger),
                            now)
            return False
        python = self.config.get("python") or ""
        if not os.path.isabs(python) or not os.access(python, os.X_OK):
            runs.write_once(record, runs.tick_line("missed", health.said("python-missing"), now, self.how, caught_up, trigger),
                            now)
            return False
        run = runs.launcher(app)
        if run is None or not os.path.isdir(record):
            runs.write_once(record, runs.tick_line("missed", health.said("lock-changed", app=title), now, self.how,
                                                   caught_up, trigger), now)
            return False
        log = os.path.join(record, "runs.jsonl")
        size = os.path.getsize(log) if os.path.exists(log) else 0
        self.running = (app["id"], now, caught_up)
        self.lock.note(app["id"], now)
        self.write()
        code = self.start_run(self.config, app, run, trigger, caught_up)
        if trigger == "schedule":  # once it's back: a run a shutdown cut off is started again on the next tick
            self.note_slot(app, runs.last_slot(app["schedule"]["at"], now))
        self.running = None
        self.lock.note("", None)
        if code is None or (os.path.getsize(log) if os.path.exists(log) else 0) == size:
            # stopped after its time, or it ended without its own line: the tick says so, so it doesn't start again today
            line = runs.tick_line("failed", health.said("unfinished", app=title), now, self.how, caught_up, trigger)
            line["finished_at"] = self.clock().replace(microsecond=0).isoformat()
            runs.write_once(record, line, now)
        self.write()
        return True

    # ---- health.json --------------------------------------------------------------------------------------------

    def entry(self, app, now):
        due = app["schedule"].get("at", "")
        base = {"app": app["id"], "due": due, "state": "due", "at": "", "caught_up": False, "said": ""}
        if self.running and self.running[0] == app["id"]:
            return dict(base, state="running", at=self.running[1].strftime("%H:%M"), caught_up=self.running[2])
        at = runs.at_today(due, now)
        record = app.get("record") or ""
        if at and now >= at:
            line = runs.today(record, at, now)[0]
            if line is None:
                return base
        else:
            line = runs.newest(record)  # before today's run: how the last one went
            if line is None:
                return base
        state = runs.state_of(line)
        started = _when(line.get("started_at"))
        caught = line.get("caught_up") is True
        said = plain(line.get("why")) if state in ("waiting", "missed", "failed") else ""
        if state == "ran" and caught and started:
            said = health.said("caught-up", time=health.clock(started))
        return dict(base, state=state, at=started.strftime("%H:%M") if started else "", caught_up=caught, said=said)

    def write(self):
        now = self.clock()
        entries = [self.entry(a, now) for a in scheduled(self.reg)]
        health.write(self.root, now, self.sign, {"state": "off", "said": ""}, entries)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check what's due and start it, for one Hydra-OS folder")
    ap.add_argument("--root", help="the root (default: HYDRA_ROOT, the nearest hydra/config.json, then ~/Hydra-OS)")
    ap.add_argument("--how", choices=("launchd", "terminal"), default="terminal")
    ap.add_argument("--run", metavar="APP", help="start that app's run now, with --trigger manual (hydra run)")
    ap.add_argument("--wait", type=int, default=0, help="with --run, how many seconds to wait for a run that's out")
    args = ap.parse_args(argv)
    try:
        config = cfg.load(os.path.abspath(os.path.expanduser(args.root))) if args.root else cfg.load()
    except cfg.NotInstalled as e:
        print(str(e), file=sys.stderr)
        return 1
    applog.use(config["root"])  # its notes go to the folder's own log
    if args.run:
        started, said = Tick(config, how=args.how).run_now(args.run, max(0, min(args.wait, 3600)))
        try:
            print(said, flush=True)
        except BrokenPipeError:  # hydra run stopped listening once the run was out; the run itself is done
            pass
        return 0 if started else 2
    if Tick(config, how=args.how)() == "held":
        print("Another app is running now, so nothing new started.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
