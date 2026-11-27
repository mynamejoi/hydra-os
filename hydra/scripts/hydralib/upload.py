"""A file dropped on an app's own page, filed into that app's folder by Home's server: Apple Health's export, for one,
which a long-time iPhone's
export takes to a few gigabytes.

  take(config, app, name, length, read, now)  ->  (code, said, path or None)

- **What's taken** is the app's own declared upload source (column.json `sources`, `kind` "upload"): only a name whose
  extension is in its `accepts`, landing in its `folder` (inbox/ by default) inside the app's record.
- **It's streamed,** a piece at a time, into a hidden file in that folder, mode 0600, then renamed whole, as
  export-<date and time>.<extension>. It's never read into memory, and nothing is kept anywhere else.
- **One file at a time** an app, and never more than MAX bytes, or more than this Mac has room for.
- **Then,** when the source isn't recorded yet and declares its own `source` and `reads`, it's recorded, as the
  person's own act on the page. The answer is the source's own `filed` line when it gives one.
The file never passes through chat, Claude or a prompt. Python 3.9 standard library only."""
import datetime
import fcntl
import os
import shutil

from . import files, registry, sources

MAX = 8 * 1024 ** 3  # above a long-time iPhone's export
ROOM = 512 * 1024 ** 2  # what's kept free on the Mac besides the file
PIECE = 1024 ** 2

NOT_TAKEN = "That app doesn't take a file."
NO_LENGTH = "That file couldn't be sent. Drop it again."
EMPTY = "That file is empty."
TOO_BIG = "That file is larger than Hydra-OS takes, which is 8 GB."
NO_ROOM = "Your Mac doesn't have room for this file. Free up some space, then drop it again."
BUSY = "Another file is still coming in. Drop this one again once it's in."
CUT_SHORT = "That file stopped coming in before it was all here. Drop it again."


def declared(root, app):
    """(the app's registry entry, its declared upload source), or (entry, None)."""
    entry = registry.app(root, app) or {}
    col = files.read_json(os.path.join(entry.get("root") or "", "column.json"), {})
    decl = [s for s in (col.get("sources") or []) if isinstance(s, dict) and isinstance(s.get("id"), str)] \
        if isinstance(col, dict) else []
    return entry, next((s for s in decl if s.get("kind") == "upload"), None), decl


def folder(record, upload):
    """The folder inside the app's record its upload source reads, made when it isn't there; None for one that would
    leave the record."""
    rel = str(upload.get("folder") or "inbox/").strip("/")
    if not record or not rel or any(part in ("", ".", "..") for part in rel.split("/")) or rel.startswith("~"):
        return None
    path = os.path.join(record, rel)
    if not os.path.realpath(path).startswith(os.path.realpath(record) + os.sep):
        return None
    files.folder(path)
    return path


def extension(name, accepts):
    ext = os.path.splitext(os.path.basename(str(name or "")))[1].lower().lstrip(".")
    return ext if ext and ext in [str(a).lower() for a in accepts or []] else None


def said_kinds(accepts):
    kinds = [".%s" % a for a in accepts or []]
    return kinds[0] if len(kinds) == 1 else ", ".join(kinds[:-1]) + " or " + kinds[-1]


def take(config, app, name, length, read, now=None):
    """File one dropped file. read(n): up to n bytes of the body. Returns (code, said, path)."""
    root = config["root"]
    now = now or datetime.datetime.now().astimezone()
    entry, upload, decl = declared(root, app)
    title = str(entry.get("title") or app)
    if not entry or not upload:
        return 404, NOT_TAKEN, None
    ext = extension(name, upload.get("accepts"))
    if not ext:
        return 400, "%s takes a %s file." % (title, said_kinds(upload.get("accepts"))), None
    if not isinstance(length, int) or length < 0:
        return 411, NO_LENGTH, None
    if length == 0:
        return 400, EMPTY, None
    if length > MAX:
        return 413, TOO_BIG, None
    inbox = folder(entry.get("record") or "", upload)
    if not inbox:
        return 404, NOT_TAKEN, None
    if shutil.disk_usage(inbox).free < length + ROOM:
        return 507, NO_ROOM, None
    lock_path = os.path.join(root, "hydra", "locks", "%s.upload.lock" % app)
    files.folder(os.path.dirname(lock_path))
    lock = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 409, BUSY, None
        path = _stream(inbox, ext, length, read, now)
        if path is None:
            return 400, CUT_SHORT, None
    finally:
        os.close(lock)
    _record(root, app, upload, decl, now)
    filed = upload.get("filed")
    said = filed if isinstance(filed, str) and 0 < len(filed) <= 120 and "\n" not in filed else \
        "Got it. %s is reading it now." % title
    return 200, said, path


def _stream(inbox, ext, length, read, now):
    stamp = now.strftime("%Y-%m-%d-%H%M%S")
    tmp = os.path.join(inbox, ".export-%s.%s.part" % (stamp, ext))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    left = length
    try:
        with os.fdopen(fd, "wb") as f:
            while left > 0:
                piece = read(min(PIECE, left))
                if not piece:
                    break
                f.write(piece)
                left -= len(piece)
            f.flush()
            os.fsync(f.fileno())
        if left:
            os.unlink(tmp)
            return None
        os.chmod(tmp, 0o600)
        final, n = os.path.join(inbox, "export-%s.%s" % (stamp, ext)), 2
        while os.path.exists(final):
            final = os.path.join(inbox, "export-%s-%d.%s" % (stamp, n, ext))
            n += 1
        os.replace(tmp, final)
        return final
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _record(root, app, upload, decl, now):
    """The drop is the person's own act on the page: the app's upload source is recorded when it isn't yet, and when it
    declares its own `source` and `reads`."""
    if not (isinstance(upload.get("source"), str) and isinstance(upload.get("reads"), str)):
        return
    if any(r.get("app") == app and r.get("id") == upload["id"] for r in sources.read(root)):
        return
    reg = registry.read(root)
    installed = {a["id"] for a in reg.get("apps", []) if a.get("kind") != "main"}
    try:
        sources.add(root, app, upload["source"], "file", upload["reads"], installed, decl, today=now.date())
    except sources.Refused:
        pass  # filed all the same; Claude can record it with the person
