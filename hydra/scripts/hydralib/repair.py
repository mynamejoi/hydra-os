"""Repair, as a button on Home carries it out (hydralib/work.py): Hydra-OS's own checks and the fixes it can make
itself, then what it fixed and what's left. First the helpers' own mending (helpers.heal), and with them on, each job
the folder uses loaded again when it isn't. Then setup's own resume on the folder, the same run that picks up where
anything was left: Hydra-OS's settings, its store and its pages in Claude Code, Home's server and the tick, with setup's
self-test written to setup.json, read before and after. A page whose folder is gone gets it back. What only Claude can
do, a source to connect again, is left for Claude, and the answer says so ("claude": true).

  run(config, app="")   (ok, [its line], {"claude": True} when what's left needs Claude, else {})

Python 3.9 standard library only."""
import os
import subprocess

from . import config as cfg
from . import files, helpers, jobs, registry

NAMES = {"claude": "Claude Code", "server": "Home's server", "save": "saving from your pages",
         "plugins": "Hydra-OS's pages in Claude Code", "jobs": "the helpers", "tick": "the daily reads",
         "list": "Hydra-OS's own plugin list"}
ALL_WELL = "Hydra-OS checked its pages, its helpers and Home, and everything is in place."
SETUP_MOST = 600  # seconds for setup's resume


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _failing(root):
    doc = files.read_json(os.path.join(root, "hydra", "setup.json"), {})
    checks = doc.get("checks") if isinstance(doc, dict) else None
    return {c["name"]: str(c.get("said") or "") for c in checks or [] if isinstance(c, dict) and isinstance(c.get("name"), str)
            and not c.get("ok")}


def _jobs(config):
    """With the helpers on, each job the folder uses loaded again when it isn't. The labels it loaded."""
    if not helpers.is_on(config) or jobs.untouchable():
        return []
    labels = [config["server"]["label"]] + ([config["tick"]["label"]] if (config.get("tick") or {}).get("on") else [])
    missing = [label for label in labels if jobs.state(label) == "absent"]
    if not missing:
        return []
    return jobs.loader()(jobs.write(config, helpers._main_root(config), jobs.agents_folder(), missing)) or []


def _resume(config):
    """Setup's own resume, as hydra-setup runs it, with the helpers as the folder has them: its stop line, or ""."""
    root = config["root"]
    main = helpers._main_root(config)
    argv = [config["python"], "-I", "-B", os.path.join(main, "scripts", "install.py"), "--root", root,
            "--python", config["python"]] + (["--jobs"] if helpers.is_on(config) else [])
    env = dict(cfg.run_env(config), HYDRA_CLAUDE=config["claude"], **cfg.test_switches())
    try:
        r = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=SETUP_MOST,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return "Hydra-OS's own setup didn't run."
    lines = [x for x in (r.stdout or "").splitlines() if x.strip()]
    return lines[0] if r.returncode == 2 and lines else ("" if r.returncode == 0 else "Hydra-OS's own setup stopped.")


def _waiting(root, app=""):
    """Each page waiting on the person, by health.json: a source to connect or sign in to again."""
    doc = files.read_json(os.path.join(root, "hydra", "health.json"), {})
    runs = doc.get("runs") if isinstance(doc, dict) else None
    titles = {a["id"]: a.get("title") or a["id"] for a in registry.read(root).get("apps", []) if a.get("id")}
    return [titles.get(r.get("app"), r.get("app")) for r in runs or [] if isinstance(r, dict) and r.get("state") == "waiting"
            and (not app or r.get("app") == app)]


def run(config, app=""):
    root = config["root"]
    before = _failing(root)
    mended = helpers.heal(config)
    loaded = _jobs(config)
    stopped = _resume(config)
    after = _failing(root)
    remade = []
    for entry in registry.read(root).get("apps", []):
        record = entry.get("record")
        if entry.get("kind") == "main" or not isinstance(record, str) or (app and entry.get("id") != app):
            continue
        if not os.path.isdir(record):
            files.folder(record)
            remade.append("the folder for %s" % (entry.get("title") or entry["id"]))
    fixed = [NAMES.get(n, n) for n in before if n not in after] + remade
    if (mended or loaded) and NAMES["jobs"] not in fixed:
        fixed.append(NAMES["jobs"])
    left = [s for s in ([stopped] if stopped else []) + [after[n] or NAMES.get(n, n) for n in after] if s]
    waiting = _waiting(root, app)
    lines = []
    if fixed:
        lines.append("Fixed: %s." % _and(fixed))
    if left:
        lines.append("Still not right: %s" % " ".join(s if s.endswith(".") else s + "." for s in left))
    if waiting:
        lines.append("%s %s waiting for you to connect again." % (_and(waiting), "is" if len(waiting) == 1 else "are"))
    if not lines:
        lines.append(ALL_WELL)
    return not left and not waiting, lines, ({"claude": True} if left or waiting else {})
