"""Removing Hydra-OS itself, on the install through Claude (the privacy page: "Tell Claude 'remove Hydra-OS'. It asks
first, then moves your Hydra-OS folder to the Trash whole, so you can take it back. Your Claude chats stay in Claude.").

`hydra remove hydra` asks first: it prints ASK for Claude to put to the person, and changes nothing. With `--yes`, after
their yes, in order:
  1. the tick's run lock, as an update takes it: a run or a review is waited for briefly, then BUSY;
  2. Home's server and the tick stopped, as launch agents or as a chat started them, and their plists taken out of the
     person's LaunchAgents;
  3. every page and the store's list uninstalled at local scope, through the Claude Code running the chat;
  4. the folder moved whole into ~/.Trash, as ~/.Trash/Hydra-OS, or with the time added when that's taken.
If a step fails, the folder stays where it is, and the line says what's left. Then DONE, and NEXT for Claude: the
morning review's scheduled task deleted with the Claude app's own tool, then "You can close this chat now."

  remove(config, yes=False, env=None, now=None, load=None)   the lines hydra remove hydra says
"""
import datetime
import os

from . import applog, files, helpers, jobs, registry, update
from . import claude as cl
from . import config as cfg

ASK = ('Ask them, in these words: "Remove Hydra-OS? Your folder goes to the Trash whole, so you can take it back." On '
       'their yes, run hydra remove hydra --yes.')
BUSY = "Hydra-OS is busy for a moment. Say 'remove Hydra-OS' again in a minute."
DONE = "Hydra-OS is in the Trash, whole, so you can take it back. Your Claude chats stay in Claude."
NEXT = ('Next, if the Claude app has a scheduled task named "Hydra-OS morning review", delete it with the app\'s own '
        'scheduled-task tool and say so in one line; with none, say nothing of it. Then say "You can close this chat '
        'now."')
LEFT = "Hydra-OS couldn't be removed whole: %s. Your Hydra-OS folder is where it was."


class Stop(Exception):
    """One plain line on why nothing more was removed."""


def _trash(root, home, now):
    """Where the folder goes: ~/.Trash/<its name>, or with the time added when that's taken."""
    trash = os.path.join(home, ".Trash")
    if not os.path.isdir(trash):
        os.makedirs(trash, mode=0o700)
    name = os.path.basename(root.rstrip(os.sep)) or "Hydra-OS"
    dest = os.path.join(trash, name)
    if os.path.lexists(dest):
        dest = os.path.join(trash, "%s %s" % (name, now.strftime("%Y-%m-%d %H.%M.%S")))
    return dest


def remove(config, yes=False, env=None, now=None):
    root = config["root"]
    env = os.environ if env is None else env
    if not yes:
        return [ASK]
    now = now or datetime.datetime.now()
    home = env.get("HOME") or os.path.expanduser("~")
    lock = update.quiet(root, env, Stop, BUSY)
    try:
        conf = cfg.load(root)
        folder = jobs.agents_folder(home)
        for label in (conf["server"]["label"], conf["tick"]["label"]):
            jobs.unload(label)
            plist = os.path.join(folder, "%s.plist" % label)
            if os.path.exists(plist):
                os.unlink(plist)
        helpers.stop_plain(conf)  # one a chat or setup started, with the helpers off
        chat = cl.chat_claude(conf, env)
        market = files.read_json(os.path.join(root, "hydra", "store", ".claude-plugin", "marketplace.json"), {})
        names = [e["name"] for e in (market.get("plugins") or []) if isinstance(e, dict) and isinstance(e.get("name"), str)] \
            if isinstance(market, dict) else []
        for name in sorted(set(names) | {registry.MAIN}, key=lambda n: n == registry.MAIN):  # the main plugin last
            cl.run(chat, ["plugin", "uninstall", "%s@%s" % (name, cfg.STORE), "--scope", "local"],
                   conf.get("claude_config", ""), env, timeout=120, cwd=root)
        cl.run(chat, ["plugin", "marketplace", "remove", cfg.STORE], conf.get("claude_config", ""), env, timeout=120,
               cwd=root)
        left = [p["name"] for p in cl.plugins(chat, conf.get("claude_config", ""), cfg.STORE, cwd=root, env=env)]
        if left:
            raise Stop(LEFT % ("Claude still has %s" % ", ".join(sorted(left))))
        dest = _trash(root, home, now)
        applog.note("remove", "Hydra-OS moved to the Trash")
        os.rename(root, dest)  # whole, on the same disk; the run lock's file goes with it
    except Stop:
        raise
    except (OSError, KeyError, ValueError) as e:
        raise Stop(LEFT % ("a step stopped (%s)" % type(e).__name__))
    finally:
        try:
            lock.__exit__(None, None, None)
        except OSError:
            pass
    return [DONE, NEXT]
