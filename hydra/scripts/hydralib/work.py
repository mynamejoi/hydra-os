"""The steps a button on Home starts that Hydra-OS carries out itself, with no Claude turn: Update, the helpers' on and
off, Repair and Remove. Each can stop or restart Home's server, so each runs in a process of its own
(scripts/work.py), in a session of its own, which launchd leaves running when it stops the server's job: it ends only
the job's own process group (launchd.plist(5), AbandonProcessGroup). The page asks how it went through GET /api/panel.

  start(config, step, app="")  "" once the step has started, else the line why not: one step at a time
  started(root, step)          when the run just started began, its "at" for the page
  shown(root, now)             {"update" | "helpers" | "repair": {"state", "said", "at", ...}} for GET /api/panel: one
                               that's working, or one that ended within the last 10 minutes, "at" its run's start
  run(config, step, app="")    the step itself, in work.py's own process, its state written as it starts and ends

<root>/hydra/panel/work.json keeps each one's last state, {"<key>": {"state": "working" | "done" | "failed", "said",
"at", "started", "pid", "repair"?, "claude"?}}: "at" when it was written, "started" when its run began, the same from
the press to its end, so the page never takes an earlier run's end for this one's. Every said is the page's own words. Each uses the Claude Code the last Hydra-OS chat ran on, or the Claude app's own
newest when that copy has moved (claude.step_claude). Python 3.9 standard library only."""
import datetime
import os
import subprocess

from . import applog, files, registry
from . import config as cfg

STEPS = {"update": "update", "helpers-on": "helpers", "helpers-off": "helpers", "repair": "repair", "remove": "remove",
         "remove-page": "remove"}
WORKING = {"update": "Updating Hydra-OS…", "helpers-on": "Turning the helpers on…",
           "helpers-off": "Turning the helpers off…", "repair": "Checking Hydra-OS…",
           "remove": "Removing Hydra-OS…", "remove-page": "Removing %s…"}
PAGE_LEFT = "%s couldn't be removed. Try again in a moment."
BUSY = "Hydra-OS is busy with another step. Try again in a moment."
STOPPED = "That stopped part way. Try again in a moment."
HELPERS = {"helpers-on": "Background helpers are on.", "helpers-off": "Background helpers are off."}
HELPERS_DIDNT = "The background helpers didn't change. Try again in a moment."
SHOWN = datetime.timedelta(minutes=10)  # how long the page is told how a step ended
MOST = datetime.timedelta(minutes=30)  # a step still working after this, or whose process is gone, stopped
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _path(root):
    return os.path.join(root, "hydra", "panel", "work.json")


def _now():
    return datetime.datetime.now().astimezone().replace(microsecond=0)


def _doc(root):
    doc = files.read_json(_path(root), {})
    return doc if isinstance(doc, dict) else {}


def _when(entry):
    try:
        at = datetime.datetime.fromisoformat(str(entry.get("at")))
    except ValueError:
        return None
    return at if at.tzinfo else None


def _alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def _working(entry, now):
    """Whether an entry is a step still under way: working, its process there, and not past MOST. One that has just
    been started has no pid yet, for a moment."""
    if not isinstance(entry, dict) or entry.get("state") != "working":
        return False
    at = _when(entry)
    if at is None or now - at > MOST:
        return False
    return entry.get("pid") is None and now - at < datetime.timedelta(minutes=1) or _alive(entry.get("pid"))


def write(root, key, **state):
    doc = _doc(root)
    doc[key] = dict(state, at=_now().isoformat())
    files.write_json(_path(root), doc)


def shown(root, now):
    out = {}
    for key, entry in _doc(root).items():
        if key not in ("update", "helpers", "repair", "remove") or not isinstance(entry, dict):
            continue
        at = _when(entry)
        if at is None or now - at > (MOST if entry.get("state") == "working" else SHOWN):
            continue
        if entry.get("state") == "working" and not _working(entry, now):
            entry = {"state": "failed", "said": STOPPED, "started": entry.get("started")}
        out[key] = {k: entry[k] for k in ("state", "said", "repair", "claude") if k in entry}
        if isinstance(entry.get("started"), str):
            out[key]["at"] = entry["started"]
    return out


def started(root, step):
    """When the run of that step began, as the page matches it, or "" with none."""
    entry = _doc(root).get(STEPS[step])
    return (entry.get("started") or "") if isinstance(entry, dict) else ""


def working(root, step, app=""):
    """The said while a step works: a page's own Remove names its page."""
    if step != "remove-page":
        return WORKING[step]
    return WORKING[step] % str((registry.app(root, app) or {}).get("title") or app)


def _main_root(config):
    main = registry.app(config["root"], registry.MAIN) or {}
    return main["root"] if os.path.isdir(main.get("root") or "") else HERE


def start(config, step, app=""):
    """The step started in a process of its own, with this server's own test switches beside run_env's (a real server
    has none), so a test's step reaches only its own stand-ins."""
    root = config["root"]
    now = _now()
    if any(_working(e, now) for e in _doc(root).values()):
        return BUSY
    began = now.isoformat()
    write(root, STEPS[step], state="working", said=working(root, step, app), pid=None, started=began)
    env = dict(cfg.run_env(config), **cfg.test_switches())
    argv = [config["python"], "-B", "-s", os.path.join(_main_root(config), "scripts", "work.py"), "--root", root,
            "--step", step, "--started", began] + (["--app", app] if app else [])
    try:
        subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    except OSError:
        write(root, STEPS[step], state="failed", said=STOPPED, started=began)
        return STOPPED
    return ""


def run(config, step, app="", started=""):
    from . import claude as cl
    root, key = config["root"], STEPS[step]
    began = started or _now().isoformat()
    said = working(root, step, app)
    write(root, key, state="working", said=said, pid=os.getpid(), started=began)
    config = dict(config, claude=cl.step_claude(config))
    extra = {}
    try:
        if step == "update":
            from . import panel, update
            lines = update.core(config)
            ok = update.went_through(lines)
            if ok:
                panel.done_for(root, "update", "", _now())  # what an Update tap asked for
            elif lines == [update.BUSY]:  # its own words are a chat's phrase; the page's are these
                lines = [BUSY]
        elif step in ("helpers-on", "helpers-off"):
            from . import helpers, jobs
            lines = helpers.on(config, jobs.loader()) if step == "helpers-on" else helpers.off(config)
            ok = lines == [helpers.ON if step == "helpers-on" else helpers.OFF]
            lines = [HELPERS[step] if ok else HELPERS_DIDNT]  # the page's words, not the chat's
            if not ok and step == "helpers-on":
                extra = {"repair": True}  # Repair loads a helper that's missing
        elif step == "repair":
            from . import repair
            ok, lines, extra = repair.run(config, app)
        elif step == "remove-page":
            from . import remove, shop
            title = str((registry.app(root, app) or {}).get("title") or app)
            try:
                lines, ok = [remove.remove_page(config, app)], True
            except (remove.Stop, shop.Refused) as e:
                applog.note("work", "remove-page %s: %s" % (app, e))
                lines, ok = [PAGE_LEFT % title], False
                extra = {"repair": True} if getattr(e, "repair", False) else {}
        else:  # remove: the folder goes to the Trash, and this file with it
            from . import remove
            remove.remove(config, yes=True)
            return
    except Exception as e:
        applog.note("work", "%s stopped: %r" % (step, e))
        write(root, key, state="failed", said=STOPPED, started=began)
        return
    write(root, key, state="done" if ok else "failed", said=" ".join(lines), started=began, **extra)
