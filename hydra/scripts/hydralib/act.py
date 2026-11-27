"""The save route: one action an installed app declares, run through the app's own script, with no Claude between.

  handle(config, app, action, body)               Home's server, POST /api/act/<app>/<action>, HYDRA_BY=page
  chat(config, app, action, fields, yes, token)   `hydra act`: the check without --yes, the save with it, HYDRA_BY=chat

What it holds to:
- the app, its installed release and its record come from `<root>/hydra/registry.json`, the main app's own record
  `<root>/hydra/` among them, for setup's self-test;
- its fields: an `id` field's `of`, `optional`, and `words`, typed text, only on `answer`, on Goals' own actions,
  and on an action the stock layout.json names as a block's `entry`, with exactly one;
- Goals' actions alone may name `yours: ["goals.json"]`;
- the script runs with config.json's `python`, `HYDRA_ROOT`, `HYDRA_BY`, `CLAUDE_CONFIG_DIR` when set, and never
  `ANTHROPIC_API_KEY`;
- one action at a time for each app across processes too: the server's and `hydra act`'s each hold flock on
  `<root>/hydra/locks/<app>.lock`, an empty file of Hydra-OS's own, while its script runs. It's never a lock in the app's
  record, which is the app's own to lock as it writes (Goals flocks its record folder).

A request runs only what the app declares, and stops at the first step that fails. The answer is the script's own
last line, as it is, or the route's own refusal, {"ok": false, "said": "<one line>"}, with a status: 400 a body or
field the action doesn't take, 404 no such app or action, 502 the app's side broke, 503 busy or not set up, 504 too
slow. Nothing here starts a shell, claude or a network call, or logs, and nothing writes but the app's own script,
besides the route's empty lock file.
Python 3.9 standard library only."""
import datetime
import decimal
import fcntl
import json
import os
import re
import selectors
import signal
import subprocess
import threading
import time
import unicodedata

from . import config as cfg
from . import files, health, registry

TIMEOUT = 30  # seconds a script may run (column.md)
BUDGET = 36  # seconds for the whole request, so the page has its answer inside its 40 (page.md)
MAX_COLUMN = 256 * 1024
MAX_OUT = 256 * 1024
MAX_IDS = 20000
MAX_FIELDS = 8
MAX_WORDS = 120
CONFIRMS = ("undo", "read-back", "once")
PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
GOALS = "goals"

NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")
FIELD = re.compile(r"[a-z][a-z0-9_]{0,31}")
WORD = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._-]{0,63}")  # a fixed argument: a plain word, not starting with -
SCRIPT = re.compile(r"scripts/(?:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}/){0,3}[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.py")
PART = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.-]{0,63}")
ID = re.compile(r"[A-Za-z0-9._:][A-Za-z0-9._:-]{0,63}")
APP = re.compile(r"[a-z][a-z0-9-]{0,39}")
TOKEN = re.compile(r"[A-Za-z0-9._:+/=-]{1,256}")
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
FLOAT = re.compile(r"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")  # HTML's valid floating-point number
CONTROL = re.compile(r"[\x00-\x1f\x7f  ]")
# No field is named for a recipient, a message, a place or a command (column.md), as a word of its name.
NOT_A_FIELD = {"to", "cc", "bcc", "recipient", "email", "address", "phone", "draft", "message", "body", "subject", "text",
               "note", "url", "link", "path", "file", "command", "shell", "prompt", "query"}
# What no said a page shows, and no typed words a script takes, may hold: an address, a phone number, a key, a home
# folder, a link (page.md, What may show; column.md, the answer path's words).
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\+?\(?[0-9][0-9 ().-]{6,}[0-9]")  # with ten digits or more, once days and times are left out
WHEN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[ T][0-9]{1,2}:[0-9]{2})?|[0-9]{1,2}:[0-9]{2}")
KEY = re.compile(r"[A-Za-z0-9+/=]{24,}")  # a run of 24 or more, letters and digits mixed
LINK = re.compile(r"(?i)[a-z][a-z0-9+.-]*://|\bwww\.|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|co|app|dev|ai|me|"
                  r"uk|us|ca|de|fr|eu|edu|gov|info|biz|xyz|ly|gg|tv|so|sh|site|page|link)(?![a-z0-9-])")

NOT_DECLARED = "This page's buttons aren't declared as Hydra-OS needs, so nothing ran."
BUSY = "This page is saving something else. Try again in a moment."
SLOW = "The page's script took too long and was stopped."
CHECK_BROKE = "The page's script didn't answer as it should. Nothing was saved."
SAVE_BROKE = "The page's script didn't answer as it should, so it may not have saved."
SENT_WRONG = "That can't be saved as it was sent."


class Answer(Exception):
    """The route's own refusal: a status, and the one line the page or chat shows."""

    def __init__(self, status, said):
        super().__init__(said)
        self.status, self.said = status, said


# ---- the app, its release and its declaration --------------------------------------------------------------------

def _inside(path, base):
    real, base = os.path.realpath(path), os.path.realpath(base)
    return real if real.startswith(base + os.sep) else None


def where(config, app):
    """(the installed release's root, the record) for an installed app, from the registry, or a refusal."""
    if not isinstance(app, str) or not APP.fullmatch(app):
        raise Answer(404, "That page isn't installed.")
    entry = registry.app(config["root"], app)  # the main app too: setup's self-test saves through its own record
    if not entry:
        raise Answer(404, "That page isn't installed.")
    plugin = entry.get("root")
    if not isinstance(plugin, str) or not os.path.isdir(plugin):
        raise Answer(503, "This page's files aren't where Hydra-OS expects them, so nothing ran. Say 'repair Hydra-OS' to Claude.")
    record = os.path.join(config["root"], app)
    if not entry.get("record") or not files.same_path(entry["record"], record):  # however each spells an accent
        raise Answer(503, "This page's folder isn't where Hydra-OS keeps it, so nothing ran. Say 'repair Hydra-OS' to Claude.")
    if not os.path.isdir(record):
        raise Answer(503, "This page's folder isn't set up yet, so nothing ran. Say 'repair Hydra-OS' to Claude.")
    return os.path.realpath(plugin), record


def manifest(plugin, app):
    """column.json, read from inside the release, or a refusal."""
    path = _inside(os.path.join(plugin, "column.json"), plugin)
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) > MAX_COLUMN:
            raise ValueError
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError, RecursionError):
        raise Answer(502, "This page's settings can't be read, so nothing ran. Say 'repair Hydra-OS' to Claude.")
    if not isinstance(doc, dict) or doc.get("id") != app:
        raise Answer(502, "This page's settings aren't its own, so nothing ran. Say 'repair Hydra-OS' to Claude.")
    return doc


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and decimal.Decimal(repr(v)).is_finite()


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _command(c):
    """[script, fixed arguments...]: one of the app's .py files under scripts/, then plain words."""
    return (isinstance(c, list) and 1 <= len(c) <= 9 and isinstance(c[0], str) and SCRIPT.fullmatch(c[0]) is not None
            and all(isinstance(w, str) and WORD.fullmatch(w) for w in c[1:]))


def _field(name, f, typed_ok):
    """One field in column.md's shape. typed_ok: the action may take `words`."""
    if not isinstance(name, str) or not FIELD.fullmatch(name) or set(re.split(r"[^a-z]+", name)) & NOT_A_FIELD:
        return False
    if not isinstance(f, dict) or f.get("optional", False) not in (True, False):
        return False
    kind = f.get("kind")
    if "of" in f and kind not in ("choice", "id"):  # a choice's `of` is its words; an id's names another field
        return False
    if kind == "choice":
        of = f.get("of")
        return (isinstance(of, list) and 1 <= len(of) <= 20
                and all(isinstance(w, str) and 1 <= len(w) <= 40 and w == w.strip() and not CONTROL.search(w) for w in of)
                and len(set(of)) == len(of))
    if kind == "date":
        a, b = f.get("from"), f.get("to")
        return _whole(a) and _whole(b) and -36600 <= a <= b <= 36600
    if kind == "number":
        lo, hi, step = f.get("min"), f.get("max"), f.get("step")
        return _number(lo) and _number(hi) and lo <= hi and (step is None or (_number(step) and step > 0))
    if kind == "id":
        return _command(f.get("list")) and ("of" not in f or (isinstance(f["of"], str) and f["of"] != name))
    if kind == "words":
        return typed_ok and _whole(f.get("max")) and 1 <= f["max"] <= MAX_WORDS
    return False


def _of(f):
    """True for an `id` field whose list runs with another field's value."""
    return f.get("kind") == "id" and "of" in f


def _writes(w):
    if not isinstance(w, list) or len(w) > 32:
        return False
    for p in w:
        if not isinstance(p, str) or not p or p.startswith("/"):
            return False
        parts = p[:-1].split("/") if p.endswith("/") else p.split("/")
        if len(parts) > 8 or not all(PART.fullmatch(x) and x not in (".", "..") for x in parts):
            return False
        if parts[0] in ("page", "shared") or p in ("home.json", "say.json"):  # the rebuild writes those
            return False
    return True


def entries(plugin):
    """The actions the release's stock layout.json names as a block's `entry`."""
    path = _inside(os.path.join(plugin, "layout.json"), plugin)
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) > MAX_COLUMN:
            return set()
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError, RecursionError):
        return set()
    if not isinstance(doc, dict) or doc.get("contract") != "layout/v1" or not isinstance(doc.get("blocks"), list):
        return set()
    return {b["entry"] for b in doc["blocks"] if isinstance(b, dict) and isinstance(b.get("entry"), str)}


def declared(doc, app, entry_names=()):
    """{name: action} for every action column.json declares, each in column.md's shape, or a refusal for them all.
    A `words` field is taken by `answer`, by Goals' own actions, and by an action a block's entry names in the stock
    layout (entry_names), which then holds exactly one."""
    acts = doc.get("actions")
    if acts is None:
        return {}
    if not isinstance(acts, list) or len(acts) > 64:
        raise Answer(502, NOT_DECLARED)
    out = {}
    for a in acts:
        good = (isinstance(a, dict) and isinstance(a.get("name"), str) and NAME.fullmatch(a["name"]) is not None
                and a["name"] not in out and _command(a.get("script")) and a.get("confirm") in CONFIRMS
                and _writes(a.get("writes")))
        fields = a.get("fields", {}) if good else None
        typed_ok = good and (a["name"] == "answer" or app == GOALS or a["name"] in entry_names)
        if good and typed_ok and a["name"] != "answer" and app != GOALS and isinstance(fields, dict):
            typed_ok = sum(1 for f in fields.values() if isinstance(f, dict) and f.get("kind") == "words") <= 1
        good = (good and isinstance(fields, dict) and len(fields) <= MAX_FIELDS
                and all(_field(n, f, typed_ok) for n, f in fields.items())
                # an `of` names another field of the same action, one that's always sent and is itself no words
                and all(f["of"] in fields and not fields[f["of"]].get("optional") and fields[f["of"]].get("kind") != "words"
                        for f in fields.values() if _of(f))
                # Goals' actions alone write under <root>/yours/, and only goals.json
                and ("yours" not in a or (app == GOALS and a["yours"] == ["goals.json"]))
                # an undo action names what takes it back, a read-back may name one too, and a once never carries one
                and (a["confirm"] != "undo" or "undo" in a)
                and (a["confirm"] != "once" or "undo" not in a)
                and ("undo" not in a or (isinstance(a["undo"], str) and NAME.fullmatch(a["undo"]) is not None)))
        if not good:
            raise Answer(502, NOT_DECLARED)
        out[a["name"]] = a
    named = {a["undo"] for a in out.values() if "undo" in a}
    for a in out.values():
        if "undo" in a and (a["undo"] not in out or a["undo"] == a["name"]):
            raise Answer(502, NOT_DECLARED)
        if a["confirm"] == "once" and a["name"] not in named:  # once is only for an action another names as its undo
            raise Answer(502, NOT_DECLARED)
    return out


# ---- the request's fields ----------------------------------------------------------------------------------------

def body_of(value):
    """(fields, token) from a page's JSON, or a 400."""
    if not isinstance(value, dict) or "fields" not in value or set(value) - {"fields", "token"}:
        raise Answer(400, SENT_WRONG)
    fields, token = value["fields"], value.get("token")
    if not isinstance(fields, dict):
        raise Answer(400, SENT_WRONG)
    if token is not None and (not isinstance(token, str) or not TOKEN.fullmatch(token)):
        raise Answer(400, "That can't be saved: its confirmation isn't one the app gave.")
    return fields, token


def plain(d):
    """A number in plain decimals, as the script takes it: 350, 0.1, -2.5."""
    d = d.normalize()
    return "0" if d == 0 else format(d, "f")


def number(v, f):
    """The number as plain decimals when it's within its bounds and on its step, else None."""
    try:
        if isinstance(v, str) and len(v) <= 40 and FLOAT.fullmatch(v):
            d = decimal.Decimal(v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            d = decimal.Decimal(repr(v))
        else:
            return None
        lo, hi = decimal.Decimal(repr(f["min"])), decimal.Decimal(repr(f["max"]))
        if not d.is_finite() or d < lo or d > hi:
            return None
        if f.get("step") is not None:
            q = (d - lo) / decimal.Decimal(repr(f["step"]))
            if q != q.to_integral_value():
                return None
        return plain(d)
    except (decimal.DecimalException, ValueError, OverflowError):
        return None


def day(v, f, today):
    if not isinstance(v, str) or not DAY.fullmatch(v):
        return None
    try:
        d = datetime.date(int(v[:4]), int(v[5:7]), int(v[8:]))
        lo, hi = today + datetime.timedelta(days=f["from"]), today + datetime.timedelta(days=f["to"])
    except (ValueError, OverflowError):
        return None
    return v if lo <= d <= hi else None


def clean_said(said):
    """True when a line holds nothing a page never shows: an email address, a phone number, a key or a home folder."""
    home = os.path.expanduser("~")
    if EMAIL.search(said) or "/Users/" in said or "~/" in said or (len(home) > 1 and home in said):
        return False
    if any(re.search(r"[0-9]", k) and re.search(r"[A-Za-z]", k) for k in KEY.findall(said)):
        return False
    return not any(sum(ch.isdigit() for ch in m.group(0)) >= 10 for m in PHONE.finditer(WHEN.sub(" ", said)))


def words(v, most):
    """Typed words as the script takes them, or None: one line of 1 to `most` characters once normalised (NFC, its
    spaces collapsed), with no control character, address, link, key or home folder."""
    if not isinstance(v, str) or len(v) > 4 * most:
        return None
    v = unicodedata.normalize("NFC", v).strip()
    if "\n" in v or "\r" in v or CONTROL.search(v.replace("\t", " ")):
        return None
    v = " ".join(v.split())
    if not 1 <= len(v) <= most or LINK.search(v) or not clean_said(v):
        return None
    return v


def _say(name):
    """A field's name, as a refusal may repeat it: only a name in a field's own shape."""
    return name if isinstance(name, str) and FIELD.fullmatch(name) else "that"


def values(decl, fields, today, ids_of):
    """[(name, value as the script takes it)], in the declared order, or a 400 that names the field. An `of` field's
    list runs with its field's checked value, so that field is checked first."""
    want = decl.get("fields", {})
    for name in fields:
        if name not in want:
            raise Answer(400, "That can't be saved: this doesn't take %s." % _say(name))
    got = {}
    for name, f in sorted(want.items(), key=lambda kv: _of(kv[1])):
        if name not in fields:
            if f.get("optional"):
                continue
            raise Answer(400, "That can't be saved: %s is missing." % name)
        v, kind, s = fields[name], f["kind"], None
        if kind == "choice":
            s = v if isinstance(v, str) and v in f["of"] else None
        elif kind == "date":
            s = day(v, f, today)
        elif kind == "number":
            s = number(v, f)
        elif kind == "id":
            of = (f["of"], got[f["of"]]) if _of(f) else None
            s = v if isinstance(v, str) and ID.fullmatch(v) and v in ids_of(f["list"], of) else None
        elif kind == "words":
            s = words(v, f["max"])
        if s is None:
            raise Answer(400, "That can't be saved: %s isn't one this takes." % name)
        got[name] = s
    return [(name, got[name]) for name in want if name in got]


# ---- running the app's script ------------------------------------------------------------------------------------

def environment(config, by):
    """The script's whole environment: run_env's, HYDRA_BY, and only the system's PATH, so nothing it starts finds
    claude."""
    env = cfg.run_env(config, {"HYDRA_BY": by})
    env["PATH"] = PATH
    return env


def start(config, plugin, argv, env, deadline, saving=False):
    """(exit code, what it printed), from `python -B -s <argv>` run in the release's root and stopped, with anything it
    started, after 30 seconds or at the request's deadline. A refusal when it ran too long or printed too much."""
    script = _inside(os.path.join(plugin, argv[0]), os.path.join(plugin, "scripts"))
    if not script or not os.path.isfile(script):
        raise Answer(502, "This app's files are incomplete, so nothing ran. Say 'repair Hydra-OS' to Claude.")
    python = config.get("python") or ""
    if not os.path.isabs(python) or not os.access(python, os.X_OK):
        raise Answer(503, health.said("python-missing"))
    stop = min(deadline, time.monotonic() + TIMEOUT)
    try:
        p = subprocess.Popen([python, "-B", "-s"] + argv, cwd=plugin, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    except OSError:
        raise Answer(502, "This app's script couldn't start, so nothing ran.")
    out, ended, broke = bytearray(), False, False
    sel = selectors.DefaultSelector()
    try:
        sel.register(p.stdout, selectors.EVENT_READ)
        while len(out) <= MAX_OUT:
            left = stop - time.monotonic()
            if left <= 0:
                break
            if sel.select(left):
                chunk = os.read(p.stdout.fileno(), 65536)
                if not chunk:
                    ended = True
                    break
                out += chunk
        if ended:
            try:
                p.wait(timeout=max(0.05, stop - time.monotonic()))
                return p.returncode, bytes(out)
            except subprocess.TimeoutExpired:  # it closed its output but kept running
                pass
    except OSError:
        broke = True
    finally:
        sel.close()
        if p.returncode is None:  # nothing has reaped the leader, so its group is still its own: stop all of it
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        p.stdout.close()
    if broke or len(out) > MAX_OUT:
        raise Answer(502, SAVE_BROKE if saving else CHECK_BROKE)
    raise Answer(504, SLOW + (" It may not have saved." if saving else " Nothing was saved."))


def _no_constant(name):
    raise ValueError("no %s" % name)


def answer_of(ran, needs_token, saving):
    """The script's last line, as it is, when it's an answer (column.md), as (bytes, the object); else a refusal."""
    broke = Answer(502, SAVE_BROKE if saving else CHECK_BROKE)
    code, out = ran
    lines = [x for x in out.decode("utf-8", "replace").splitlines() if x.strip()]
    if not lines:
        raise broke
    line = lines[-1].strip()
    try:
        a = json.loads(line, parse_constant=_no_constant)
    except (ValueError, RecursionError):
        raise broke
    if (not isinstance(a, dict) or not isinstance(a.get("ok"), bool) or not isinstance(a.get("said"), str)
            or not 1 <= len(a["said"]) <= 200 or CONTROL.search(a["said"])
            or (code, a["ok"]) not in ((0, True), (2, False))):
        raise broke
    if "token" in a and (not isinstance(a["token"], str) or not TOKEN.fullmatch(a["token"])):
        raise broke
    if needs_token and a["ok"] and "token" not in a:
        raise broke
    if not clean_said(a["said"]):
        if saving and a["ok"]:  # it saved: the page must know, so only the words change
            a["said"] = "Saved."
            return json.dumps(a, ensure_ascii=False).encode("utf-8"), a
        raise Answer(502, "The app's answer held something a page never shows. Nothing was saved.")
    return line.encode("utf-8"), a


def _ids(ran):
    """The ids a list prints: its last line, a JSON list of ids in their shape, or a refusal."""
    lines = [x for x in ran[1].decode("utf-8", "replace").splitlines() if x.strip()] if ran[0] == 0 else []
    try:
        ids = json.loads(lines[-1]) if lines else None
    except (ValueError, RecursionError):
        ids = None
    if not isinstance(ids, list) or len(ids) > MAX_IDS or not all(isinstance(i, str) and ID.fullmatch(i) for i in ids):
        raise Answer(502, "This app's choices couldn't be read, so nothing ran.")
    return set(ids)


_LOCKS = {}
_GUARD = threading.Lock()


def lock_path(root, app):
    return os.path.join(root, "hydra", "locks", app + ".lock")


class _Held:
    """One action at a time for an app: a lock for the server's threads, then flock on `<root>/hydra/locks/<app>.lock`
    for every process, `hydra act`'s too. The file is empty and only ever made, never written."""

    def __init__(self, app, path, deadline):
        self.app, self.path, self.deadline, self.fd, self.lock = app, path, deadline, None, None

    def __enter__(self):
        with _GUARD:
            self.lock = _LOCKS.setdefault(self.app, threading.Lock())
        if not self.lock.acquire(timeout=max(0.0, self.deadline - time.monotonic())):
            raise Answer(503, BUSY)
        try:
            files.folder(os.path.dirname(self.path))
            self.fd = os.open(self.path, os.O_RDONLY | os.O_CREAT, 0o600)
            while True:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except BlockingIOError:
                    if time.monotonic() >= self.deadline:
                        raise Answer(503, BUSY)
                    time.sleep(0.05)
        except OSError:
            self._let_go()
            raise Answer(503, "Hydra-OS's own folder can't be written, so nothing ran. Say 'repair Hydra-OS' to Claude.")
        except BaseException:
            self._let_go()
            raise

    def __exit__(self, *exc):
        self._let_go()

    def _let_go(self):
        if self.fd is not None:
            os.close(self.fd)  # closing it lets the flock go
            self.fd = None
        self.lock.release()


def _run(config, app, action, fields, token, decide, by, today, deadline):
    """(the answer's bytes, its object) for one action. decide(declaration) says whether this is the save, or refuses."""
    plugin, record = where(config, app)
    decl = declared(manifest(plugin, app), app, entries(plugin)).get(action) if isinstance(action, str) else None
    if decl is None:
        raise Answer(404, "That isn't something this app declares.")
    save = decide(decl)
    env = environment(config, by)
    with _Held(app, lock_path(config["root"], app), deadline):
        lists = {}

        def ids_of(command, of=None):
            argv = list(command) + ["--record", record] + (["--%s=%s" % of] if of else [])
            key = tuple(argv)
            if key not in lists:
                lists[key] = _ids(start(config, plugin, argv, env, deadline))
            return lists[key]

        vals = values(decl, fields, today, ids_of)
        argv = list(decl["script"]) + ["--record", record] + ["--%s=%s" % (n, s) for n, s in vals]
        if not save:  # the check: its said, its token when the script gives one, and nothing written
            return answer_of(start(config, plugin, argv, env, deadline), decl["confirm"] == "read-back", False)
        argv += ["--yes"] + (["--token=" + token] if token is not None else [])
        return answer_of(start(config, plugin, argv, env, deadline, saving=True), False, True)


def refusal(said):
    return json.dumps({"ok": False, "said": said}, ensure_ascii=False).encode("utf-8")


def handle(config, app, action, value, today=None, budget=BUDGET):
    """(status, the answer's bytes) for a page's POST /api/act/<app>/<action>, the parsed JSON body `value`. A read-back
    sent without a token runs its check; anything else runs the save, with the token for a read-back."""
    deadline = time.monotonic() + budget

    def decide(decl):
        read_back = decl["confirm"] == "read-back"
        if token is not None and not read_back:
            raise Answer(400, "That can't be saved: only a read-back takes a confirmation.")
        return not (read_back and token is None)

    try:
        fields, token = body_of(value)
        return 200, _run(config, app, action, fields, token, decide, "page", today or datetime.date.today(), deadline)[0]
    except Answer as a:
        return a.status, refusal(a.said)


def chat(config, app, action, fields, yes=False, token=None, today=None, budget=BUDGET):
    """(status, the answer as an object) for `hydra act <app> <action> --<field>=<value> ... [--yes [--token=<t>]]`.
    Without --yes it runs the check, for any action, and the answer carries the script's token when it gives one;
    nothing is written. With --yes it runs the save, passing the token when given. A read-back's save needs one."""
    deadline = time.monotonic() + budget

    def decide(decl):
        if yes and token is None and decl["confirm"] == "read-back":
            raise Answer(400, "Run the check first, then save with --yes and the token it printed.")
        return bool(yes)

    try:
        if not isinstance(fields, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items()):
            raise Answer(400, SENT_WRONG)
        if token is not None and (not yes or not isinstance(token, str) or not TOKEN.fullmatch(token)):
            raise Answer(400, "A token goes with --yes, as the check printed it.")
        return 200, _run(config, app, action, fields, token, decide, "chat", today or datetime.date.today(), deadline)[1]
    except Answer as a:
        return a.status, {"ok": False, "said": a.said}
