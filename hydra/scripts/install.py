#!/usr/bin/env python3
"""Hydra-OS's setup, run by bin/hydra-setup in the person's own chat after their yes, from the plugin Claude installed
off the hydra-os list:

    <python> <plugin>/scripts/install.py [--root DIR] [--jobs] [--port N] [--python PATH]

The plugin carries the free pages in its release/ folder. Setup lays them out, with the plugin itself, as one release
folder in <root>/hydra/.setup/, and takes that away when it ends. The steps run in order, and setup stops at the first
that fails, with one plain line on what stopped it:

1. Room: about 1 GB free on this Mac, or nothing is changed.
2. Claude Code: the one this chat runs on (HYDRA_CLAUDE, as hydra-setup finds it, or `claude` on PATH), at version
   2.1.310 or newer. Setup never installs, updates or signs in to it, and never starts a model.
3. The folder: <root>, ~/Hydra-OS by default, and its folders, each 0700. A folder that syncs to a cloud, or one that
   holds anything of the person's own, is refused. config.json is written.
4. The store: the release's pages copied into <root>/hydra/store/, a plugin list named hydra-os, added to Claude Code
   at local scope from <root>, and each page it lists installed there, so Hydra-OS's hooks and skills are on only in
   chats in <root>. Each page's own folder is made and its first page drawn.
5. The command and the folder's rules: <root>/hydra/bin/hydra, and <root>/.claude/settings.json allowing it by name,
   and the morning review's writes to its own answers folder alone.
6. Home's server. With --jobs, the person's yes to the helpers, Home's server and the tick are launch agents that
   start at login; without it, nothing starts at login: Home's server runs as setup's own process, and later starts
   with each Hydra-OS chat (hydralib/helpers.py).
7. <root>/.claude/launch.json, so the Claude app's Browser pane opens Home.
8. The hydra-os-get list, which the plugin was installed from at local scope in <root>, left: so every later update
   comes only through hydra update, checked against Hydra-OS's key.
9. The self-test, written to <root>/hydra/setup.json, each check that failed said with what to do; then the signed
   catalog of pages is read, so Home's Shop shows them at once.

A fresh setup that stops takes back all it made, so nothing is left changed. Over a folder already set up, setup picks
up where it was left, and keeps the person's goals, sources and pages as they are. It exits 0 once done, or 2 with its
line.

Setup never signs anyone in, never reads or keeps a token, and never writes Claude Code's own settings or ~/.claude:
Claude Code's own plugin commands do that. Python 3.9 standard library only."""
import argparse
import datetime
import http.client
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from hydralib import claude as cl  # noqa: E402
from hydralib import config as cfg  # noqa: E402
from hydralib import applog, files, health, jobs, pages, registry, settings, shop, space, tools, you  # noqa: E402
from hydralib import release as builds  # noqa: E402  (Setup takes a release folder of that name)

PLUGIN = os.path.dirname(HERE)  # <release>/hydra/<version>
RELEASE = os.path.dirname(os.path.dirname(PLUGIN))
SYNCED = ("/Library/Mobile Documents/", "/Library/CloudStorage/", "/Dropbox/", "/OneDrive", "/Google Drive/", "/Box/",
          "/pCloud Drive/", "/iCloud Drive/")
NAME = re.compile(r"[a-z][a-z0-9-]{0,40}")
SERVER_WAIT = 15.0
GONE_WAIT = 15.0  # seconds for an older Home server to let its port go
SAVE_QUESTION = {"id": "q-setup", "kind": "one", "text": "Setup's own check.", "picks": [{"id": "ok", "label": "OK"}]}
SYNCED_SAID = ("Hydra-OS can't live in a folder that syncs to a cloud, such as iCloud Drive or Dropbox. Pick a folder "
               "on this Mac, then run setup again.")
JOBS_OFF = "Hydra-OS's helpers stay off: Home and the day's reads start with each Hydra-OS chat."
JOBS_ON = "Hydra-OS's helpers are on, and start again each time you log in to this Mac."
MAC_MOST_OLD = (13, 0)
NOT_A_MAC = "Hydra-OS needs a Mac with macOS 13 Ventura or later. Nothing was set up."
NO_CLAUDE = "Setup couldn't find the Claude Code this chat runs on, so nothing was changed."
OLD_CLAUDE = ("The Claude Code this chat runs on is older than Hydra-OS needs, version 2.1.310 or newer, so nothing was "
              "changed. Once Claude is up to date, run this same hydra-setup again.")
BROKEN_RELEASE = "This copy of Hydra-OS is damaged, so nothing was set up. Install Hydra-OS again."
# the catalog of pages, and its mirror on another host of the same account, for a raw-host outage or rate limit
SHOP_CATALOG = "https://raw.githubusercontent.com/mynamejoi/hydra-os/main/catalog.json"
SHOP_MIRROR = "https://mynamejoi.github.io/hydra-os/catalog.json"
# setup's own lines in the person's chat, while it works and at its end; Claude says the messages around them
CHAT_STEPS = ("Adding your pages…", "Starting them…")
CHAT_DONE = "Hydra-OS is set up."
# what Claude does next, carried by setup's own last lines: the plugin's skills load only in a chat in the Hydra-OS
# folder, so the chat that runs setup has only these. Claude tells the person in its own words
CHAT_NEXT = ("Next, tell them in a few plain sentences what's now set up: their pages in a Hydra-OS folder on this Mac"
             " with its own copy of Python; two helpers that start at login to show their pages and keep them fresh; a"
             " short morning review that uses a little of their Claude plan each day, and a bit more on Mondays, when "
             "Research looks into their goals; nothing about them sent anywhere; and that Help turns any of it off or "
             "removes Hydra-OS. Then tell them you'll move this chat into their Hydra-OS folder, so their pages and "
             "you stay together. Then move this chat into %s with the Claude app's own folder change, which asks them "
             "first, and open Home in the Browser pane from %s. Then walk them through it, in these words or close to "
             "them: \"Here's what you have. Home, beside this chat, is your day on one page: your goals at the top, and"
             " what your pages found below. Research looks into your goals overnight, and each day I'll ask how "
             "they're going. There's nothing to learn: tell me what you want, in your own words. Ask me for a new "
             "chart or new data on any page, and the Shop has more pages when you want them.\" Then ask: \"What's one "
             "thing you're working toward?\" Their answer is their first goal.")
CHAT_FAILED = ("Tell them that this step didn't finish and that nothing was changed, then offer to try again from "
               "here. On their yes, run this same hydra-setup again.")
CHAT_SAY_IT = ("Tell them that, in your own words. Once they've renamed it, offer to try again, and on their yes, run "
               "this same hydra-setup again.")
CHAT_UNFINISHED = (' After that, tell them about each line above that starts "Something didn\'t finish setting up", and '
                   'offer to finish it: on their yes, run this same hydra-setup again.')
CHAT_BROKE = "Hydra-OS's setup stopped on something it didn't expect."
# the folder's own rules: Hydra-OS's command, and the Write tool to the morning review's answers alone, which in the
# scheduled task's don't-ask mode is all it may write (Edit rules cover Write; "/" is the folder itself)
ALLOW = ("Bash(hydra:*)", "Edit(/hydra/think/answers/**)")
PUBLIC_LIST = "hydra-os-get"  # the public plugin list a buyer adds (shell/mac-app/make_list.py), left once setup is done
LOCAL_SETTINGS = "settings.local.json"  # Claude Code's own file for a plugin installed at local scope
NOT_OURS = "There's already a folder named Hydra-OS in your home folder, so nothing was changed. It needs another name first."


class Stop(Exception):
    """A step that failed, with its plain words."""


def tilde(path):
    return files.tilde(path)


NAMES = ("Hydra-OS", "Home", "Claude")  # a check's words that begin with one keep its capital mid-sentence


def mid(said):
    """A check's words inside a sentence: its first letter lowered, unless they begin with a name, and no full stop."""
    said = said.rstrip(".")
    return said if said.startswith(NAMES) else said[:1].lower() + said[1:]


def synced(path):
    real = os.path.realpath(path) + "/"
    return any(part in real for part in SYNCED)


def free_port(first):
    """The first free port from first up, for Home; 0 asks the Mac for any free one, as a test's setup does, so a test
    never takes Home's own 8792."""
    if not first:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    for port in range(first, first + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise Stop("No port from %d up is free on this Mac. Close what's using them, then run setup again." % first)


class Setup:
    def __init__(self, root=None, jobs_on=False, port=None, release=None, env=None, home=None, load=jobs.load,
                 python=None, python_from=None):
        self.env = dict(os.environ if env is None else env)
        self.env.pop("ANTHROPIC_API_KEY", None)
        self.root = os.path.abspath(os.path.expanduser(root or cfg.DEFAULT_ROOT))
        applog.use(self.root)  # its notes go to the folder's own log, once it's set up
        self.jobs_on, self.port = jobs_on, port
        self.given_release = release  # a release folder given, as tests give one; else the plugin's own (assemble)
        self.release = release or RELEASE
        self.home = home or os.path.expanduser("~")
        self.server = None  # the server process setup started, when it started one
        self.checks = {}
        self.claude = self.version = ""
        self.config = None
        self.existing = None
        self.build = builds.own(PLUGIN)  # this release's own build, from its build.json, when it has one
        self.updating = False  # a folder an older build set up
        # the Python Hydra-OS runs on: its own, from hydra-setup's checked download (python_from), kept in
        # <root>/hydra/python/ by python_step; else the one given; else the one running setup
        self.python_from = os.path.abspath(python_from) if python_from else None
        self.python = os.path.abspath(python) if python else sys.executable
        self.loaded = []  # every launch agent this setup started, so a stop takes them back
        loader = load
        self.load = lambda paths: self.loaded.extend(loader(paths) or []) or self.loaded_last(paths)

    def loaded_last(self, paths):
        """What the last load started, as jobs.load answers: each label whose plist it was given and that's loaded now."""
        labels = [os.path.basename(p)[:-len(".plist")] for p in paths]
        return [lbl for lbl in labels if lbl in self.loaded]

    # ---- the run --------------------------------------------------------------------------------------------------

    def run(self):
        """Setup in the person's own chat. It prints only CHAT_STEPS as it goes and CHAT_DONE at its end, then
        CHAT_NEXT, since the plugin's own setup skill loads only in a new chat. A stop prints its one line, then
        CHAT_FAILED. 0 once done; 2 with one line when a step stopped it. A fresh setup that stops takes away all it
        made (undo), so nothing is left changed; over a folder already set up, it picks up where it was left."""
        fresh = False
        try:
            self.space_step()
            self.existing = self.read_existing()
            fresh = self.existing is None
            if fresh and not self.ours():
                raise Stop(NOT_OURS)
            self.python_step()
            self.release = self.given_release or self.assemble()
            self.claude_step()
            if fresh:
                self.root_step()
            else:
                self.resume_config()
            you.fill_from_account(self.root, self.env)  # Home's greeting, from the Mac account's own full name
            print(CHAT_STEPS[0], flush=True)
            if fresh:
                self.store_step()
                self.command_step()
            else:
                self.resume_step()
            self.catalog_step()
            print(CHAT_STEPS[1], flush=True)
            self.server_step()
            self.jobs_step()
            self.launch_step()
            if fresh:
                settings.mark_whats_new(self.root, str((registry.app(self.root, registry.MAIN) or {}).get("version")
                                                       or "0"))
            self.leave_public_list()
            self.python_tidy()
        except Stop as e:
            if fresh:
                self.undo()
            applog.note("install", "setup stopped: %s" % e)
            print(str(e), flush=True)
            print(CHAT_SAY_IT if str(e) == NOT_OURS else CHAT_FAILED, flush=True)
            return 2
        except Exception as e:  # a step that broke is taken back as a stop is, so nothing is left half made
            if fresh:
                self.undo()
            applog.note("install", "setup broke: %r" % (e,))
            print(CHAT_BROKE, flush=True)
            print(CHAT_FAILED, flush=True)
            return 2
        finally:
            shutil.rmtree(os.path.join(self.root, "hydra", ".setup"), ignore_errors=True)
        self.self_test()
        unfinished = False
        for name in ("server", "save", "plugins", "tick", "jobs", "list"):
            ok, said = self.checks.get(name, (True, ""))
            if not ok:
                unfinished = True
                print("Something didn't finish setting up: %s." % mid(said))
        print(CHAT_DONE, flush=True)
        print(CHAT_NEXT % (tilde(self.root), tilde(os.path.join(self.root, ".claude", "launch.json"))) +
              (CHAT_UNFINISHED if unfinished else ""), flush=True)
        return 0

    # ---- the steps ------------------------------------------------------------------------------------------------

    def space_step(self):
        """Room first: setup needs 1 GB free, or it changes nothing."""
        try:
            space.need(self.root, space.SETUP, self.env)
        except space.Short as e:
            raise Stop(str(e))

    def claude_step(self):
        """This Mac, Python, and the Claude Code this chat runs on, at a version Hydra-OS was tested with."""
        if not os.path.isfile(self.python) or not os.access(self.python, os.X_OK):
            raise Stop("The Python setup was given isn't on this Mac. Nothing was set up.")
        mac = platform.mac_ver()[0] if sys.platform == "darwin" else ""
        try:
            parts = tuple(int(x) for x in mac.split(".")[:2])
        except ValueError:
            parts = ()
        if len(parts) < 1 or (parts + (0,))[:2] < MAC_MOST_OLD:
            raise Stop(NOT_A_MAC)
        found = cl.find(self.env)
        text, ver = cl.version(found) if found else ("", None)
        if not found or ver is None:
            raise Stop(NO_CLAUDE)
        if ver < cfg.TESTED_CLAUDE:
            raise Stop(OLD_CLAUDE)
        self.claude, self.version = found, text
        self.checks["claude"] = (True, "Claude is on this Mac, version %s." % text)
        applog.note("install", "macOS %s, Claude Code %s" % (mac, text))

    def release_plugins(self):
        """[(name, the folder, its list entry)] for each plugin the release lists, checked before anything is made, so
        a broken release folder never leaves a half-made folder behind."""
        market = files.read_json(os.path.join(self.release, ".claude-plugin", "marketplace.json"), {})
        listed = market.get("plugins") if isinstance(market, dict) else None
        if not isinstance(listed, list) or not listed:
            raise Stop(BROKEN_RELEASE)
        base = os.path.realpath(self.release)
        out = []
        for p in listed:
            name, source = (p.get("name"), p.get("source")) if isinstance(p, dict) else (None, None)
            src = os.path.realpath(os.path.join(self.release, source or ""))
            if (not isinstance(name, str) or not NAME.fullmatch(name) or not src.startswith(base + os.sep)
                    or not os.path.isfile(os.path.join(src, ".claude-plugin", "plugin.json"))):
                raise Stop(BROKEN_RELEASE)
            out.append((name, src, p))
        if not any(n == registry.MAIN for n, _, _ in out):
            raise Stop(BROKEN_RELEASE)
        return out

    def read_existing(self):
        """config.json of a folder already set up, or None for a new one."""
        if synced(self.root):
            raise Stop(SYNCED_SAID)
        path = cfg.path(self.root)
        if not os.path.exists(path):
            return None
        raw = files.read_json(path)
        if not isinstance(raw, dict) or raw.get("contract") != cfg.CONTRACT:
            raise Stop("Hydra-OS's settings in %s can't be read, so nothing was changed." % tilde(self.root))
        self.updating = builds.updates(self.root, PLUGIN)
        return raw

    def resume_config(self):
        """A folder already set up: its config.json, with the shop's address when it names none, and the Python
        hydra-setup just brought, kept here by python_step, in place of the one it ran on."""
        self.raw = self.existing
        moved = bool(self.python_from) and self.raw.get("python") != self.python
        if moved:
            self.raw = dict(self.raw, python=self.python)
        if self.shop_setting() or moved:
            cfg.write(self.root, self.raw)
        self.config = cfg.load(self.root)
        if moved:
            self.tools_step()

    def python_step(self):
        """Its own Python, from hydra-setup's checked download, kept in <root>/hydra/python/<its name>: copied whole,
        its links kept, so setup, the helpers and every hook run on the copy there, never the Mac's own python3. A
        copy of that name already there is taken away first, so a half-made one never stays."""
        if not self.python_from:
            return
        if not os.path.isfile(os.path.join(self.python_from, "bin", "python3")):
            raise Stop("Hydra-OS's Python isn't where setup put it. Nothing was set up.")
        dest = os.path.join(self.root, "hydra", "python", os.path.basename(self.python_from))
        try:
            files.folder(os.path.dirname(dest))
            if os.path.lexists(dest):
                shutil.rmtree(dest)
            shutil.copytree(self.python_from, dest, symlinks=True)
        except OSError:
            raise Stop("Hydra-OS couldn't keep its Python in %s." % tilde(self.root))
        self.python = os.path.join(dest, "bin", "python3")

    def python_tidy(self):
        """Once setup is done on its own Python, any other one an earlier setup kept in <root>/hydra/python/ goes."""
        kept = os.path.join(self.root, "hydra", "python")
        mine = os.path.dirname(os.path.dirname(self.python))
        if os.path.dirname(mine) != kept or not os.path.isdir(kept):
            return
        for name in os.listdir(kept):
            if os.path.join(kept, name) != mine:
                shutil.rmtree(os.path.join(kept, name), ignore_errors=True)

    def resume_step(self):
        """A folder already set up, picked up where it was left. config.json, yours/, every page's folder, the store and
        the installed pages stay as they are; setup goes on to what's left. One an older build set up gets its store
        again from this release, and its pages are installed again."""
        if self.updating:
            self.plugins = self.release_plugins()
            self.tools_step()
            self.store_step()
        reg = registry.read(self.root)
        main = registry.app(self.root, registry.MAIN)
        if not main or not main.get("root") or not os.path.isdir(main["root"]):
            reg = registry.build(self.config, env=self.env)  # the main app's own entry, from Claude's own list
            main = registry.app(self.root, registry.MAIN)
        if not main:
            raise Stop("Hydra-OS's own pages aren't installed in %s." % tilde(self.root))
        self.main_root = main["root"]
        self.titles = [a.get("title") or a["id"] for a in reg.get("apps", [])]
        self.checks["plugins"] = (True, "%s %s installed." % (_and(self.titles), "is" if len(self.titles) == 1 else "are"))
        self.allow_step()

    def allow_step(self):
        """The folder's own rules as this release has them (ALLOW), each one missing added, with every other rule and
        key of its .claude/settings.json kept as it is."""
        path = os.path.join(self.root, ".claude", "settings.json")
        doc = files.read_json(path, None)
        doc = doc if isinstance(doc, dict) else {}
        perms = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
        allow = [r for r in perms.get("allow") or [] if isinstance(r, str)]
        missing = [r for r in ALLOW if r not in allow]
        if missing:
            files.write_json(path, dict(doc, permissions=dict(perms, allow=allow + missing)))

    def shop_setting(self):
        """config.json's shop.catalog, the catalog's address, when it names none, so a page can be added on this Mac.
        Never in a test: a run with any HYDRA_TEST_ switch names no shop, so its tick reads HYDRA_TEST_SHOP_CATALOG or
        nothing, and no test reaches the network."""
        shop_cfg = self.raw.get("shop") if isinstance(self.raw.get("shop"), dict) else {}
        if any(k.startswith("HYDRA_TEST_") for k in self.env):
            return False
        named = shop_cfg.get("catalog")
        if named:
            if named == SHOP_CATALOG and not shop_cfg.get("mirror"):  # the mirror beside it
                self.raw["shop"] = dict(shop_cfg, mirror=SHOP_MIRROR)
                return True
            return False
        self.raw["shop"] = dict(shop_cfg, catalog=SHOP_CATALOG, mirror=SHOP_MIRROR)
        return True

    def jobs_were_on(self):
        return bool(self.existing is not None and (self.raw.get("tick") or {}).get("on"))

    def root_step(self):
        root = self.root
        self.plugins = self.release_plugins()
        for sub in ("", "hydra", "hydra/panel", "hydra/locks", "hydra/bin", "hydra/store", "hydra/home", "hydra/dreams",
                    "yours", ".claude"):
            files.folder(os.path.join(root, sub))
        port = self.port or (free_port(0) if cfg.test_switches(self.env) else free_port(cfg.FIRST_PORT))
        self.raw = cfg.new(root, self.python, self.claude, self.version, port=port)
        self.shop_setting()
        cfg.write(root, self.raw)
        self.config = cfg.load(root)
        self.tools_step()

    def tools_step(self):
        """Hydra-OS's own small tools and TMPDIR (hydralib/tools.py), then setup's own calls take them too."""
        tools.write(self.root, self.config["python"])
        self.env.update(cfg.session_env(self.config, self.env))

    def store_step(self):
        store = os.path.join(self.root, "hydra", "store")
        entries = []
        for name, src, p in self.plugins:
            rel = os.path.relpath(src, os.path.realpath(self.release))
            _copy(src, os.path.join(store, rel))
            entries.append({"name": name, "source": "./" + rel, "version": str(p.get("version") or ""),
                            **({"description": p["description"]} if isinstance(p.get("description"), str) else {})})
        names = {e["name"] for e in entries}  # pages added from the shop stay, whatever the release holds
        entries += [e for e in shop.bought_entries(self.root) if e["name"] not in names]
        files.write_json(os.path.join(store, ".claude-plugin", "marketplace.json"),
                         {"name": cfg.STORE, "owner": {"name": "Hydra-OS"},
                          "description": "Hydra-OS's own store, copied from its release, with the pages added to it.",
                          "plugins": entries})
        # at local scope, from <root>: declared and enabled in <root>/.claude/settings.local.json only, so Hydra-OS's
        # hooks and skills are on in chats in <root> and off in every other conversation the person has
        code, _ = cl.run(self.claude, ["plugin", "marketplace", "add", store, "--scope", "local"], env=self.env,
                         timeout=120, cwd=self.root)
        if code != 0:
            raise Stop("Claude couldn't add Hydra-OS's store.")
        for e in entries:
            code, _ = cl.run(self.claude, ["plugin", "install", "%s@%s" % (e["name"], cfg.STORE), "--scope", "local"],
                             env=self.env, timeout=300, cwd=self.root)
            if code != 0:
                raise Stop("Claude couldn't install %s from Hydra-OS's store." % e["name"])
        reg = registry.build(self.config, env=self.env)
        self.titles = [a.get("title") or a["id"] for a in reg.get("apps", [])]
        main = registry.app(self.root, registry.MAIN)
        if not main:
            raise Stop("Hydra-OS's own pages didn't install.")
        self.main_root = main["root"]
        for a in reg.get("apps", []):
            if a.get("kind") != "main":
                files.folder(a["record"])
                pages.app(self.config, a["id"], force=True)
        pages.home(self.config)
        verb = "is" if len(self.titles) == 1 else "are"
        self.checks["plugins"] = (True, "%s %s installed." % (_and(self.titles), verb))

    def command_step(self):
        """<root>/hydra/bin/hydra: a /bin/sh launcher with every path quoted, so a home with a space or an accented
        letter in its path is fine (a `#!` line can't hold a space), and the script it runs beside it."""
        bin_path = os.path.join(self.root, "hydra", "bin", "hydra")
        script = os.path.join(self.root, "hydra", "bin", ".hydra.py")
        files.write_text(script, COMMAND % {"root": json.dumps(self.root),
                                            "fallback": json.dumps(os.path.join(self.root, "hydra", "store",
                                                                                os.path.relpath(PLUGIN, self.release)))})
        files.write_text(bin_path, '#!/bin/sh\nexec %s -B -s %s "$@"\n' % (shlex.quote(self.config["python"]),
                                                                          shlex.quote(script)))
        os.chmod(bin_path, 0o700)
        files.write_json(os.path.join(self.root, ".claude", "settings.json"), {"permissions": {"allow": list(ALLOW)}})

    def catalog_step(self):
        """The Shop's pages at once: the signed catalog read before Home's server starts, so Home is never drawn
        without it, rather than first at a later tick. A read that fails changes nothing else; it never raises."""
        try:
            applog.note("install", "the catalog: %s" % shop.read_catalog(self.config, env=self.env))
        except Exception as e:
            applog.note("install", "the catalog couldn't be read: %r" % (e,))

    def no_login_jobs(self):
        """With the helpers off, nothing of Hydra-OS starts at login: a job of this build's own labels, Home's server's
        or the tick's, that an older install left loaded or written is booted out and its plist removed
        (jobs.retire_own), before Home's server starts, so an older server gives up the port first."""
        gone = jobs.retire_own(self.config, self.home)
        if gone:
            applog.note("install", "with the helpers off, an older install's jobs taken away: %s" % ", ".join(sorted(gone)))
        if gone.get(self.config["server"]["label"]) == "running":
            self.wait_gone()

    def server_step(self):
        if not (self.jobs_on or self.jobs_were_on()):
            self.no_login_jobs()
        if self.existing is not None and not self.updating and self.get("/api/panel")[0] == 200:
            self.checks["server"] = (True, "Home answers on this Mac.")
            return
        if self.jobs_on or self.jobs_were_on():
            if self.updating:  # it ran from an older release: started again from this one
                jobs.unload(self.config["server"]["label"])
                self.wait_gone()
            paths = jobs.write(self.config, self.main_root, jobs.agents_folder(self.home), [self.config["server"]["label"]])
            self.load(paths)
        else:
            self.server = subprocess.Popen(
                [self.config["python"], "-B", "-s", os.path.join(self.main_root, "scripts", "server.py"), "--root", self.root],
                cwd=self.root, env=dict(cfg.run_env(self.config), **cfg.test_switches(self.env)),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
            files.write_json(os.path.join(self.root, "hydra", "server.pid"),  # so the last chat's end can stop it
                             {"pid": self.server.pid, "at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()})
        self.wait_server()
        self.checks["server"] = (True, "Home answers on this Mac.")

    def wait_gone(self):
        end = time.monotonic() + GONE_WAIT
        while time.monotonic() < end and self.get("/api/panel")[0] != 0:
            time.sleep(0.2)

    def wait_server(self):
        end = time.monotonic() + SERVER_WAIT
        while time.monotonic() < end:
            if self.get("/api/panel")[0] == 200:
                return
            time.sleep(0.2)
        raise Stop("Home's server didn't start.")

    def jobs_step(self):
        gone = jobs.retire_others(self.config, self.home)  # an older build's job this one doesn't use
        if gone:
            applog.note("install", "an older build's jobs taken away: %s" % ", ".join(gone))
        if self.jobs_were_on():
            self.jobs_on = True
            ok = True
            if self.updating:  # the tick ran from an older release: started again from this one
                label = self.config["tick"]["label"]
                jobs.unload(label)
                ok = self.load(jobs.write(self.config, self.main_root, jobs.agents_folder(self.home), [label])) == [label]
            self.checks["jobs"] = (ok, JOBS_ON if ok else "Hydra-OS's helpers didn't start.")
            return
        if not self.jobs_on:
            self.raw["helpers"] = "off"  # the person's no: Home's server and the day's reads start with each chat
            cfg.write(self.root, self.raw)
            self.config = cfg.load(self.root)
            self.checks["jobs"] = (True, JOBS_OFF)
            return
        labels = [self.config["tick"]["label"]]
        self.raw["tick"]["on"] = True  # first, so the tick finds itself on as it starts
        self.raw["helpers"] = "on"
        cfg.write(self.root, self.raw)
        self.config = cfg.load(self.root)
        loaded = self.load(jobs.write(self.config, self.main_root, jobs.agents_folder(self.home), labels))
        ok = sorted(loaded) == sorted(labels)
        self.checks["jobs"] = (ok, JOBS_ON if ok else "Hydra-OS's helpers didn't start.")

    def launch_step(self):
        """<root>/.claude/launch.json: Home, by its origin alone, for the Claude app's Browser pane, which opens a server
        that's already running when an entry has a url and no command. Claude opens it there on the person's first
        message, in one tab."""
        port = self.config["home"]["port"]
        files.write_json(os.path.join(self.root, ".claude", "launch.json"),
                         {"version": "0.0.1",
                          "configurations": [{"name": "Hydra-OS", "url": "http://localhost:%d" % port, "port": port}]})

    # ---- Home's server, asked ---------------------------------------------------------------------------------------

    def get(self, path):
        return self.request("GET", path)

    def request(self, method, path, body=None):
        port = self.config["home"]["port"]
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=40)
            own = "http://127.0.0.1:%d" % port
            headers = {"Host": "127.0.0.1:%d" % port}
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers.update({"Content-Type": "application/json", "Origin": own, "Sec-Fetch-Site": "same-origin"})
            c.request(method, path, body=data, headers=headers)
            r = c.getresponse()
            out = r.read()
            c.close()
            return r.status, out
        except (OSError, http.client.HTTPException):
            return 0, b""

    # ---- the self-test ----------------------------------------------------------------------------------------------

    def self_test(self):
        self.checks["save"] = self.save_check()
        self.checks["tick"] = self.tick_check()
        order = ("claude", "server", "save", "plugins", "jobs", "tick", "list")
        checks = [{"name": n, "ok": bool(self.checks.get(n, (False, ""))[0]), "said": self.checks.get(n, (False, ""))[1]}
                  for n in order]
        files.write_json(os.path.join(self.root, "hydra", "setup.json"),
                         {"contract": "setup/v1", "at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
                          "checks": checks, **({"build": self.build} if self.build else {})})

    def save_check(self):
        """A made-up answer through Home's server, on a throwaway question in the main app's own folder, taken back
        with Undo; then the question and its answers are removed."""
        selftest = os.path.join(self.root, "hydra", "selftest")
        try:
            files.write_json(os.path.join(selftest, "question.json"), SAVE_QUESTION)
            fields = {"question": "q-setup", "pick": "ok"}
            code, out = self.request("POST", "/api/act/hydra/answer", {"fields": fields})
            saved = code == 200 and json.loads(out or b"{}").get("ok") is True
            code, out = self.request("POST", "/api/act/hydra/unanswer", {"fields": fields})
            undone = code == 200 and json.loads(out or b"{}").get("ok") is True
            lines = files.read_lines(os.path.join(selftest, "answers.jsonl"))
            ok = saved and undone and [x.get("undone", False) for x in lines] == [False, True]
        except (OSError, ValueError):
            ok = False
        finally:
            shutil.rmtree(selftest, ignore_errors=True)
        return (True, "A save goes through and comes back.") if ok else (False, "A save didn't go through Home's server.")

    def tick_check(self):
        """Whether a tick writes health.json again. It's told by the file, not its words: a tick within the same second
        as the one before it, as on a quick 'try again' just after the tick's job started, writes the very same words."""
        import tick  # the tick script beside this one

        def written():
            try:
                st = os.stat(health.path(self.root))
            except OSError:
                return None
            return st.st_ino, st.st_mtime_ns  # each write is a new file renamed into place

        before = written()
        try:
            tick.Tick(self.config, env=self.env, how="terminal", start_runs=False)()
        except Exception:
            return False, "Hydra-OS couldn't check what's due on this Mac."
        ok = bool(health.read(self.root)) and written() not in (None, before)
        return (True, "Hydra-OS checked what's due on this Mac.") if ok else (False, "Hydra-OS couldn't check what's due on this Mac.")

    # ---- the folder, the release and leaving the first list ---------------------------------------------------------

    def ours(self):
        """Whether a folder that isn't set up is free to set up: missing, or holding only what the plugin's own install
        at local scope made there (.claude/settings.local.json, Claude Code's own) and what an earlier setup that
        stopped left. A folder of the person's own of that name is never mixed with."""
        for sub, allowed in (("", {"hydra", ".claude", ".DS_Store"}), ("hydra", {".setup", "python", ".DS_Store"}),
                             (".claude", {LOCAL_SETTINGS, ".DS_Store"})):
            try:
                if not set(os.listdir(os.path.join(self.root, sub))) <= allowed:
                    return False
            except FileNotFoundError:
                continue
            except OSError:
                return False
        return True

    def assemble(self):
        """The release this plugin carries: the plugin itself and the free pages in its own release/ folder
        (shell/mac-app/make_list.py), laid out as a release folder is, in <root>/hydra/.setup/, made afresh and taken
        away when setup ends. A plugin with no release/ folder sits in one already, as the store's own copy does, and
        that's the release."""
        inner = os.path.join(PLUGIN, "release")
        market = files.read_json(os.path.join(inner, ".claude-plugin", "marketplace.json"), None)
        if not isinstance(market, dict) or not isinstance(market.get("plugins"), list):
            return RELEASE
        main = files.read_json(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), {})
        ver = str(main.get("version") or "") if isinstance(main, dict) else ""
        if not NAME.fullmatch(main.get("name") or "") or not ver:
            raise Stop(BROKEN_RELEASE)
        out = os.path.join(self.root, "hydra", ".setup", "release")
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)
        files.folder(out)
        mine = os.path.join(out, main["name"], ver)
        shutil.copytree(PLUGIN, mine, symlinks=False, ignore=lambda d, names: ["release"] if d == PLUGIN else [])
        for name in os.listdir(inner):
            if name != ".claude-plugin" and os.path.isdir(os.path.join(inner, name)):
                shutil.copytree(os.path.join(inner, name), os.path.join(out, name), symlinks=False)
        shutil.copytree(os.path.join(inner, ".claude-plugin"), os.path.join(out, ".claude-plugin"))
        return out

    def undo(self):
        """A fresh setup that stopped, taken back whole: the jobs it started stopped and their plists removed, the
        pages it installed at local scope uninstalled and the store's list removed, and the folder it made taken away
        (ours: it held nothing of the person's)."""
        for label in list(self.loaded):
            jobs.unload(label)
            plist = os.path.join(jobs.agents_folder(self.home), "%s.plist" % label)
            if os.path.exists(plist):
                os.unlink(plist)
        if self.server and self.server.poll() is None:
            self.server.terminate()
        if self.claude and os.path.isdir(self.root):
            market = files.read_json(os.path.join(self.root, "hydra", "store", ".claude-plugin", "marketplace.json"), {})
            for e in (market.get("plugins") or []) if isinstance(market, dict) else []:
                if isinstance(e, dict) and isinstance(e.get("name"), str):
                    cl.run(self.claude, ["plugin", "uninstall", "%s@%s" % (e["name"], cfg.STORE), "--scope", "local"],
                           env=self.env, timeout=120, cwd=self.root)
            cl.run(self.claude, ["plugin", "marketplace", "remove", cfg.STORE], env=self.env, timeout=120, cwd=self.root)
        if self.ours() or os.path.exists(cfg.path(self.root)):
            self.take_back()

    def take_back(self):
        """The folder setup made, taken away, but for Claude Code's own .claude/settings.local.json from the plugin's
        install at local scope, which stays, so 'try again' finds the plugin where it was."""
        kept = os.path.join(self.root, ".claude", LOCAL_SETTINGS)
        if not os.path.isfile(kept) or os.path.islink(kept):
            shutil.rmtree(self.root, ignore_errors=True)
            return
        for name in os.listdir(self.root):
            path = os.path.join(self.root, name)
            if name == ".claude":
                for inner in os.listdir(path):
                    there = os.path.join(path, inner)
                    if inner == LOCAL_SETTINGS:
                        continue
                    if os.path.isdir(there) and not os.path.islink(there):
                        shutil.rmtree(there, ignore_errors=True)
                    else:
                        os.unlink(there)
            elif os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.unlink(path)

    def leave_public_list(self):
        """The first list left: the main plugin as installed from it uninstalled at local scope in <root>, and the list
        removed from Claude Code. Hydra-OS runs from its own store at local scope in <root> from here on, so Claude
        Code's own plugin update can never pull a change Hydra-OS's key didn't sign, and every later update comes only
        through hydra update. A Mac that never had the list has nothing to leave."""
        code, out = cl.run(self.claude, ["plugin", "marketplace", "list", "--json"], env=self.env, timeout=60,
                           cwd=self.root)
        try:
            names = [m.get("name") for m in json.loads(out or "[]") if isinstance(m, dict)]
        except ValueError:
            names = None
        if code == 0 and names is not None and PUBLIC_LIST not in names:
            self.checks["list"] = (True, "Hydra-OS updates only through its own signed list.")
            return
        cl.run(self.claude, ["plugin", "uninstall", "%s@%s" % (registry.MAIN, PUBLIC_LIST), "--scope", "local"],
               env=self.env, timeout=120, cwd=self.root)
        code, _ = cl.run(self.claude, ["plugin", "marketplace", "remove", PUBLIC_LIST], env=self.env, timeout=120,
                         cwd=self.root)
        self.checks["list"] = ((True, "Hydra-OS updates only through its own signed list.") if code == 0 else
                               (False, "Hydra-OS's first list is still in Claude, so updates could come from it."))


def _and(names):
    names = [str(n) for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else "Nothing"


def _copy(src, dest):
    """Copy a plugin folder into the store: folders 0700, files 0600, with symlinks, caches and test folders (the
    plugin's own tests/ and the kit's) left out."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    for here, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(here, d)) and d not in ("__pycache__", "tests")]
        rel = os.path.relpath(here, src)
        out = os.path.join(dest, rel) if rel != "." else dest
        files.folder(out)
        for n in names:
            path = os.path.join(here, n)
            if os.path.islink(path) or n.endswith(".pyc") or n == ".DS_Store":
                continue
            target = os.path.join(out, n)
            if os.path.lexists(target):  # a new file of its own each time, so its mode is set only on what it made
                os.unlink(target)
            shutil.copyfile(path, target)
            os.chmod(target, 0o600)


COMMAND = '''"""Hydra-OS's command: runs the main plugin's scripts/hydra.py from its installed release. Written by setup;
nothing else is kept here."""
import json
import os
import sys

ROOT = %(root)s
sys.dont_write_bytecode = True
try:
    with open(os.path.join(ROOT, "hydra", "registry.json"), encoding="utf-8") as f:
        main = next(a for a in json.load(f)["apps"] if a.get("kind") == "main")
    script = os.path.join(main["root"], "scripts", "hydra.py")
    if not os.path.isfile(script):
        raise ValueError
except (OSError, ValueError, KeyError, StopIteration, TypeError):
    script = os.path.join(%(fallback)s, "scripts", "hydra.py")
os.environ["HYDRA_ROOT"] = ROOT
os.execv(sys.executable, [sys.executable, "-B", "-s", script] + sys.argv[1:])
'''


def main(argv=None):
    ap = argparse.ArgumentParser(description="Set up Hydra-OS, in the person's own chat, after their yes")
    ap.add_argument("--root", help="where Hydra-OS keeps everything (default ~/Hydra-OS)")
    ap.add_argument("--jobs", action="store_true", help="start the helpers at login, after the person's yes")
    ap.add_argument("--port", type=int, help="Home's port (default: the first free one from 8792 up)")
    ap.add_argument("--python", help="the Python Hydra-OS runs on (default: the one running setup)")
    ap.add_argument("--python-from", help="its own Python, as hydra-setup checked and unpacked it, to keep in <root>")
    args = ap.parse_args(argv)
    load = jobs.load
    if os.environ.get("HYDRA_TEST_LAUNCHCTL"):  # tests only: launchctl's stand-in
        load = jobs.test_load(os.environ["HYDRA_TEST_LAUNCHCTL"], os.path.expanduser("~"))
    return Setup(args.root, args.jobs, args.port, python=args.python, python_from=args.python_from, load=load).run()


if __name__ == "__main__":
    sys.exit(main())
