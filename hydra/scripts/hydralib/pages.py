"""Pages built on request: before Home's server serves a page, it makes sure the
page is as new as what it's drawn from.

- **Home** is built by Home's own `fresh(root)`, which rebuilds it only
  when something Home reads has changed. It runs in a process of its own, so nothing in it can stop the server.
- **An app's page** is built when it's missing, was built on another day, or is older than any installed app's
  `say.json`, `yours/goals.json`, `yours/sources.json`, `yours/settings.json`, the app's layout,
  `yours/layouts/<app>.json`, the registry, `hydra/registry.json`, or `hydra/home/you.json` (so a page added or removed
  puts every rail right, and their name or place reaches every page): the app's
  `scripts/page.py --record <record>`, from its installed release.

Each build is at most once a second for each page, never two at once, and stopped after 30 seconds. A failure leaves
the last page standing. Builds run with config.json's python, run_env's environment and only the system's PATH, so
nothing they start finds claude.

An open page learns of a new build from `GET /api/panel`'s `built`, so the same check also runs from that poll, in the
background (Freshener): each app's page when it's stale, and Home's fresh(root) when anything Home reads is newer
than at its last run, and at least once a minute for its time-of-day lines."""
import datetime
import os
import signal
import subprocess
import threading
import time

from . import config as cfg
from . import registry

TIMEOUT = 30
EVERY = 1.0  # seconds between two builds of one page
HOME_EVERY = 60.0  # seconds: while a page polls, Home's fresh(root) runs at least this often
PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
HOME = "home"
YOURS = ("goals.json", "sources.json", "settings.json")
SHARED = (("hydra", "registry.json"), ("hydra", "home", "you.json"))  # what every page's rail, sky and words take

_BUILD = threading.Lock()
_LAST = {}


def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def newest_input(root, app):
    """The newest time among what an app's page is drawn from, or 0."""
    times = [_mtime(os.path.join(root, "yours", n)) for n in YOURS]
    times.append(_mtime(os.path.join(root, "yours", "layouts", app + ".json")))
    times += [_mtime(os.path.join(root, *parts)) for parts in SHARED]
    for a in registry.read(root).get("apps", []):
        if a.get("kind") != "main" and a.get("record"):
            times.append(_mtime(os.path.join(a["record"], "say.json")))
    return max([t for t in times if t is not None] or [0])


def stale(root, app, record, today=None):
    """True when the page is missing, was built on another day than today, or is older than anything it's drawn
    from."""
    built = _mtime(os.path.join(record, "page", "index.html"))
    if built is None:
        return True
    if datetime.date.fromtimestamp(built) != (today or datetime.date.today()):
        return True
    return built < newest_input(root, app)


def _env(config):
    env = cfg.run_env(config)
    env["PATH"] = PATH
    return env


def _run(config, argv, cwd):
    """True when argv ran to a clean exit within its time; its output is never read or kept."""
    python = config.get("python") or ""
    if not os.path.isabs(python) or not os.access(python, os.X_OK):
        return False
    try:
        p = subprocess.Popen([python, "-B", "-s"] + argv, cwd=cwd, env=_env(config), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    except OSError:
        return False
    try:
        return p.wait(timeout=TIMEOUT) == 0
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.wait()
        return False


def _due(key):
    """True, and the time noted, when this page wasn't built in the last second."""
    now = time.monotonic()
    if now - _LAST.get(key, -EVERY) < EVERY:
        return False
    _LAST[key] = now
    return True


def home(config):
    """Run Home's own fresh(root), at most once a second. Returns True when it ran and ended cleanly."""
    main = registry.app(config["root"], registry.MAIN)
    folder = os.path.join(main["root"], HOME) if main and main.get("root") else ""
    if not folder or not os.path.isfile(os.path.join(folder, "page.py")):
        return False
    with _BUILD:
        if not _due((config["root"], HOME)):
            return False
        code = "import sys; sys.path.insert(0, sys.argv[1]); import page; page.fresh(sys.argv[2])"
        return _run(config, ["-c", code, folder, config["root"]], folder)


def app(config, app_id, force=False):
    """Build an installed app's page when it's stale (or force), at most once a second. Returns True when it built."""
    entry = registry.app(config["root"], app_id)
    if not entry or entry.get("kind") == "main" or not entry.get("root") or not entry.get("record"):
        return False
    script = os.path.join(entry["root"], "scripts", "page.py")
    if not os.path.isfile(script) or not os.path.isdir(entry["record"]):
        return False
    if not force and not stale(config["root"], app_id, entry["record"]):
        return False
    with _BUILD:
        if not force and not stale(config["root"], app_id, entry["record"]):  # built while this one waited
            return False
        if not _due((config["root"], app_id)):
            return False
        return _run(config, ["scripts/page.py", "--record", entry["record"]], entry["root"])


def home_newest(root):
    """The newest time among what Home reads, as Home's page.py inputs() lists it: the
    registry, health.json, the person's goals, sources, settings and Home layout, Home's own you.json and quote.json
    (the name and the quote, set in the chat, which fresh(root) never writes: it writes only hydra/home/page/), and
    each app's home.json, say.json, offers under shared/ and its upload folder, inbox/, whose time moves on a drop
    (a name saved with Home open showed only at the once-a-minute run)."""
    paths = [os.path.join(root, "hydra", "registry.json"), os.path.join(root, "hydra", "health.json"),
             os.path.join(root, "yours", "goals.json"), os.path.join(root, "yours", "sources.json"),
             os.path.join(root, "yours", "settings.json"), os.path.join(root, "yours", "layouts", "home.json"),
             os.path.join(root, "hydra", "home", "you.json"), os.path.join(root, "hydra", "home", "quote.json")]
    for a in registry.read(root).get("apps", []):
        rec = a.get("record")
        if a.get("kind") == "main" or not rec:
            continue
        paths += [os.path.join(rec, "home.json"), os.path.join(rec, "say.json"), os.path.join(rec, "inbox")]
        try:
            paths += [os.path.join(rec, "shared", n) for n in os.listdir(os.path.join(rec, "shared"))]
        except OSError:
            pass
    return max([t for t in (_mtime(p) for p in paths) if t is not None] or [0])


class Freshener:
    """Runs the pages' check in one background thread when kicked (each GET /api/panel), so the poll answers at once
    and its next answer carries the new `built`."""

    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.busy = False
        self.again = False
        self.home_seen = -1.0
        self.home_at = -HOME_EVERY

    def kick(self):
        with self.lock:
            if self.busy:
                self.again = True
                return
            self.busy = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                self.sweep()
            except Exception:  # a broken input never stops the server; the next kick tries again
                pass
            with self.lock:
                if not self.again:
                    self.busy = False
                    return
                self.again = False

    def sweep(self):
        root = self.config["root"]
        newest = home_newest(root)
        if newest > self.home_seen or time.monotonic() - self.home_at >= HOME_EVERY:
            home(self.config)
            self.home_seen, self.home_at = max(newest, home_newest(root)), time.monotonic()
        for a in registry.read(root).get("apps", []):
            if a.get("kind") != "main":
                app(self.config, a.get("id"))
