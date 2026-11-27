"""Shared helpers for Health's scripts: where Hydra-OS keeps its files on this Mac, Health's own folder there, the
clock and safe writes.

<root> is found in this order: $HYDRA_ROOT, else the nearest folder above the working folder that holds
hydra/config.json, else ~/Hydra-OS. Health's own files are in <root>/health, or --record DIR. Nothing here makes
either folder: setup does. Nothing here reads a path, a port or a name from a constant but that last default.

privacy.py, which the doctor's private line uses, reads these names from here, so they keep
their meaning: ROOT, ID, TITLE, load_json, write_json, plugin_version, record_dir, settings and expand.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent  # the plugin's own folder, from this file, never the working folder
HOME = pathlib.Path.home()
DEFAULT_ROOT = "~/Hydra-OS"   # the last place to look; code never writes there by itself


def load_json(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return copy.deepcopy(default)


MANIFEST = load_json(ROOT / "column.json", {}) or {}
ID = MANIFEST.get("id", ROOT.name)
TITLE = MANIFEST.get("title", ID.title())
# the blocks the stock page has (layout.json): a finding, a question or a dataset for any other block isn't written
BLOCKS = {b.get("id") for b in (load_json(ROOT / "layout.json", {}) or {}).get("blocks") or [] if isinstance(b, dict)}


# ---- where things live ----

def expand(path, record: pathlib.Path | None = None) -> pathlib.Path:
    p = pathlib.Path(os.path.expanduser(str(path)))
    if not p.is_absolute() and record is not None:
        p = record / p
    return p


def tilde(path) -> str:
    """A path as a person reads it, with ~/ for the home folder, never spelled out."""
    s, h = str(path), str(HOME)
    return "~" + s[len(h):] if s == h or s.startswith(h + os.sep) else s


def hydra_root(env=None, cwd=None) -> pathlib.Path:
    """The folder that holds hydra/config.json, in that order. It always answers: with nothing found it's the
    default, which may not be there, and installed() says so."""
    env = os.environ if env is None else env
    if env.get("HYDRA_ROOT"):
        return expand(env["HYDRA_ROOT"])
    here = pathlib.Path(cwd or os.getcwd())
    for d in (here, *here.parents):
        if (d / "hydra" / "config.json").is_file():
            return d
    return expand(DEFAULT_ROOT)


def installed(root: pathlib.Path) -> bool:
    return (root / "hydra" / "config.json").is_file()


def config(root: pathlib.Path) -> dict:
    """hydra/config.json (install/v1), its paths expanded; {} when it can't be read."""
    c = load_json(root / "hydra" / "config.json", {})
    if not isinstance(c, dict):
        return {}
    for k in ("root", "python", "claude", "claude_config"):
        if isinstance(c.get(k), str) and c[k]:
            c[k] = str(expand(c[k]))
    return c


def record_dir(arg: str | None = None) -> pathlib.Path:
    """Health's own folder: --record DIR, else <root>/health."""
    return expand(arg) if arg else hydra_root() / ID


def root_of(record: pathlib.Path, env=None) -> pathlib.Path:
    """<root> for a run on this folder: $HYDRA_ROOT when set, else the folder above it when that holds hydra/config.json,
    else what hydra_root() finds."""
    env = os.environ if env is None else env
    if not env.get("HYDRA_ROOT") and installed(record.parent):
        return record.parent
    return hydra_root(env)


def settings(record: pathlib.Path) -> dict:
    """The few settings a folder may carry, for privacy.py's private terms."""
    s = {"private_terms": "private.txt"}
    got = load_json(record / "settings.json", {})
    if isinstance(got, dict):
        s.update({k: v for k, v in got.items() if isinstance(v, str)})
    return s


def main_scripts(root: pathlib.Path, env=None) -> pathlib.Path | None:
    """The main app's scripts/ folder, which holds its library: $HYDRA_PLUGINS/hydra/scripts in tests, else the one the
    list of installed apps names. None when it isn't there."""
    env = os.environ if env is None else env
    if env.get("HYDRA_PLUGINS"):
        p = expand(env["HYDRA_PLUGINS"]) / "hydra" / "scripts"
        return p if (p / "hydralib").is_dir() else None
    reg = load_json(root / "hydra" / "registry.json", {})
    for app in (reg.get("apps") or []) if isinstance(reg, dict) else []:
        if isinstance(app, dict) and app.get("id") == "hydra" and isinstance(app.get("root"), str):
            p = expand(app["root"]) / "scripts"
            return p if (p / "hydralib").is_dir() else None
    return None


# ---- safe writes: whole or not at all, 0600 in 0700 folders ----

def folder(path: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def write_atomic(path: pathlib.Path, text: str, mode: int | None = 0o600) -> None:
    """Whole or not at all: a temporary file beside it, then a rename."""
    path = pathlib.Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: pathlib.Path, obj, mode: int | None = 0o600) -> None:
    write_atomic(path, json.dumps(obj, indent=1, ensure_ascii=False) + "\n", mode)


def append_line(path: pathlib.Path, obj) -> None:
    """One JSON object on one line, the file 0600."""
    line = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def read_jsonl(path: pathlib.Path) -> list:
    out = []
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


# ---- the clock ----

def parse_time(s):
    if not s:
        return None
    if isinstance(s, dt.datetime):
        t = s
    else:
        s = str(s).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            t = dt.datetime.fromisoformat(s)
        except ValueError:
            return None
    return t if t.tzinfo else t.astimezone()


def now(arg: str | None = None) -> dt.datetime:
    """--now ISO (tests), else the clock, always with its offset."""
    return parse_time(arg) if arg else dt.datetime.now().astimezone()


def iso(t: dt.datetime) -> str:
    return t.astimezone().isoformat(timespec="seconds")


def clock(t: dt.datetime) -> str:
    """The clock's format, as date '+%a %b %-d, %H:%M' prints it."""
    t = t.astimezone()
    return f"{t:%a %b} {t.day}, {t:%H:%M}"


def plugin_version() -> str:
    return str((load_json(ROOT / ".claude-plugin" / "plugin.json", {}) or {}).get("version", "0.0.0"))
