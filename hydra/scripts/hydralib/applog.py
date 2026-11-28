"""Hydra-OS's own notes: one line each, "<who>: <what>", in Hydra-OS's own words, never a command's output.

They go to one place, the folder's own log ("Hydra-OS keeps a log of what ran, in ~/Hydra-OS/hydra/logs, with keys,
passwords and email addresses taken out. It stays on your Mac."): <root>/hydra/logs/hydra.log, once its process has said
which folder it works in (use). Nothing is written outside the Hydra-OS folder. Each line has
  its time and is cleaned: no control character, anything that looks like a key, a token, a password said, or an email
  taken out as "[taken out]", the home folder written as ~, and at most 400 characters. Over 256 KB, the log becomes
  hydra.1.log, in place of the one before. The folder is 0700 and the files 0600. A folder that isn't set up yet, with
  no hydra/config.json, gets nothing, so a setup's own checks of the folder see nothing of the log's.

hydra report reads the log's last lines (hydralib/report.py). Python 3.9 standard library only."""
import datetime
import os
import re

MOST = 300  # characters of one note
LINE_MOST = 400  # characters of a line as the log keeps it
LOG_MOST = 256 * 1024  # bytes of the log before it becomes hydra.1.log
TAKEN = "[taken out]"

# has them), a password or a key said with its value (the message hook's), and an email
SECRETS = [re.compile(p, re.I if i >= 9 else 0) for i, p in enumerate([
    r"sk-ant-[A-Za-z0-9_-]{20,}",
    r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{32,}",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bAIza[0-9A-Za-z_-]{35}\b",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
    r"(?<![\w.-])\d(?:[ -]?\d){12,18}(?![\w.-])",  # a card-shaped number: 13 to 19 digits, spaced or dashed
    r"\b(?:password|passcode|passwd|pwd|pin)\b\s*(?:is|was|=|:)\s*\S+",
    r"\b(?:client[ _-]?secret|api[ _-]?key|access[ _-]?token|secret[ _-]?key|token)\b\s*(?:is|=|:)\s*\S+",
])]
_root = None  # the Hydra-OS folder this process works in, once it says (use)


def use(root):
    """The Hydra-OS folder whose log this process's notes go to. Each entry point says it once it knows."""
    global _root
    _root = os.path.abspath(root) if root else None


def log_path(root):
    return os.path.join(root, "hydra", "logs", "hydra.log")


def clean(text, home=None):
    """A line as the log keeps it: control characters out, anything SECRETS finds taken out, the home folder as ~,
    and at most LINE_MOST characters."""
    s = "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in str(text))
    for pattern in SECRETS:
        s = pattern.sub(TAKEN, s)
    home = os.path.expanduser("~") if home is None else home
    if home and home != "/":
        s = s.replace(home, "~")
    return s[:LINE_MOST]


def _keep(line, now=None):
    root = _root
    if not root or not os.path.isfile(os.path.join(root, "hydra", "config.json")):
        return
    path = log_path(root)
    try:
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder, mode=0o700)
        if os.path.exists(path) and os.path.getsize(path) > LOG_MOST:
            os.replace(path, os.path.join(folder, "hydra.1.log"))
        stamp = (now or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (stamp, clean(line)))
    except (OSError, ValueError):
        pass  # a note never stops what it notes


def note(who, text, env=None):
    """One line for the folder's own log, once its process said which folder it works in. env: kept for its callers."""
    _keep("%s: %s" % (who, " ".join(str(text).split())[:MOST]))


def last(root, n=40):
    """The log's last n lines, from hydra.log and, before it, hydra.1.log, each as it was kept."""
    out = []
    for name in ("hydra.log", "hydra.1.log"):
        try:
            with open(os.path.join(root, "hydra", "logs", name), encoding="utf-8", errors="replace") as f:
                lines = [l.rstrip("\n") for l in f.read(LOG_MOST * 2).splitlines() if l.strip()]
        except OSError:
            lines = []
        out = lines + out
        if len(out) >= n:
            break
    return out[-n:]
