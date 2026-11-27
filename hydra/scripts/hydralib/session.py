"""What the hooks do for a Hydra-OS chat besides their words:

  start(root, environ, now, session)  at the chat's start: Claude's Bash commands get Hydra-OS's own small tools, TMPDIR
                                      and Python through CLAUDE_ENV_FILE, which Claude Code sources before each
                                      Bash command (its hooks docs), and HYDRA_CLAUDE, the Claude Code running this chat,
                                      so hydra's own steps in it use the same one; then, with the helpers off, Home's
                                      server and one tick (hydralib/helpers.py)
  end(root, environ, now, session)    at the chat's end: with the helpers off and no Hydra-OS chat left, Home's server
                                      stopped

The Claude Code running this chat is the hook's own parent process, when it's a program named claude: Hydra-OS never
looks anywhere else for one. Neither says a word to Claude, and a chat outside the Hydra-OS folder never gets here.
Under any HYDRA_TEST_ switch, no parent is read and nothing is started, unless the test names its own
(HYDRA_TEST_CHAT_CLAUDE, HYDRA_TEST_CHAT_START=1). Python 3.9 standard library only."""
import os
import shlex

from . import config as cfg
from . import files, helpers, tools

EXPORTED = ("TMPDIR", "HYDRA_PYTHON", "CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS")


def env_lines(config, environ):
    """The export lines for CLAUDE_ENV_FILE: Hydra-OS's own tools first on PATH, the rest as session_env has them.
    Every value is quoted, so a home with a space or an accented letter in its path is fine."""
    env = cfg.session_env(config, environ)
    lines = ['export PATH=%s:"$PATH"' % shlex.quote(tools.bin_dir(config["root"]))]
    lines += ["export %s=%s" % (k, shlex.quote(env[k])) for k in EXPORTED if env.get(k)]
    return lines


def write_env_file(path, lines):
    """Add each line not there yet, so a resumed or compacted session doesn't stack them."""
    try:
        with open(path, encoding="utf-8") as f:
            have = set(f.read().splitlines())
    except OSError:
        have = set()
    new = [line for line in lines if line not in have]
    if new:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(new) + "\n")
    return new


def _claude_file(path):
    return isinstance(path, str) and os.path.isabs(path) and os.path.basename(path) == "claude" and \
        os.path.isfile(path) and os.access(path, os.X_OK)


def _comm(pid):
    return helpers.ps(pid, "comm")


def chat_claude(environ, ppid=None, look=_comm):
    """The Claude Code running this chat: the hook's own parent, by its full path, when it's a program named claude;
    else None."""
    if any(k.startswith("HYDRA_TEST_") for k in environ):
        given = environ.get("HYDRA_TEST_CHAT_CLAUDE") or ""
        return given if _claude_file(given) else None
    path = look(os.getppid() if ppid is None else ppid)
    return path if _claude_file(path) else None


def _testing(environ):
    return any(k.startswith("HYDRA_TEST_") for k in environ) and environ.get("HYDRA_TEST_CHAT_START") != "1"


def start(root, environ, now, session=""):
    config = cfg.load(root)
    claude = chat_claude(environ)
    path = environ.get("CLAUDE_ENV_FILE")
    if path:
        lines = env_lines(config, environ)
        if claude:
            lines.append("export HYDRA_CLAUDE=%s" % shlex.quote(claude))
        write_env_file(path, lines)
    if claude and claude != config.get("claude"):  # the app moves its own copy at each of its updates
        raw = files.read_json(cfg.path(root), {})
        if isinstance(raw, dict) and raw.get("contract") == cfg.CONTRACT:
            raw["claude"] = files.tilde(claude)
            cfg.write(root, raw)
            config = cfg.load(root)
    if not _testing(environ):
        helpers.chat_start(config, session, now)


def end(root, environ, now, session=""):
    if not _testing(environ):
        helpers.chat_end(cfg.load(root), session, now)
