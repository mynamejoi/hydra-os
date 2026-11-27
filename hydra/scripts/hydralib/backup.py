"""The update's backup, and putting it back. Before an update changes anything, what it could change is kept as APFS
clones, which take no room until a file
changes; when any step fails, every kept path is put back byte for byte, with its mode, and whatever the update made is
taken away.

  <root>/hydra/backups/<stamp>/manifest.json   {"contract": "backup/v1", "at", "why", "paths": {<path>: true|false}}:
                                               each kept path, relative to <root>, and whether it was there
  <root>/hydra/backups/<stamp>/files/<path>    its copy, as it was

What's kept (kept()): yours/, every page's record, Hydra-OS's own config.json and registry.json, the store's list, the
person's name and city (hydra/home/), their bought pages and keys (hydra/shop/) and the folder's .claude/, whose
settings.local.json is Claude Code's list of the pages turned on there. A record outside <root> isn't Hydra-OS's to
keep, and is left out. The last two backups are kept (KEEP).

  kept(root)                    the paths a backup keeps
  take(root, why, now=None, extra=())   a backup, whole or not at all, with any extra paths too; its folder
  restore(root, folder)         every kept path as it was, byte for byte
  latest(root)                  the newest backup's folder, or None
  prune(root, keep=KEEP)        all but the newest `keep` taken away

Python 3.9 standard library only; the copies are /bin/cp's, with -c (clonefile) first."""
import datetime
import os
import shutil
import subprocess

from . import files, registry

CONTRACT = "backup/v1"
KEEP = 2
FOLDER = ("hydra", "backups")
OWN = ("yours", os.path.join("hydra", "config.json"), os.path.join("hydra", "registry.json"),
       os.path.join("hydra", "store", ".claude-plugin", "marketplace.json"), os.path.join("hydra", "home"),
       os.path.join("hydra", "shop"), ".claude")
ASIDE = ".restoring"


class Failed(Exception):
    """A backup that couldn't be made, or put back."""


def folder(root):
    return os.path.join(root, *FOLDER)


def kept(root):
    """Each path a backup keeps, relative to <root>: Hydra-OS's own (OWN), then each page's record inside <root>."""
    out = list(OWN)
    for app in registry.read(root).get("apps", []):
        record = app.get("record") if isinstance(app, dict) and app.get("kind") != "main" else None
        if isinstance(record, str) and record:
            rel = os.path.relpath(os.path.abspath(record), os.path.abspath(root))
            if rel != "." and not rel.startswith(".." + os.sep) and rel != ".." and rel.split(os.sep)[0] != "hydra":
                out.append(rel)
    return sorted(set(out))


def _clone(src, dst):
    """src copied to dst whole, its mode and times kept and a link copied as a link: an APFS clone where the disk can
    make one, else a plain copy."""
    files.folder(os.path.dirname(dst))
    for flags in (["-c", "-R", "-P", "-p"], ["-R", "-P", "-p"]):
        if os.path.lexists(dst):
            _remove(dst)
        r = subprocess.run(["/bin/cp"] + flags + [src, dst], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return
    raise Failed("%s couldn't be copied." % files.tilde(src))


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


def _stamp(now):
    return now.strftime("%Y%m%d-%H%M%S")


def take(root, why, now=None, extra=()):
    """A backup of every kept path, as it is now, whole or not at all: one that can't finish is taken away again and
    Failed says so, before the update changes anything."""
    now = (now or datetime.datetime.now().astimezone()).replace(microsecond=0)
    base = folder(root)
    files.folder(base)
    name, n = _stamp(now), 1
    while os.path.lexists(os.path.join(base, name)):
        n += 1
        name = "%s-%d" % (_stamp(now), n)
    out = os.path.join(base, name)
    work = out + ".partial"
    paths = {}
    try:
        files.folder(os.path.join(work, "files"))
        for rel in sorted(set(kept(root)) | set(extra)):
            src = os.path.join(root, rel)
            paths[rel] = os.path.lexists(src)
            if paths[rel]:
                _clone(src, os.path.join(work, "files", rel))
        files.write_json(os.path.join(work, "manifest.json"), {"contract": CONTRACT, "at": now.isoformat(),
                                                               "why": str(why), "paths": paths})
        os.rename(work, out)
    except (OSError, Failed) as e:
        shutil.rmtree(work, ignore_errors=True)
        raise Failed(str(e) if isinstance(e, Failed) else "The backup couldn't be made.")
    return out


def manifest(backup):
    doc = files.read_json(os.path.join(backup, "manifest.json"), None)
    if not isinstance(doc, dict) or doc.get("contract") != CONTRACT or not isinstance(doc.get("paths"), dict):
        raise Failed("That backup isn't whole.")
    return doc


def restore(root, backup):
    """Every kept path put back as the backup has it, byte for byte with its mode, and a path that wasn't there taken
    away. Each is moved aside first and the aside taken away only once its copy is in place, so a restore that stops
    part way leaves no path missing."""
    doc = manifest(backup)
    for rel, there in sorted(doc["paths"].items()):
        if not isinstance(rel, str) or os.path.isabs(rel) or rel.split(os.sep)[0] in ("..", ".") or ".." in rel.split(os.sep):
            continue  # never a path outside <root>
        path = os.path.join(root, rel)
        aside = path + ASIDE
        if os.path.lexists(aside):
            _remove(aside)
        if os.path.lexists(path):
            os.rename(path, aside)
        try:
            if there:
                _clone(os.path.join(backup, "files", rel), path)
        except Failed:
            if os.path.lexists(aside):
                if os.path.lexists(path):
                    _remove(path)
                os.rename(aside, path)
            raise
        if os.path.lexists(aside):
            _remove(aside)


def backups(root):
    base = folder(root)
    try:
        names = sorted(n for n in os.listdir(base) if not n.endswith(".partial") and
                       os.path.isfile(os.path.join(base, n, "manifest.json")))
    except OSError:
        return []
    return [os.path.join(base, n) for n in names]


def latest(root):
    found = backups(root)
    return found[-1] if found else None


def prune(root, keep=KEEP):
    for old in backups(root)[:-keep] if keep else backups(root):
        shutil.rmtree(old, ignore_errors=True)
    base = folder(root)
    for n in os.listdir(base) if os.path.isdir(base) else []:
        if n.endswith(".partial"):  # one a stopped run left
            shutil.rmtree(os.path.join(base, n), ignore_errors=True)

