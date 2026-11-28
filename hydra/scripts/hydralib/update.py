"""hydra update for Hydra-OS itself: the signed catalog's latest core, put in place in order, and everything put back
byte for byte when any
step after the backup fails.

  1. busy: the tick's run lock (runs.Lock) is held for the whole update, and a review under its fence waits: BUSY.
  2. the catalog, read fresh (shop.read_catalog), and its core only when the shop's key signed it.
  3. the zip, fetched (https, or a test catalog's own folder), at most ZIP_MOST, checked by the catalog's sha256, and
     staged in <root>/hydra/.update/ with plain files and folders only; its plugin.json is hydra's, at that version.
  4. the backup (backup.take), with the hydra command and setup.json beside what every backup keeps.
  5. the new core's scripts/migrate.py --root.
  6. the store: the new core, without its release/, as store/hydra/<version>/, and the store's list naming it.
  7. Claude Code's copy, through the Claude Code that runs the chat: plugin marketplace update, then plugin update
     hydra@hydra-os at local scope. The registry built again names the new core, and the hydra command runs it.
  8. Hydra-OS's own Python, for a home that still runs on the Mac's own python3, as an older Hydra-OS set it up: the
     one the new core's scripts/python.pins names for this chip, fetched, checked by its sha256 before the Mac's own
     tar unpacks it, started once, and kept in <root>/hydra/python/<its name>/; then config.json, hydra/bin/python3 and
     the hydra command name it. A home already on its own Python keeps it.
  9. Each free page the new release carries that this home lacks, as Research came free in 1.2.0, added as setup adds
     it: copied into the store, listed, installed at local scope through the same Claude Code, its folder made and its
     page drawn. Best effort and asking nothing: a page already here, bought or free, is left as it is, nothing is
     removed, and a page that doesn't go in is left out without undoing the update.
 10. Home's server and the tick started again from the new core, and Home answering again.
Any failure from 4 on puts everything back: the backup restored, the new store folder taken away, Claude Code's copy
back at the old version (plugin update again, else uninstall and install), the Python it kept taken away, the jobs
from the old core again: FAILED.
One version is kept back in the store, and the last two backups.

HYDRA_TEST_UPDATE_FAIL=<step>, for tests only, stops the update at the end of that step (backup, migrate, store,
claude, registry, python, jobs or server), as Checks plants a failure at each one.

  core(config, env=None, now=None, load=None)    the lines hydra update says for Hydra-OS itself
"""
import datetime
import http.client
import json
import os
import platform
import shlex
import shutil
import subprocess
import time
import urllib.parse
import zipfile

from . import applog, backup, files, jobs, registry, review_fence, runs, shop, space, tools
from . import claude as cl
from . import config as cfg
from . import release as builds

BUSY = "Hydra-OS is busy for a moment. Say 'update Hydra-OS' again in a minute."
FAILED = "The update didn't finish, so Hydra-OS is as it was."
UP_TO_DATE = "Hydra-OS %s is up to date."
DONE = "Hydra-OS %s is in place."
NO_SHOP = "Hydra-OS has no shop to check yet, so nothing changed."
OFFLINE = "Hydra-OS couldn't reach its shop. Check the Mac is online, then try again."
NOT_CHECKED = "The shop's list didn't check out, so nothing changed."
FETCH = "Hydra-OS couldn't download the update. Check the Mac is online, then try again."
NOT_SIGNED = "The download didn't match what the shop signed, so it wasn't used."
ODD = "The download holds something Hydra-OS never has, so it wasn't used."
NOT_HYDRA = "The download isn't Hydra-OS %s, so it wasn't used."
NO_BACKUP = "Hydra-OS couldn't back up your pages first, so nothing changed."
ZIP_MOST = 64 * 1024 * 1024
UNZIPPED_MOST = 256 * 1024 * 1024
STAGE = (".update",)  # <root>/hydra/.update/
KEEP = 2  # versions of the core kept in the store: the one in use and the one before
SERVER_WAIT = 30.0
BUSY_WAIT = 30  # seconds hydra update waits for a run or a review to end before it says BUSY;
# HYDRA_TEST_BUSY_WAIT, for tests only, sets another
STEPS = ("backup", "migrate", "store", "claude", "registry", "python", "jobs", "server")
EXTRA = (os.path.join("hydra", "bin", ".hydra.py"), os.path.join("hydra", "setup.json"),
         os.path.join("hydra", "bin", "hydra"), os.path.join("hydra", "bin", "python3"))
PYTHON_MOST = 64 * 1024 * 1024  # bytes of Hydra-OS's own Python's archive


def _wait(env):
    try:
        return max(0, int(env.get("HYDRA_TEST_BUSY_WAIT", BUSY_WAIT)))
    except ValueError:
        return BUSY_WAIT


def quiet(root, env, refused, busy=None):
    """The tick's run lock, held: a run that's out, or a review under its fence, is waited for briefly, then
    refused(BUSY) is raised. Returns the held lock; its __exit__ lets it go."""
    busy = busy or BUSY
    end = time.monotonic() + _wait(env)
    while review_fence.live(root):
        if time.monotonic() >= end:
            raise refused(busy)
        time.sleep(2)
    lock = runs.Lock(root, wait=max(0, int(end - time.monotonic())))
    try:
        lock.__enter__()
    except runs.Held:
        raise refused(busy)
    return lock


class Stop(Exception):
    """One plain line on why the update stopped."""


class _Planted(Exception):
    """A failure a test planted (HYDRA_TEST_UPDATE_FAIL)."""


def _now(now=None):
    return (now or datetime.datetime.now().astimezone()).replace(microsecond=0)


def _unzip(path, dest):
    """The zip's files into dest: plain files and folders only, nothing outside dest and no link, at most
    UNZIPPED_MOST in all; folders 0700, files 0600, or 0700 for one that was executable."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise Stop(ODD)
    with z:
        infos = z.infolist()
        if sum(i.file_size for i in infos) > UNZIPPED_MOST:
            raise Stop(ODD)
        for i in infos:
            name = os.path.normpath(i.filename)
            mode = (i.external_attr >> 16) & 0o170000
            if os.path.isabs(name) or name.split(os.sep)[0] == ".." or ".." in name.split(os.sep) or \
                    mode not in (0, 0o100000, 0o040000):
                raise Stop(ODD)
            target = os.path.join(dest, name)
            if i.is_dir():
                files.folder(target)
                continue
            files.folder(os.path.dirname(target))
            with z.open(i) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(target, 0o700 if (i.external_attr >> 16) & 0o100 else 0o600)


class Update:
    def __init__(self, config, env=None, now=None, load=None):
        self.config, self.root = config, config["root"]
        self.env = os.environ if env is None else env
        self.now = _now(now)
        self.load = load or (jobs.test_load(self.env["HYDRA_TEST_LAUNCHCTL"], os.path.expanduser("~"))
                             if self.env.get("HYDRA_TEST_LAUNCHCTL") else jobs.load)
        self.stage = os.path.join(self.root, "hydra", *STAGE)
        self.chat = cl.chat_claude(config, self.env)
        self.config = dict(config, claude=self.chat)  # for registry.build and shop._install, the same Claude Code
        self.made = None  # the backup, once taken
        self.target = None  # the store folder this update made
        self.old = None  # the core in use, {"version", "root"}
        self.added = []  # the free pages this update added: [name], taken out again if a later step fails
        self.python_made = None  # the Python this update kept in <root>/hydra/python/, for a home it moved onto it
        self.python_was = None  # the Python config.json named before

    def planted(self, step):
        if self.env.get("HYDRA_TEST_UPDATE_FAIL") == step:
            raise _Planted(step)

    def claude(self, args, timeout=300):
        """Claude Code's own commands, through the Claude Code running the person's chat, found by its own process as
        hydra-setup finds it: a buyer has no claude command."""
        return cl.run(self.chat, args, self.config.get("claude_config", ""), self.env, timeout=timeout, cwd=self.root)

    # ---- before anything changes ----------------------------------------------------------------------------------

    def latest(self):
        got = shop.read_catalog(self.config, now=self.now, force=True, env=self.env)
        if got == "none":
            raise Stop(NO_SHOP)
        if got == "offline":
            raise Stop(OFFLINE)
        if got == "refused":
            raise Stop(NOT_CHECKED)
        return shop.catalog(self.root, self.env).get("core")  # only a signed catalog carries one

    def fetch(self, want):
        shutil.rmtree(self.stage, ignore_errors=True)
        files.folder(self.stage)
        zipped = os.path.join(self.stage, "hydra-%s.zip" % want["version"])
        try:
            shop._fetch(want["zip"], ZIP_MOST, zipped)
        except (OSError, ValueError, shop.Refused):
            raise Stop(FETCH)
        if shop._sha256(zipped) != want["sha256"]:
            raise Stop(NOT_SIGNED)
        try:  # room for it unpacked, in the store and backed up
            space.need(self.root, 3 * os.path.getsize(zipped) + space.CORE_MORE, self.env)
        except space.Short as e:
            raise Stop(str(e))
        staged = os.path.join(self.stage, "hydra")
        files.folder(staged)
        _unzip(zipped, staged)
        plugin = shop._plugin(staged)
        if plugin.get("name") != registry.MAIN or plugin.get("version") != want["version"] or \
                not os.path.isfile(os.path.join(staged, "scripts", "hydra.py")):
            raise Stop(NOT_HYDRA % want["version"])
        return staged

    # ---- the steps that change things -----------------------------------------------------------------------------

    def migrate(self, staged):
        script = os.path.join(staged, "scripts", "migrate.py")
        if os.path.isfile(script):
            r = subprocess.run([self.config["python"], "-B", "-s", script, "--root", self.root], cwd=staged,
                               env=cfg.run_env(self.config), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=300)
            said = r.stdout.decode("utf-8", "replace").strip().splitlines()
            applog.note("update", "migrate: %s" % (said[0] if said else "no line"))
            if r.returncode != 0:
                raise _Planted("migrate")
        self.planted("migrate")

    def store(self, staged, version):
        store = os.path.join(self.root, "hydra", "store")
        target = os.path.join(store, registry.MAIN, version)
        if os.path.lexists(target):
            shutil.rmtree(target)  # a part made by an update that stopped: the backup holds nothing of it
        shutil.copytree(staged, target, symlinks=True, ignore=lambda d, names: ["release"] if d == staged else [])
        self.target = target
        market = os.path.join(store, ".claude-plugin", "marketplace.json")
        doc = files.read_json(market, None)
        if not isinstance(doc, dict) or not isinstance(doc.get("plugins"), list):
            raise _Planted("store")
        doc = dict(doc, plugins=[e for e in doc["plugins"] if not (isinstance(e, dict) and e.get("name") == registry.MAIN)])
        doc["plugins"].insert(0, {"name": registry.MAIN, "source": "./%s/%s" % (registry.MAIN, version),
                                  "version": version})
        files.write_json(market, doc)
        self.planted("store")

    def claude_copy(self, version):
        self.claude(["plugin", "marketplace", "update", cfg.STORE], timeout=120)
        code, _ = self.claude(["plugin", "update", "%s@%s" % (registry.MAIN, cfg.STORE), "--scope", "local"])
        if code != 0:
            raise _Planted("claude")
        self.planted("claude")

    def registry_step(self, version):
        registry.build(self.config, env=self.env)
        main = registry.app(self.root, registry.MAIN) or {}
        if main.get("version") != version or not os.path.isdir(main.get("root") or ""):
            raise _Planted("registry")
        self.command(main["root"])
        self.planted("registry")
        return main

    def command(self, main_root):
        """The hydra command's script, written again with this core's folder as its fallback."""
        import install as setup_script  # scripts/install.py, beside hydra.py
        path = os.path.join(self.root, "hydra", "bin", ".hydra.py")
        if os.path.isfile(path):
            files.write_text(path, setup_script.COMMAND % {"root": json.dumps(self.root), "fallback": json.dumps(main_root)})

    def free_pages(self, staged):
        """Each free page the new release lists that the store's list lacks, added as setup adds it, best effort."""
        from . import pages
        release = os.path.join(staged, "release")
        listed = files.read_json(os.path.join(release, ".claude-plugin", "marketplace.json"), {})
        market_path = os.path.join(self.root, "hydra", "store", ".claude-plugin", "marketplace.json")
        market = files.read_json(market_path, {})
        have = {e.get("name") for e in (market.get("plugins") or []) if isinstance(e, dict)}
        for e in (listed.get("plugins") or []) if isinstance(listed, dict) else []:
            name = e.get("name") if isinstance(e, dict) else None
            if not isinstance(name, str) or name == registry.MAIN or name in have or not isinstance(e.get("source"), str):
                continue
            src = os.path.realpath(os.path.join(release, e["source"]))
            rel = os.path.relpath(src, os.path.realpath(release))
            target = os.path.join(self.root, "hydra", "store", rel)
            if rel.startswith("..") or not os.path.isfile(os.path.join(src, ".claude-plugin", "plugin.json")):
                continue
            try:
                if os.path.lexists(target):
                    shutil.rmtree(target)
                shutil.copytree(src, target, symlinks=True)
                market = files.read_json(market_path, {})
                market["plugins"] = list(market.get("plugins") or []) + [
                    {"name": name, "source": "./" + rel, "version": str(e.get("version") or ""),
                     **({"description": e["description"]} if isinstance(e.get("description"), str) else {})}]
                files.write_json(market_path, market)
                self.claude(["plugin", "marketplace", "update", cfg.STORE], timeout=120)
                code, _ = self.claude(["plugin", "install", "%s@%s" % (name, cfg.STORE), "--scope", "local"])
                if code != 0:
                    raise OSError("Claude Code didn't install %s" % name)
                self.added.append(name)
            except (OSError, ValueError) as err:
                applog.note("update", "%s left out: %s" % (name, err))
                self.take_out(name, rel)
        if self.added:
            registry.build(self.config, env=self.env)
            for name in self.added:
                entry = registry.app(self.root, name) or {}
                try:
                    files.folder(entry["record"])
                    pages.app(self.config, name, force=True)
                except (OSError, ValueError, KeyError) as err:
                    applog.note("update", "%s's first page: %s" % (name, err))
            applog.note("update", "free pages added: %s" % ", ".join(self.added))

    def take_out(self, name, rel=None):
        """A free page this update added, out again: the store's list, its copy and Claude Code's install."""
        self.claude(["plugin", "uninstall", "%s@%s" % (name, cfg.STORE), "--scope", "local"])
        market_path = os.path.join(self.root, "hydra", "store", ".claude-plugin", "marketplace.json")
        market = files.read_json(market_path, {})
        if isinstance(market, dict) and isinstance(market.get("plugins"), list):
            market["plugins"] = [p for p in market["plugins"] if not (isinstance(p, dict) and p.get("name") == name)]
            files.write_json(market_path, market)
        shutil.rmtree(os.path.join(self.root, "hydra", "store", rel or name), ignore_errors=True)

    def python_step(self, staged):
        """A home on the Mac's own python3 (an older Hydra-OS's), moved onto Hydra-OS's own, as setup gets it: the
        new core's scripts/python.pins line for this chip, "<chip> <sha256> <address>", its archive fetched from its
        https address (or a file:// one in a made-up release), checked by its sha256, unpacked with the Mac's own tar,
        started once, then kept in <root>/hydra/python/<its name>/, and config.json, hydra/bin/python3 and the hydra
        command pointed at it. The backup holds config.json and both tools, so a later failure puts them back."""
        python = self.config.get("python") or ""
        if os.path.dirname(os.path.realpath(python)) != "/usr/bin":
            return
        pin = None
        try:
            with open(os.path.join(staged, "scripts", "python.pins"), encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 3 and parts[0] == platform.machine():
                        pin = parts[1:]
                        break
        except OSError:
            pass
        if not pin:
            raise ValueError("no Python pinned for this Mac's chip")
        digest, address = pin
        parsed = urllib.parse.urlparse(address)
        name = os.path.basename(parsed.path)
        if parsed.scheme not in ("https", "file") or not name.endswith(".tar.gz") or name.startswith("."):
            raise ValueError("that isn't a Python address Hydra-OS takes")
        name = name[:-len(".tar.gz")]
        work = os.path.join(self.stage, "python")
        shutil.rmtree(work, ignore_errors=True)
        files.folder(work)
        archive = os.path.join(work, "python.tar.gz")
        shop._fetch(address if parsed.scheme == "https" else urllib.parse.unquote(parsed.path), PYTHON_MOST, archive)
        if shop._sha256(archive) != digest:
            raise ValueError("the Python's sha256 isn't the pinned one")
        unpacked = os.path.join(work, name)
        os.makedirs(unpacked)
        subprocess.run(["/usr/bin/tar", "-xzf", archive, "-C", unpacked, "--strip-components", "1"], check=True,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
        own = os.path.join(unpacked, "bin", "python3")
        subprocess.run([own, "-I", "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"], check=True,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
        kept = os.path.join(self.root, "hydra", "python")
        files.folder(kept)
        dest = os.path.join(kept, name)
        if os.path.lexists(dest):
            shutil.rmtree(dest)
        os.rename(unpacked, dest)
        self.python_made, self.python_was = dest, python
        python = os.path.join(dest, "bin", "python3")
        raw = files.read_json(cfg.path(self.root), {})
        cfg.write(self.root, dict(raw, python=python))
        self.config = dict(self.config, python=python)
        tools.write(self.root, python)
        command = os.path.join(self.root, "hydra", "bin", "hydra")
        if os.path.isfile(command):
            files.write_text(command, '#!/bin/sh\nexec %s -B -s %s "$@"\n' % (
                shlex.quote(python), shlex.quote(os.path.join(self.root, "hydra", "bin", ".hydra.py"))))
            os.chmod(command, 0o700)
        applog.note("update", "moved onto Hydra-OS's own Python, %s" % name)

    def jobs_step(self, main_root):
        """Home's server and, when it's on, the tick, started again from main_root: as launch agents, or as a process
        of its own when a chat started it, with the helpers off. With the helpers chosen off, a job of either label an
        older install left is booted out and its plist removed instead (jobs.retire_own), so nothing starts at login,
        and Home's server goes on as a process of its own, from main_root, for the chat that asked."""
        from . import helpers
        if helpers.chose_off(self.config):
            gone = jobs.retire_own(self.config)
            if gone:
                applog.note("update", "with the helpers off, an older install's jobs taken away: %s" % ", ".join(sorted(gone)))
            if gone.get(self.config["server"]["label"]) == "running":
                self.wait_gone()
            if helpers.plain_running(self.config):
                helpers.restart_plain(self.config, main_root)
            else:
                helpers.start_plain(self.config, main_root)
            return
        labels = [self.config["server"]["label"]] + ([self.config["tick"]["label"]] if self.config["tick"].get("on") else [])
        folder = jobs.agents_folder(os.path.expanduser("~"))
        labels = [lbl for lbl in labels if os.path.exists(os.path.join(folder, lbl + ".plist"))]
        for label in labels:
            jobs.unload(label)
        self.wait_gone()
        if labels:
            self.load(jobs.write(self.config, main_root, folder, labels))
        helpers.restart_plain(self.config, main_root)

    def get(self):
        try:
            c = http.client.HTTPConnection("127.0.0.1", self.config["home"]["port"], timeout=5)
            c.request("GET", "/api/panel")
            return c.getresponse().status
        except OSError:
            return 0

    def wait_gone(self):
        end = time.monotonic() + 15
        while time.monotonic() < end and self.get() != 0:
            time.sleep(0.2)

    def wait_server(self):
        end = time.monotonic() + SERVER_WAIT
        while time.monotonic() < end:
            if self.get() == 200:
                return
            time.sleep(0.2)
        raise _Planted("server")

    # ---- putting everything back ----------------------------------------------------------------------------------

    def restore(self):
        if self.made:
            try:
                backup.restore(self.root, self.made)
            except (OSError, backup.Failed) as e:
                applog.note("update", "the restore stopped: %s" % e)

    def back(self):
        """Everything as it was: the backup restored, the store folder this update made taken away, Claude Code's copy
        at the old version again, and the jobs from the old core; then the backup restored once more, so what Claude
        Code's own commands wrote back is byte for byte too. Each part is tried, whatever another did."""
        for name in self.added:  # the free pages it added, out again, before the backup puts the store's list back
            self.take_out(name)
        self.restore()
        if self.python_made:  # the Mac's own python3 again, as config.json names it once more
            self.config = dict(self.config, python=self.python_was)
            shutil.rmtree(self.python_made, ignore_errors=True)
        if self.target and self.old and os.path.basename(self.target) != self.old["version"]:
            shutil.rmtree(self.target, ignore_errors=True)
        self.claude(["plugin", "marketplace", "update", cfg.STORE], timeout=120)
        mine = "%s@%s" % (registry.MAIN, cfg.STORE)
        self.claude(["plugin", "update", mine, "--scope", "local"])
        now = {p["name"]: p["version"] for p in cl.plugins(self.chat, self.config.get("claude_config", ""),
                                                            cfg.STORE, cwd=self.root, env=self.env)}
        if self.old and registry.MAIN in now and now[registry.MAIN] != self.old["version"]:  # listed, and wrong
            self.claude(["plugin", "uninstall", mine, "--scope", "local"])
            self.claude(["plugin", "install", mine, "--scope", "local"])
        self.restore()  # the registry and Claude Code's settings in the folder, as they were, byte for byte
        main = registry.app(self.root, registry.MAIN) or {}
        if main.get("root"):
            try:
                self.jobs_step(main["root"])
                self.wait_server()
            except (_Planted, OSError) as e:
                applog.note("update", "Home didn't answer after the rollback: %s" % e)

    # ---- the whole update -----------------------------------------------------------------------------------------

    def run(self):
        lock = quiet(self.root, self.env, Stop)
        try:
            return self.locked()
        finally:
            lock.__exit__(None, None, None)
            shutil.rmtree(self.stage, ignore_errors=True)

    def locked(self):
        main = registry.app(self.root, registry.MAIN) or {}
        self.old = {"version": str(main.get("version") or ""), "root": main.get("root") or ""}
        want = self.latest()
        if not want or not want.get("zip") or not want.get("sha256") or \
                shop.vt(want["version"]) <= shop.vt(self.old["version"]):
            return [UP_TO_DATE % self.old["version"]]
        staged = self.fetch(want)
        try:
            self.made = backup.take(self.root, "an update to %s" % want["version"], self.now, extra=EXTRA)
            self.planted("backup")
        except backup.Failed:
            raise Stop(NO_BACKUP)
        except _Planted:
            self.back()
            raise Stop(FAILED)
        try:
            self.migrate(staged)
            self.store(staged, want["version"])
            self.claude_copy(want["version"])
            new = self.registry_step(want["version"])
            self.python_step(staged)
            self.planted("python")
            self.free_pages(staged)
            self.jobs_step(new["root"])
            self.planted("jobs")
            self.wait_server()
            self.planted("server")
        except (_Planted, OSError, ValueError, KeyError, subprocess.SubprocessError, shop.Refused) as e:
            applog.note("update", "stopped at %s; putting everything back" % e)
            self.back()
            raise Stop(FAILED)
        self.finish(new, want["version"])
        return [DONE % want["version"]]

    def finish(self, new, version):
        """One version kept back in the store, the last two backups, and setup.json's build as the new core's."""
        folder = os.path.join(self.root, "hydra", "store", registry.MAIN)
        keep = {version, self.old["version"]}
        for v in sorted((v for v in os.listdir(folder) if shop.vt(v)), key=shop.vt)[:-KEEP]:
            if v not in keep:
                shutil.rmtree(os.path.join(folder, v), ignore_errors=True)
        backup.prune(self.root)
        own = builds.own(new["root"])
        setup = os.path.join(self.root, "hydra", "setup.json")
        doc = files.read_json(setup, None)
        if own and isinstance(doc, dict):
            files.write_json(setup, dict(doc, build=own))


# ---- a bought page's update ---------------------------------------------------------------------------

PAGE_FAILED = "The update didn't finish, so %s is as it was."
PAGE_NO_BACKUP = "Hydra-OS couldn't back up your pages first, so %s wasn't updated."
PAGE_STEPS = ("backup", "migrate", "store")


class _Quiet:
    """The tick's run lock, held while a page is updated, and never under a review's fence: each waited for briefly,
    then BUSY."""

    def __init__(self, root, env):
        self.root, self.env, self.lock = root, env, None

    def __enter__(self):
        self.lock = quiet(self.root, self.env, shop.Refused)
        return self

    def __exit__(self, *exc):
        self.lock.__exit__(*exc)


def page(config, page_id, version, staged, title, env=None, now=None):
    """A bought page's update to the version staged: the backup first, as Hydra-OS's
    own update takes it; then the page's own scripts/migrate.py from its new release, with --record <its record>; then
    shop._install, the store, Claude Code's copy and the registry. Any failure puts everything back: the backup
    restored, the version folder this update made taken away, Claude Code's copy back at the version before, and the
    backup restored once more: PAGE_FAILED. Returns the page's registry entry."""
    u = Update(config, env, now)
    config = u.config  # Claude Code's own commands through the one running the chat, as hydra update's
    root = config["root"]
    with _Quiet(root, u.env):
        try:
            made = backup.take(root, "an update of %s to %s" % (page_id, version), u.now)
        except backup.Failed:
            raise shop.Refused(PAGE_NO_BACKUP % title)
        u.made = made
        folder = os.path.join(root, "hydra", "store", page_id, version)
        there = os.path.isdir(folder)
        was = {p["name"]: p["version"] for p in cl.plugins(config["claude"], config.get("claude_config", ""), cfg.STORE,
                                                            cwd=root, env=u.env)}.get(page_id)
        # what a killed update leaves to be put back at the next start (shop.recover)
        files.write_json(shop._p(root, shop.UPDATING), {"page": page_id, "version": version, "there": there,
                                                        "was": was or "", "backup": made, "pid": os.getpid(),
                                                        "at": u.now.isoformat()})
        try:
            u.planted("backup")
            record = (registry.app(root, page_id) or {}).get("record") or os.path.join(root, page_id)
            script = os.path.join(staged, "scripts", "migrate.py")
            if os.path.isfile(script):
                r = subprocess.run([config["python"], "-B", "-s", script, "--record", record], cwd=staged,
                                   env=dict(cfg.run_env(config), HYDRA_ROOT=root), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=300)
                said = r.stdout.decode("utf-8", "replace").strip().splitlines()
                applog.note("update", "%s's migrate: %s" % (page_id, said[0] if said else "no line"))
                if r.returncode != 0:
                    raise _Planted("migrate")
            u.planted("migrate")
            entry = shop._install(config, page_id, version, staged, None, u.env, prune=False)
            u.planted("store")
        except (shop.Refused, _Planted, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            applog.note("update", "%s's update stopped at %s; putting everything back" % (page_id, e))
            u.restore()
            if not there:
                shutil.rmtree(folder, ignore_errors=True)
            mine = "%s@%s" % (page_id, cfg.STORE)
            u.claude(["plugin", "marketplace", "update", cfg.STORE], timeout=120)
            u.claude(["plugin", "update", mine, "--scope", "local"])
            now_ = {p["name"]: p["version"] for p in cl.plugins(config["claude"], config.get("claude_config", ""),
                                                                 cfg.STORE, cwd=root, env=u.env)}
            if was and page_id in now_ and now_[page_id] != was:  # listed, and wrong: never on a list that failed
                u.claude(["plugin", "uninstall", mine, "--scope", "local"])
                u.claude(["plugin", "install", mine, "--scope", "local"])
            u.restore()
            shop._unjournal(root, shop.UPDATING)
            raise shop.Refused(PAGE_FAILED % title)
        shop._unjournal(root, shop.UPDATING)
        shop.prune_versions(root, page_id, version)  # one version kept back, once the whole update went through
        backup.prune(root)
        return entry


def went_through(lines):
    """Whether hydra update for Hydra-OS itself ended up to date or in place, so the pages may follow it."""
    last = lines[-1] if lines else ""
    return any(last == (said % last.split(" ")[1]) for said in (UP_TO_DATE, DONE)) if last.count(" ") >= 2 else False


READY = "Hydra-OS %s is ready. What's new:"
CURRENT = "Hydra-OS is up to date."


def ready(root, env=None):
    """The newer core the catalog in force offers, as Home's Update shows it, or "": no reading of the shop, just the
    copy the daily read kept, checked against the shop's key again."""
    have = str((registry.app(root, registry.MAIN) or {}).get("version") or "")
    core = shop.catalog(root, env).get("core") or {}
    return core["version"] if core.get("version") and shop.vt(core["version"]) > shop.vt(have) else ""
PAGE_READY = "%s %s is ready."


def check(config, env=None, now=None):
    """hydra update --check: what hydra update would bring, from the shop's signed catalog read fresh, changing nothing
    else: Hydra-OS's next version and its notes, or that it's up to date, then each page added from the shop that has a
    newer version. The shop's own line when it can't be read or doesn't check out."""
    root = config["root"]
    env = os.environ if env is None else env
    have = str((registry.app(root, registry.MAIN) or {}).get("version") or "")
    got = shop.read_catalog(config, now=_now(now), force=True, env=env)
    if got in ("none", "offline", "refused"):
        return [{"none": NO_SHOP, "offline": OFFLINE, "refused": NOT_CHECKED}[got]]
    want = shop.catalog(root, env).get("core") or {}
    if want.get("version") and shop.vt(want["version"]) > shop.vt(have):
        out = [READY % want["version"]] + ["- %s" % n for n in want.get("notes") or []]
    else:
        out = [UP_TO_DATE % have]
    return out + [PAGE_READY % (p["title"], p["version"]) for p in shop.state(root)["pages"] if p["state"] == "update"]


def core(config, env=None, now=None, load=None):
    """The lines hydra update says for Hydra-OS itself; Stop's line when it stopped."""
    try:
        return Update(config, env, now, load).run()
    except Stop as e:
        return [str(e)]

