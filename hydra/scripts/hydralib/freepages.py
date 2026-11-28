"""Hydra-OS's free pages, brought in line with a release: each free page the release lists that this home lacks, added
as setup adds it, and each one it has at an older version brought up to the release's. A page bought from the Shop is
never touched, and nothing is removed. Best effort: a page that doesn't go in is left as it was, its old version still
in the store and in Claude Code, and its own files as they were before its own migrate ran.

  bring(config, release, claude, env=None, deadline=None)
      [(name, "added" | "upgraded", version)]: for an update's own step and for the new core's migrate.py, which an
      older core's update runs, so a home on any earlier core gets the new release's free pages. deadline, a
      time.monotonic() value, keeps the whole of it inside the time an older update gives its migrate: no page is
      started without LEAST seconds left, each call waits only for what's left, a page's way back gets BACK seconds
      more, and the pages are drawn only with DRAW seconds left (Home draws one when it's opened anyway).
Python 3.9 standard library only."""
import os
import shutil
import subprocess
import tempfile
import time

from . import applog, backup, files, registry
from . import claude as cl
from . import config as cfg

MIGRATE_WAIT = 300  # seconds for a page's own scripts/migrate.py
CLAUDE_WAIT = 300  # seconds for one of Claude Code's own commands
LEAST = 60  # seconds a page needs left before the deadline to be started
BACK = 40  # seconds past the deadline a page's way back may take
DRAW = 70  # seconds left before the deadline for the pages to be drawn here


def _wait(deadline, most):
    """A call's time: most seconds, or what's left before the deadline, and never under 5."""
    return most if deadline is None else max(5, min(most, deadline - time.monotonic()))


def _claude(config, claude, args, env, wait):
    code, _ = cl.run(claude, args, config.get("claude_config", ""), env, timeout=wait, cwd=config["root"])
    return code


def _market(root):
    return os.path.join(root, "hydra", "store", ".claude-plugin", "marketplace.json")


def _put(root, name, entry):
    """The store's list with this page's entry in its own place (at the end when it's new), or without it when entry is
    None."""
    path = _market(root)
    doc = files.read_json(path, {})
    if isinstance(doc, dict) and isinstance(doc.get("plugins"), list):
        at = [i for i, p in enumerate(doc["plugins"]) if isinstance(p, dict) and p.get("name") == name]
        rest = [p for p in doc["plugins"] if not (isinstance(p, dict) and p.get("name") == name)]
        if entry:
            rest.insert(at[0] if at else len(rest), entry)
        doc["plugins"] = rest
        files.write_json(path, doc)


def _keep(root, name, record):
    """A copy of a page's own files before its own migrate moves them, in <root>/hydra/: (the folder, the copy)."""
    held = tempfile.mkdtemp(prefix=".free-%s-" % name, dir=os.path.join(root, "hydra"))
    copy = os.path.join(held, "record")
    try:
        backup._clone(record, copy)
    except (OSError, backup.Failed):
        shutil.rmtree(held, ignore_errors=True)
        raise OSError("its own files couldn't be copied first")
    return held, copy


def bring(config, release, claude, env=None, deadline=None):
    from . import shop
    root = config["root"]
    listed = files.read_json(os.path.join(release, ".claude-plugin", "marketplace.json"), {})
    market = files.read_json(_market(root), {})
    if not isinstance(listed, dict) or not isinstance(market, dict) or not isinstance(market.get("plugins"), list):
        return []
    bought = set(shop.bought(root))
    have = {p.get("name"): p for p in market["plugins"] if isinstance(p, dict)}
    done = []
    for e in listed.get("plugins") or []:
        name = e.get("name") if isinstance(e, dict) else None
        if not isinstance(name, str) or name == registry.MAIN or name in bought or not isinstance(e.get("source"), str):
            continue
        version, cur = str(e.get("version") or ""), have.get(name)
        if cur and shop.vt(str(cur.get("version") or "")) >= shop.vt(version):
            continue
        src = os.path.realpath(os.path.join(release, e["source"]))
        rel = os.path.relpath(src, os.path.realpath(release))
        if rel.startswith("..") or len(rel.split(os.sep)) < 2 or \
                not os.path.isfile(os.path.join(src, ".claude-plugin", "plugin.json")):
            continue  # a page's own <name>/<version>/ folder only, never the folder that holds its every version
        if deadline is not None and deadline - time.monotonic() < LEAST:
            applog.note("free pages", "%s %s left for the next update: no time left in this one" % (name, version))
            continue
        target = os.path.join(root, "hydra", "store", rel)
        made = not os.path.lexists(target)
        record = (registry.app(root, name) or {}).get("record") or ""
        migrate = os.path.join(src, "scripts", "migrate.py")
        held = copy = None
        try:
            if not made:
                shutil.rmtree(target)
            shutil.copytree(src, target, symlinks=True)
            if cur and os.path.isdir(record) and os.path.isfile(migrate):  # its own files moved to its new version
                held, copy = _keep(root, name, record)
                r = subprocess.run([config["python"], "-B", "-s", os.path.join(target, "scripts", "migrate.py"),
                                    "--record", record], cwd=target, env=dict(cfg.run_env(config), HYDRA_ROOT=root),
                                   stdin=subprocess.DEVNULL, capture_output=True,
                                   timeout=_wait(deadline, MIGRATE_WAIT))
                if r.returncode != 0:
                    raise OSError("its own migrate didn't finish")
            _put(root, name, {"name": name, "source": "./" + rel, "version": version,
                              **({"description": e["description"]} if isinstance(e.get("description"), str) else {})})
            _claude(config, claude, ["plugin", "marketplace", "update", cfg.STORE], env, _wait(deadline, CLAUDE_WAIT))
            mine = "%s@%s" % (name, cfg.STORE)
            code = _claude(config, claude, ["plugin", "update" if cur else "install", mine, "--scope", "local"], env,
                           _wait(deadline, CLAUDE_WAIT))
            if code != 0 and not cur:  # one an update that stopped left in Claude Code, now listed again
                code = _claude(config, claude, ["plugin", "update", mine, "--scope", "local"], env,
                               _wait(deadline, CLAUDE_WAIT))
            if code != 0:
                raise OSError("Claude Code didn't take it")
            done.append((name, "upgraded" if cur else "added", version))
        except (OSError, ValueError, subprocess.SubprocessError) as err:
            applog.note("free pages", "%s %s left as it was: %s" % (name, version, err))
            back = None if deadline is None else deadline + BACK
            _put(root, name, cur)
            if copy and os.path.lexists(copy):  # its own files as they were before its own migrate
                try:
                    shutil.rmtree(record, ignore_errors=True)
                    os.rename(copy, record)
                except OSError as e:
                    applog.note("free pages", "%s's own files couldn't be put back: %s" % (name, e))
            if made:
                shutil.rmtree(target, ignore_errors=True)
            _claude(config, claude, ["plugin", "marketplace", "update", cfg.STORE], env, _wait(back, 120))
            mine = "%s@%s" % (name, cfg.STORE)
            if cur:  # back at the version the list names again
                _claude(config, claude, ["plugin", "update", mine, "--scope", "local"], env, _wait(back, 120))
            else:
                _claude(config, claude, ["plugin", "uninstall", mine, "--scope", "local"], env, _wait(back, 120))
        finally:
            if held:
                shutil.rmtree(held, ignore_errors=True)
    if done:
        from . import pages
        registry.build(dict(config, claude=claude), env=env)
        for name, _how, _version in done:
            try:
                files.folder((registry.app(root, name) or {})["record"])
                if deadline is None or deadline - time.monotonic() >= DRAW:
                    pages.app(config, name, force=True)
            except (OSError, ValueError, KeyError) as err:
                applog.note("free pages", "%s's page: %s" % (name, err))
        applog.note("free pages", ", ".join("%s %s %s" % d for d in done))
    return done
