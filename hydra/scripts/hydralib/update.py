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
  8. Home's server and the tick started again from the new core, and Home answering again.
Any failure from 4 on puts everything back: the backup restored, the new store folder taken away, Claude Code's copy
back at the old version (plugin update again, else uninstall and install), the jobs from the old core again: FAILED.
One version is kept back in the store, and the last two backups.

HYDRA_TEST_UPDATE_FAIL=<step>, for tests only, stops the update at the end of that step (backup, migrate, store,
claude, registry, jobs or server), as Checks plants a failure at each one.

  core(config, env=None, now=None, load=None)    the lines hydra update says for Hydra-OS itself
"""
import datetime
import http.client
import json
import os
import shutil
import subprocess
import time
import zipfile

from . import applog, backup, files, jobs, registry, review_fence, runs, shop, space
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
STEPS = ("backup", "migrate", "store", "claude", "registry", "jobs", "server")
EXTRA = (os.path.join("hydra", "bin", ".hydra.py"), os.path.join("hydra", "setup.json"))


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
        self.restore()
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
            self.jobs_step(new["root"])
            self.planted("jobs")
            self.wait_server()
            self.planted("server")
        except (_Planted, OSError, ValueError, KeyError) as e:
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


def core(config, env=None, now=None, load=None):
    """The lines hydra update says for Hydra-OS itself; Stop's line when it stopped."""
    try:
        return Update(config, env, now, load).run()
    except Stop as e:
        return [str(e)]

