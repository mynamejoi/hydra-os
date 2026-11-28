"""`<root>` and `config.json`.

<root> is found, in order: $HYDRA_ROOT; the nearest folder above the working folder that holds hydra/config.json; and
~/Hydra-OS. Code reads every path, port, label and store name from config.json, never from a constant."""
import datetime
import os
import pwd
import re

from . import files

CONTRACT = "install/v1"
DEFAULT_ROOT = "~/Hydra-OS"
TESTED_CLAUDE = (2, 1, 310)
STORE = "hydra-os"
FIRST_PORT = 8792


class NotInstalled(Exception):
    """Hydra-OS isn't installed where this looked."""


def expand(path):
    return os.path.abspath(os.path.expanduser(path)) if path else path


def find_root(cwd=None, env=None):
    """The folder that holds hydra/config.json, as install.md finds it, or raise NotInstalled."""
    env = os.environ if env is None else env
    given = env.get("HYDRA_ROOT")
    if given:
        root = expand(given)
        if os.path.isfile(os.path.join(root, "hydra", "config.json")):
            return root
        raise NotInstalled("Hydra-OS isn't installed at the folder HYDRA_ROOT names.")
    here = os.path.abspath(cwd or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(here, "hydra", "config.json")):
            return here
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    root = expand(DEFAULT_ROOT)
    if os.path.isfile(os.path.join(root, "hydra", "config.json")):
        return root
    raise NotInstalled("Hydra-OS isn't installed on this Mac yet.")


def path(root):
    return os.path.join(root, "hydra", "config.json")


def load(root=None, cwd=None, env=None):
    """config.json as a dict, with every path in it expanded; raise NotInstalled when there's none to read. The root is
    the folder that holds this config.json, whatever its `root` says, so a reader whose HOME differs from the writer's
    (a test's throwaway one) still finds its own root."""
    root = os.path.abspath(root or find_root(cwd, env))
    c = files.read_json(path(root))
    if not isinstance(c, dict) or c.get("contract") != CONTRACT:
        raise NotInstalled("Hydra-OS's config.json can't be read.")
    out = dict(c)
    out["root"] = root
    out["python"] = expand(c.get("python"))
    out["claude"] = expand(c.get("claude"))
    out["claude_config"] = expand(c.get("claude_config") or "")
    store = dict(c.get("store") or {})
    store["folder"] = expand(store.get("folder") or os.path.join(root, "hydra", "store"))
    out["store"] = store
    return out


def new(root, python, claude, claude_version, claude_config="", port=FIRST_PORT, now=None):
    """A fresh config.json for setup: every path written with ~/ when it's under the home folder."""
    now = now or datetime.datetime.now().astimezone()
    return {
        "contract": CONTRACT,
        "root": files.tilde(root),
        "python": files.tilde(python),
        "claude": files.tilde(claude),
        "claude_version": claude_version,
        "claude_config": files.tilde(claude_config) if claude_config else "",
        "store": {"name": STORE, "folder": files.tilde(os.path.join(root, "hydra", "store"))},
        "home": {"listen": "127.0.0.1", "port": port, "names": []},
        "tick": {"every_minutes": 15, "label": "os.hydra.tick", "on": False},
        "server": {"label": "os.hydra.home"},
        "installed_at": now.replace(microsecond=0).isoformat(),
    }


def write(root, config):
    files.refuse_newer(path(root), CONTRACT)
    files.write_json(path(root), config)


SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def session_env(config, given=None):
    """What every Hydra-OS process gets: Hydra-OS's own small tools first on PATH, then Claude Code's folder, then the
    system's, with no Homebrew; HYDRA_PYTHON; Claude Code's git status snapshot off; and once setup has made it
    (hydralib/tools.py), TMPDIR in the Hydra-OS folder. Never a DEVELOPER_DIR: Hydra-OS runs on its own Python, which
    needs nothing of Apple's developer tools. given: kept for its callers, and not read."""
    from . import tools  # noqa: PLC0415 (tools imports files, as this module does)
    root = config["root"]
    claude_dir = os.path.dirname(config["claude"]) if config.get("claude") else ""
    env = {"PATH": ":".join(p for p in (tools.bin_dir(root), claude_dir, SYSTEM_PATH) if p),
           "HYDRA_PYTHON": config.get("python") or "",
           "CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS": "1"}
    if tools.ready(root):
        env["TMPDIR"] = tools.tmp_dir(root)
    return {k: v for k, v in env.items() if v}


def account():
    """The person's account name: the environment's USER or LOGNAME, else the system's for this process, since a launch
    agent or a bare environment has neither."""
    name = os.environ.get("USER") or os.environ.get("LOGNAME")
    if not name:
        try:
            name = pwd.getpwuid(os.getuid()).pw_name
        except KeyError:
            name = ""
    return name


def run_env(config, extra=None):
    """The environment every job, save and run starts with: HYDRA_ROOT, USER and LOGNAME, CLAUDE_CONFIG_DIR when set,
    session_env's PATH and the rest, and never ANTHROPIC_API_KEY. Claude Code
    reads its sign-in from the Keychain under the account's name, so without USER every model call is "Not logged in"
    while `claude auth status` still says signed in."""
    env = {"HOME": os.path.expanduser("~"), "LANG": "en_US.UTF-8",
           "LC_ALL": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
           "HYDRA_ROOT": config["root"]}
    user = account()
    if user:
        env["USER"] = env["LOGNAME"] = user
    env.update(session_env(config, os.environ))
    if config.get("claude_config"):
        env["CLAUDE_CONFIG_DIR"] = config["claude_config"]
    if os.environ.get("HYDRA_PLUGINS"):
        env["HYDRA_PLUGINS"] = os.environ["HYDRA_PLUGINS"]
    for name in test_pass(os.environ):
        env[name] = os.environ[name]
    for k, v in (extra or {}).items():
        env[k] = v
    env.pop("ANTHROPIC_API_KEY", None)
    return env


PASS_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
NEVER_PASS = ("ANTHROPIC_", "CLAUDE_", "HYDRA_", "PYTHON", "DYLD_", "LD_")
NEVER_NAMES = ("PATH", "HOME", "LANG", "LC_ALL", "SHELL", "TMPDIR")


def test_switches(environ=None):
    """For tests only: the HYDRA_TEST_ switches of this process, for a server it starts, as jobs.test_load gives a
    test's job its own, so that server and every step it starts reach only the test's stand-ins. A real process has
    none."""
    return {k: v for k, v in (os.environ if environ is None else environ).items() if k.startswith("HYDRA_TEST_")}


def test_pass(environ):
    """For tests only: the variables HYDRA_TEST_PASS names (comma-separated, A-Z, 0-9 and _) that are set, which every
    run, save and page build then carries as they are, such as a fake service's address. Never an Anthropic, Claude,
    Hydra-OS, Python or loader variable, nor PATH or HOME. No job sets HYDRA_TEST_PASS."""
    out = []
    for name in str(environ.get("HYDRA_TEST_PASS") or "").split(","):
        name = name.strip()
        if (PASS_NAME.fullmatch(name) and not name.startswith(NEVER_PASS) and name not in NEVER_NAMES
                and name in environ and name not in out):
            out.append(name)
    return out


VERSION = re.compile(r"(?<![\d.])(\d+)\.(\d+)\.(\d+)(?![\d.])")


def version_tuple(text):
    """(2, 1, 310) from "2.1.310 (Claude Code)", or from the first such version in its first line, whatever's around it
    ("Claude Code 2.2.0"), or None. A Claude Code that answers in a new shape still answered."""
    m = VERSION.search((text or "").strip().split("\n")[0])
    return tuple(int(x) for x in m.groups()) if m else None
