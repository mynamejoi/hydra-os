"""Files the way every contract asks for them: written whole or not at all, mode 0600 in 0700 folders, read with a
size cap, and `.jsonl` appended one line at a time. Python 3.9 standard library only."""
import json
import os
import re
import tempfile
import unicodedata

MAX_READ = 4 * 1024 * 1024
NEWER = "That was saved by a newer Hydra-OS."
CONTRACT = re.compile(r"([a-z][a-z0-9-]*)/v([0-9]{1,4})")


class Newer(Exception):
    """A file a newer Hydra-OS saved, a newer version of its contract: never written over by this one."""

    def __init__(self):
        super().__init__(NEWER)


def contract_of(value):
    """(name, version) of a contract such as "settings/v1", or None."""
    m = CONTRACT.fullmatch(value) if isinstance(value, str) else None
    return (m.group(1), int(m.group(2))) if m else None


def refuse_newer(path, contract):
    """Newer when the file at path says it's a newer version of contract than this Hydra-OS writes, so an older core,
    after a rollback or on another Mac's copy, never resets what a newer one saved."""
    want = contract_of(contract)
    doc = read_json(path, None)
    have = contract_of(doc.get("contract")) if isinstance(doc, dict) else None
    if want and have and have[0] == want[0] and have[1] > want[1]:
        raise Newer()


def folder(path):
    """Make a folder and its parents at 0700, and leave one that was there already as it is. Hydra-OS sets a mode only
    on what it has just made: macOS held setup's server, started from the downloaded app, on a chmod of a folder another
    process had made, and a folder Hydra-OS didn't make keeps its mode."""
    missing, p = [], os.path.abspath(path)
    while not os.path.isdir(p):  # each level it makes, made 0700 one at a time: makedirs gives only the last its mode
        missing.append(p)
        if os.path.dirname(p) == p:
            break
        p = os.path.dirname(p)
    for p in reversed(missing):
        try:
            os.mkdir(p, 0o700)
        except FileExistsError:
            continue  # made by another just now: theirs, as it is
        os.chmod(p, 0o700)  # its own new folder: mkdir's mode passes through the umask
    return path


def write_text(path, text):
    """Write text whole or not at all: a temporary file in the same folder, mode 0600, then a rename."""
    parent = os.path.dirname(os.path.abspath(path))
    folder(parent)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json(path, value):
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_json(path, default=None, cap=MAX_READ):
    """The file's JSON, or default when it's missing, too big or not JSON."""
    try:
        if os.path.getsize(path) > cap:
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, RecursionError):
        return default


def append_line(path, value):
    """Append one JSON line, the file 0600 in a 0700 folder."""
    folder(os.path.dirname(os.path.abspath(path)))
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)  # 0600 when it makes it; one there is as it is
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")


def read_lines(path, cap=MAX_READ):
    """Every JSON line that reads as an object, oldest first; a bad line is skipped."""
    try:
        if os.path.getsize(path) > cap:
            return []
        with open(path, encoding="utf-8") as f:
            raw = f.read().splitlines()
    except OSError:
        return []
    out = []
    for line in raw:
        try:
            v = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def same_path(a, b):
    """The same path, links followed and accents in one form: a folder whose name holds an accent can be stored in one
    Unicode form and given in the other (a home folder made from Python, a root setup was given by the app), and is one
    folder either way (claude.py's _same_folder)."""
    return unicodedata.normalize("NFC", os.path.realpath(a)) == unicodedata.normalize("NFC", os.path.realpath(b))


def within(path, top):
    """Whether path is the folder top or inside it, told by the folders themselves, so no spelling of either name, nor a
    link, makes one folder two (an accented home read as outside its own Hydra-OS folder)."""
    try:
        stop = os.stat(top)
    except OSError:
        return False
    here = os.path.realpath(path)
    while True:
        try:
            if os.path.samestat(os.stat(here), stop):
                return True
        except OSError:
            pass
        up = os.path.dirname(here)
        if up == here:
            return False
        here = up


def tilde(path):
    """A path as a person reads it: ~/ for the home folder, never the home folder spelled out."""
    home = os.path.expanduser("~")
    path = str(path)
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path
