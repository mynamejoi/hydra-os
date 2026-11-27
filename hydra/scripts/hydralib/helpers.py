"""Hydra-OS's two helpers, Home's server and the tick, as the person chose at setup or later in their chat.

config.json's "helpers" says which, "on" or "off", as setup wrote it from the person's answer. With the helpers on,
both are launch agents in ~/Library/LaunchAgents: Home's server starts at login, and the tick runs
every 15 minutes, starting each page's daily read once it's due. With them off, nothing of Hydra-OS runs while no
Hydra-OS chat is open: Home's server starts with a chat in the Hydra-OS folder and stops when the last one ends, and
each chat's start runs one tick in the background, so the day's reads catch up then.

  on(config, load, home)        hydra helpers on: a server a chat started stopped, both jobs written and loaded
  off(config, home)             hydra helpers off: both jobs stopped and their plists removed; Home's server goes on
                                for the chat that asked, until the last Hydra-OS chat ends
  heal(config)                  at a chat's start: with the helpers off, an older install's jobs taken away; with them
                                on, their link pointed again at the Python that moved, and both started again
  chat_start(config, session)   a Hydra-OS chat's start: heal, then, with the helpers off, Home's server started when
                                it doesn't answer, and one tick started in the background
  chat_end(config, session)     a Hydra-OS chat's end, with the helpers off: with no chat left, Home's server stopped
  start_plain, stop_plain       Home's server as a process of its own, kept in <root>/hydra/server.pid
  ps(pid, field)                one process's command line or program, as ps prints it under a UTF-8 locale

Nothing here starts Claude Code. Python 3.9 standard library only."""
import datetime
import http.client
import os
import signal
import subprocess
import sys
import time
import unicodedata

from . import config as cfg
from . import applog, files, jobs, registry

ON = ("Hydra-OS's helpers are on: Home's server starts each time you log in to this Mac, and the tick runs every 15 "
      "minutes, starting each page's daily read once it's due.")
OFF = ("Hydra-OS's helpers are off: nothing of Hydra-OS runs while no Hydra-OS chat is open. Home's server starts with a "
       "Hydra-OS chat, and the day's reads catch up then.")
DIDNT = "Hydra-OS's helpers didn't start. Offer to try again."
SERVER_WAIT = 15.0
CHAT_WAIT = 3.0  # how long a chat's start waits for Home's server, so the hook stays quick
CHAT_MOST = datetime.timedelta(hours=12)  # a chat that ended without saying so stops counting after this


def _pid_path(root):
    return os.path.join(root, "hydra", "server.pid")


def _chats_path(root):
    return os.path.join(root, "hydra", "chats.json")


def is_on(config):
    return config.get("helpers") == "on" or bool((config.get("tick") or {}).get("on"))


def chose_off(config):
    """Whether the person chose the helpers off, so a Hydra-OS chat starts Home's server and the day's reads: never
    for a folder that never chose."""
    return config.get("helpers") == "off" and not bool((config.get("tick") or {}).get("on"))


def answers(config, timeout=1.0):
    """Whether Home's server answers on this Mac's loopback address."""
    try:
        c = http.client.HTTPConnection("127.0.0.1", config["home"]["port"], timeout=timeout)
        c.request("GET", "/api/panel", headers={"Host": "127.0.0.1:%d" % config["home"]["port"]})
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except (OSError, http.client.HTTPException):
        return False


def _main_root(config):
    main = registry.app(config["root"], registry.MAIN) or {}
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return main.get("root") if os.path.isdir(main.get("root") or "") else here


def ps(pid, field):
    """One process's `field` as ps prints it, "command" (its command line) or "comm" (its program's path), in NFC; ""
    when there's none. ps runs under a UTF-8 locale: with none, it prints a path's letters outside ASCII escaped, and
    no path would match."""
    try:
        out = subprocess.run(["/bin/ps", "-ww", "-o", field + "=", "-p", str(int(pid))], capture_output=True,
                             encoding="utf-8", errors="surrogateescape", timeout=5,
                             env={"PATH": "/usr/bin:/bin", "LC_ALL": "en_US.UTF-8"}).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return unicodedata.normalize("NFC", out)


def _ours(config, pid):
    """Whether a recorded pid is still this folder's own Home server, by its own command line."""
    line = ps(pid, "command")
    return (os.sep + "server.py") in line and line.endswith(unicodedata.normalize("NFC", "--root " + config["root"]))


def start_plain(config, main_root=None, wait=SERVER_WAIT):
    """Home's server as a process of its own, when it doesn't answer: started from the main plugin's release, its pid
    kept. True once it answers."""
    if answers(config):
        return True
    root = config["root"]
    proc = subprocess.Popen(
        [config["python"], "-B", "-s", os.path.join(main_root or _main_root(config), "scripts", "server.py"), "--root",
         root], cwd=root, env=cfg.run_env(config), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    files.write_json(_pid_path(root), {"pid": proc.pid, "at": _now().isoformat()})
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if answers(config, timeout=0.5):
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.1)
    return False


def stop_plain(config, wait=SERVER_WAIT):
    """The Home server a chat or setup started, stopped: only the pid this folder kept, and only while it's still that
    server."""
    root = config["root"]
    doc = files.read_json(_pid_path(root), {})
    pid = doc.get("pid") if isinstance(doc, dict) else None
    if isinstance(pid, int) and pid > 1 and _ours(config, pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        end = time.monotonic() + wait
        while time.monotonic() < end and _ours(config, pid):
            time.sleep(0.1)
    try:
        os.unlink(_pid_path(root))
    except OSError:
        pass


def plain_running(config):
    doc = files.read_json(_pid_path(config["root"]), {})
    pid = doc.get("pid") if isinstance(doc, dict) else None
    return isinstance(pid, int) and pid > 1 and _ours(config, pid)


def _write_on(config, on):
    raw = files.read_json(cfg.path(config["root"]), {})
    raw["tick"] = dict(raw.get("tick") or {}, on=bool(on))
    raw["helpers"] = "on" if on else "off"
    cfg.write(config["root"], raw)
    return cfg.load(config["root"])


def on(config, load=jobs.load, home=None):
    """Both helpers as launch agents, after the person's yes. A server a chat started gives way to the job's."""
    if is_on(config) and config.get("helpers") == "on":
        return [ON]
    stop_plain(config)
    jobs.retire_others(config, home)  # an older build's job this one doesn't use
    config = _write_on(config, True)  # first, so the tick finds itself on as it starts
    folder = jobs.agents_folder(home)
    labels = [config["server"]["label"], config["tick"]["label"]]
    loaded = load(jobs.write(config, _main_root(config), folder, labels)) or []
    end = time.monotonic() + SERVER_WAIT
    while time.monotonic() < end and not answers(config, timeout=0.5):
        time.sleep(0.2)
    return [ON] if sorted(loaded) == sorted(labels) and answers(config) else [DIDNT]


def off(config, home=None):
    """Both launch agents stopped and their plists removed, after the person's yes. Home's server goes on as a process
    of its own for the chat that asked, until the last Hydra-OS chat ends."""
    folder = jobs.agents_folder(home)
    for label in (config["server"]["label"], config["tick"]["label"]):
        jobs.unload(label)
        plist = os.path.join(folder, "%s.plist" % label)
        if os.path.exists(plist):
            os.unlink(plist)
    config = _write_on(config, False)
    _wait_gone(config)
    start_plain(config)
    return [OFF]


def _wait_gone(config, wait=SERVER_WAIT):
    end = time.monotonic() + wait
    while time.monotonic() < end and answers(config, timeout=0.5):
        time.sleep(0.2)


def restart_plain(config, main_root):
    """After an update: a server a chat started, started again from the new release."""
    if plain_running(config):
        stop_plain(config)
        start_plain(config, main_root)


def _now():
    return datetime.datetime.now().astimezone().replace(microsecond=0)


def _chats(root, now):
    doc = files.read_json(_chats_path(root), {})
    got = doc.get("sessions") if isinstance(doc, dict) and isinstance(doc.get("sessions"), dict) else {}
    out = {}
    for sid, at in got.items():
        try:
            when = datetime.datetime.fromisoformat(str(at))
        except ValueError:
            continue
        if when.tzinfo and now - when < CHAT_MOST:
            out[sid] = at
    return out


def heal(config):
    """The helpers' own mending at a chat's start, so what's left over mends with nobody doing anything. With them off,
    a job of this build's own labels that an older install left loaded or written is booted out and its plist removed
    (jobs.retire_own). With them on, when the Python their link should name has moved, as after an Xcode or macOS
    change, the link is pointed at it again and both jobs start again. Returns what it mended, for the log."""
    if chose_off(config):
        gone = jobs.retire_own(config)
        if gone.get(config["server"]["label"]) == "running":
            _wait_gone(config, wait=CHAT_WAIT)
        return sorted(gone)
    if not is_on(config) or jobs.untouchable():
        return []
    link = jobs.program(config)
    want = jobs.real_python(config["python"])
    if os.path.islink(link) and os.readlink(link) == want and os.path.exists(link):
        return []
    labels = [config["server"]["label"]] + ([config["tick"]["label"]] if (config.get("tick") or {}).get("on") else [])
    loaded = jobs.loader()(jobs.write(config, _main_root(config), jobs.agents_folder(), labels)) or []
    return ["the link"] + sorted(loaded)


def chat_start(config, session, now=None):
    """A Hydra-OS chat's start: first the helpers' own mending (heal). With the helpers on, the jobs do the rest. With
    them off: this chat counted, Home's server started when it doesn't answer, and one tick started in the background
    for the day's reads."""
    try:
        mended = heal(config)
    except (OSError, subprocess.SubprocessError, ValueError):
        mended = []
    if mended:
        applog.note("helpers", "mended at a chat's start: %s" % ", ".join(mended))
    if not chose_off(config):
        return
    root = config["root"]
    now = now or _now()
    chats = _chats(root, now)
    chats[str(session or "chat")] = now.isoformat()
    files.write_json(_chats_path(root), {"sessions": chats})
    start_plain(config, wait=CHAT_WAIT)
    subprocess.Popen([config["python"], "-B", "-s", os.path.join(_main_root(config), "scripts", "tick.py"), "--root",
                      root, "--how", "terminal"], cwd=root, env=cfg.run_env(config), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)


def chat_end(config, session, now=None):
    """A Hydra-OS chat's end. With the helpers off and no Hydra-OS chat left, Home's server a chat started stops."""
    if not chose_off(config):
        return
    root = config["root"]
    now = now or _now()
    chats = _chats(root, now)
    chats.pop(str(session or "chat"), None)
    files.write_json(_chats_path(root), {"sessions": chats})
    if not chats:
        stop_plain(config)


if __name__ == "__main__":
    sys.exit(0)
