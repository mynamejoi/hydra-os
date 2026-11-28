"""The `claude` command, as Hydra-OS asks it things in a step the person takes: its version, the installed plugins and
the MCP servers, and Claude Code's own plugin commands. Each call passes CLAUDE_CONFIG_DIR when config.json's
claude_config names one, and never ANTHROPIC_API_KEY. Nothing here starts a model."""
import json
import os
import shutil
import subprocess
import unicodedata

from . import applog
from . import config as cfg

TIMEOUT = 60
VERSION_WAIT = 30  # a Claude Code that doesn't answer `--version` in this long didn't start


def find(env=None):
    """The claude command, or None: the Claude Code running the person's chat, as it was given (HYDRA_CLAUDE: hydra-setup's
    --claude, or what a Hydra-OS chat's start notes for that chat's commands), else `claude` on PATH. Hydra-OS never
    looks anywhere else for it."""
    env = os.environ if env is None else env
    given = env.get("HYDRA_CLAUDE") or ""
    if os.path.isabs(given) and os.path.isfile(given) and os.access(given, os.X_OK):
        return given
    found = shutil.which("claude", path=env.get("PATH"))
    return os.path.abspath(found) if found else None


def chat_claude(config, env=None):
    """The Claude Code for a command the person asked for in their chat: HYDRA_CLAUDE, the one running that chat, when
    it's given, else config.json's."""
    env = os.environ if env is None else env
    given = env.get("HYDRA_CLAUDE") or ""
    if os.path.isabs(given) and os.path.isfile(given) and os.access(given, os.X_OK):
        return given
    return config["claude"]


ENGINES = os.path.join("Library", "Application Support", "Claude", "claude-code")  # the Claude app's own, in the home


def _runs(path):
    return isinstance(path, str) and os.path.isabs(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def app_engine(env=None, home=None):
    """The Claude app's own Claude Code, its newest version: the one documented place Hydra-OS looks when the copy
    config.json names is gone, as the app moves its copy at each of its updates. <version>/<build>/claude.app, run by
    its bundle's own program, which is named claude. Under any HYDRA_TEST_ switch, only the folder HYDRA_TEST_ENGINES
    names. None when there's none; Hydra-OS never installs or downloads Claude Code."""
    import plistlib
    import re
    env = os.environ if env is None else env
    if any(k.startswith("HYDRA_TEST_") for k in env):
        top = env.get("HYDRA_TEST_ENGINES") or ""
    else:
        top = os.path.join(home or os.path.expanduser("~"), ENGINES)
    try:
        versions = [v for v in os.listdir(top) if re.fullmatch(r"\d+(?:\.\d+)*", v)] if top else []
    except OSError:
        return None
    for version in sorted(versions, key=lambda v: tuple(int(p) for p in v.split(".")), reverse=True):
        try:
            builds = os.listdir(os.path.join(top, version))
        except OSError:
            continue
        for build in sorted(builds, key=lambda b: os.path.getmtime(os.path.join(top, version, b)), reverse=True):
            app = os.path.join(top, version, build, "claude.app")
            try:
                with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
                    program = plistlib.load(f).get("CFBundleExecutable")
            except (OSError, ValueError, plistlib.InvalidFileException):
                continue
            path = os.path.join(app, "Contents", "MacOS", str(program or ""))
            if program == "claude" and _runs(path):
                return path
    return None


def step_claude(config, env=None):
    """The Claude Code for a step a page's button started, with no chat: config.json's, the one the last Hydra-OS chat
    ran on, while it's there, else the Claude app's own newest (app_engine)."""
    return config["claude"] if _runs(config.get("claude")) else (app_engine(env) or config["claude"])


def _env(claude_config="", base=None):
    env = dict(os.environ if base is None else base)
    env.pop("ANTHROPIC_API_KEY", None)
    if claude_config:
        env["CLAUDE_CONFIG_DIR"] = claude_config
    return env


def run(claude, args, claude_config="", env=None, timeout=TIMEOUT, cwd=None):
    """(exit code, stdout) of `claude <args>`, never through a shell. (127, "") when it can't start."""
    try:
        r = subprocess.run([claude] + list(args), env=_env(claude_config, env), cwd=cwd, capture_output=True,
                           text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        applog.note("claude", "%s: %s" % (shape(args), type(e).__name__))
        return 127, ""
    first = next((x for x in (r.stderr or "").splitlines() if x.strip()), "") if r.returncode else ""
    applog.note("claude", "%s: exit %d%s" % (shape(args), r.returncode, ": " + first[:200] if first else ""))
    return r.returncode, r.stdout


def shape(args):
    """A call as the log names it: its command words, with no path, value or output, "claude plugin install x@y"."""
    words = []
    for a in args:
        if a.startswith("/") or (a.startswith("-") and words) or len(words) == 3:
            break
        words.append(a)
    return " ".join(["claude"] + words)


def version(claude, claude_config=""):
    """(the version as read, (2, 1, 310)) or ("", None): None when it didn't answer within VERSION_WAIT seconds,
    ended with an error, or said no version."""
    code, out = run(claude, ["--version"], claude_config, timeout=VERSION_WAIT)
    text = out.strip().split("\n")[0] if code == 0 else ""
    ver = cfg.version_tuple(text)
    return ("%d.%d.%d" % ver if ver else text.split(" ")[0]) if text else "", ver


def plugins(claude, claude_config="", marketplace="", cwd=None, env=None):
    """[{"name", "version", "path", "folder"}] for each installed, enabled plugin, from `claude plugin list --json`, kept
    to one marketplace when one is named: path is Claude Code's own copy (installPath), folder the one it loads the
    plugin in place from (readFromFolder), when there's one. Run from cwd: Hydra-OS installs at local scope in <root>, and
    a plugin installed so lists as enabled only from that folder.
    One row each: 2.1.310 lists a plugin once for every folder it's installed in, each enabled from a folder that has it,
    so on a Mac that set Hydra-OS up in an earlier folder, every app came twice. This folder's own row is kept when it's
    there."""
    code, out = run(claude, ["plugin", "list", "--json"], claude_config, env, cwd=cwd)
    try:
        rows = json.loads(out) if code == 0 and out.strip() else []
    except ValueError:
        rows = []
    found, at = [], {}
    for p in rows if isinstance(rows, list) else []:
        pid = str(p.get("id") or "")
        name, _, market = pid.partition("@")
        if not name or not p.get("enabled") or (marketplace and market != marketplace):
            continue
        row = {"name": name, "version": str(p.get("version") or ""), "path": str(p.get("installPath") or ""),
               "folder": str(p.get("readFromFolder") or "")}
        if name not in at:
            at[name] = len(found)
            found.append(row)
        elif cwd and p.get("projectPath") and _same_folder(str(p["projectPath"]), cwd):
            found[at[name]] = row
    return found


def _same_folder(a, b):
    """The same folder, links followed and accents in one form, as a home with a decomposed accent has it."""
    return unicodedata.normalize("NFC", os.path.realpath(a)) == unicodedata.normalize("NFC", os.path.realpath(b))


def mcp_servers(claude, claude_config="", env=None):
    """The MCP server names `claude mcp list` shows, names only."""
    code, out = run(claude, ["mcp", "list"], claude_config, env)
    names = []
    for line in out.splitlines() if code == 0 else []:
        head = line.split(":", 1)[0].strip()
        if head and not head.lower().startswith(("checking", "no mcp")) and len(head) <= 80:
            names.append(head)
    return names

