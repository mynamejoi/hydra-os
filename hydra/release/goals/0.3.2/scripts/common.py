"""Goals' shared parts: where things live, whole-or-nothing writes, the clock, and days and figures in words.

<root> is never a constant. A script given --record takes <root> as that folder's parent, so a test's record never
reaches the person's own goals. With no record it is $HYDRA_ROOT, then the nearest folder above the working folder
that holds hydra/config.json, then ~/Hydra-OS when that holds one. Python 3.9, standard library only.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import pathlib
import re
import tempfile

ID, TITLE = "goals", "Goals"
PLUGIN = pathlib.Path(__file__).resolve().parent.parent
NOT_SET_UP = "Hydra-OS isn't set up on this Mac yet."
DAY = re.compile(r"\d{4}-\d\d-\d\d")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class NotSetUp(Exception):
    """No <root> to be found: nothing is installed here."""


def root_of(record=None) -> pathlib.Path:
    if record is not None:
        return pathlib.Path(record).expanduser().absolute().parent
    env = os.environ.get("HYDRA_ROOT")
    if env:
        return pathlib.Path(env).expanduser().absolute()
    here = pathlib.Path.cwd()
    for folder in (here, *here.parents):
        if (folder / "hydra" / "config.json").is_file():
            return folder
    home = pathlib.Path.home() / "Hydra-OS"
    if (home / "hydra" / "config.json").is_file():
        return home
    raise NotSetUp(NOT_SET_UP)


def load_kit(root):
    """Hydra-OS's kit, the main plugin's kit/ (its README, "Reaching it"): $HYDRA_KIT, else $HYDRA_PLUGINS/hydra/kit,
    else the registry's hydra root. Loaded by its path, so nothing on sys.path can stand in for it. None when the
    main plugin isn't in reach, as in a test of a record alone."""
    import importlib.util
    folder = os.environ.get("HYDRA_KIT")
    if not folder and os.environ.get("HYDRA_PLUGINS"):
        folder = os.path.join(os.environ["HYDRA_PLUGINS"], "hydra", "kit")
    if not folder:
        reg = load_json(pathlib.Path(root) / "hydra" / "registry.json", None)
        apps = reg.get("apps") if isinstance(reg, dict) else None
        hydra = next((a for a in apps or [] if isinstance(a, dict) and a.get("id") == "hydra"), None)
        if not (hydra and isinstance(hydra.get("root"), str)):
            return None
        folder = os.path.join(hydra["root"], "kit")
    path = os.path.join(folder, "kit.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("hydra_kit", path)
        kit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kit)
        return kit
    except Exception:  # noqa: BLE001  (a kit that can't be loaded is a kit that isn't there)
        return None


def record_of(root, record=None) -> pathlib.Path:
    return pathlib.Path(record).expanduser().absolute() if record is not None else pathlib.Path(root) / ID


def yours(root) -> pathlib.Path:
    return pathlib.Path(root) / "yours"


def folder(path) -> pathlib.Path:
    """The folder, made when it's missing, mode 0700, as every folder Hydra-OS writes is."""
    path = pathlib.Path(path)
    if not path.is_dir():
        path.mkdir(parents=True, mode=0o700)
        os.chmod(path, 0o700)
    return path


def write_whole(path, text: str, mode: int = 0o600) -> None:
    """The file whole or not at all: a temporary file beside it, then a rename."""
    path = pathlib.Path(path)
    folder(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path, obj) -> None:
    write_whole(path, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def append_line(path, obj) -> None:
    """One whole line on a .jsonl, mode 0600."""
    path = pathlib.Path(path)
    folder(path.parent)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return default


def lines(path) -> list:
    """A .jsonl's objects, oldest first. A line that isn't one is left out."""
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        pass
    return out


def parse_time(s):
    """An ISO 8601 time with its offset, or None."""
    if not isinstance(s, str):
        return None
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def now(arg=None) -> dt.datetime:
    """--now ISO, for tests, else the clock, always with its offset."""
    if arg:
        t = parse_time(arg)
        if t is None:
            raise ValueError("--now isn't a time with its offset")
        return t
    return dt.datetime.now().astimezone()


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def day(s):
    """A real day written YYYY-MM-DD, or None."""
    if not (isinstance(s, str) and DAY.fullmatch(s)):
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def day_words(d: dt.date, today: dt.date) -> str:
    """"Sep 20" in this year, "Apr 2026" in another."""
    return f"{MONTHS[d.month - 1]} {d.day}" if d.year == today.year else f"{MONTHS[d.month - 1]} {d.year}"


def weekday_day(d: dt.date) -> str:
    """"Mon Mar 23", as the kit says a day a goal is read on or counted to."""
    return f"{WEEKDAYS[d.weekday()]} {MONTHS[d.month - 1]} {d.day}"


def one_day(d: dt.date, today: dt.date) -> str:
    """One day, as "on" or "as of" reads it: "May 1" in this year, "May 1, 2025" in another."""
    return f"{MONTHS[d.month - 1]} {d.day}" + ("" if d.year == today.year else f", {d.year}")


def number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def figure(n) -> str:
    """A figure as a caption shows it: thousands grouped, and no decimals on a whole number."""
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}"
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def with_unit(n, unit) -> str:
    """"17 swims", "1 swim", or with a sign, "$20,000"."""
    if not unit:
        return figure(n)
    if is_sign(unit):
        return f"{unit}{figure(n)}"
    return f"{figure(n)} {singular(unit) if n == 1 else unit}"


def singular(unit: str) -> str:
    """A unit's first word for exactly one: "swims" is "swim", "stories" "story",
    "classes" "class", "people" "person", and "km" stays "km"."""
    first, sep, rest = unit.partition(" ")
    low = first.lower()
    if low == "people":
        one = first[:2] + "rson"
    elif low.endswith("ies") and len(low) > 3:
        one = first[:-3] + ("Y" if first[-3:].isupper() else "y")
    elif low.endswith(("sses", "shes", "ches", "xes")):
        one = first[:-2]
    elif low.endswith("s") and not low.endswith("ss") and len(low) > 1:
        one = first[:-1]
    else:
        one = first
    return one + sep + rest


def next_month(d: dt.date) -> dt.date:
    """The same day of the next month, or that month's last day when it's shorter."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def is_sign(unit) -> bool:
    return isinstance(unit, str) and len(unit) == 1 and unit in "$€£¥₹₩"
