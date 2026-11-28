"""The two launch agents, Hydra-OS's helpers: Home's server (`server.label`) and the tick (`tick.label`). Setup writes
and loads them only with `--jobs`, after the person's yes. Tests write plists only into a throwaway folder they name
and never call load().

  plists(config, release)        {label: the plist's dict}
  write(config, release, folder) each plist written whole, 0600, into `folder` (the person's ~/Library/LaunchAgents)
  load(paths)                    `launchctl bootstrap gui/<uid>` for each, only from setup with --jobs
  state(label)                   "running", "loaded" or "absent", from `launchctl print`

Each job runs config.json's python as `-B -s` on the installed release's own script, in `<root>`, with HYDRA_ROOT and
config.session_env's settings (Hydra-OS's own small tools first on PATH, and TMPDIR), and writes no log: a job's output
goes nowhere.

macOS names a job by its program in what it shows a person, in Login Items, so a job's program is
<root>/hydra/bin/Hydra-OS, a link to that python made as its plist is written, and it shows as Hydra-OS, not python3."""
import os
import plistlib
import signal
import subprocess
import tempfile

from . import applog
from . import config as cfg

PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
PROGRAM = "Hydra-OS"  # the name macOS shows for the jobs, in <root>/hydra/bin


def program(config):
    """<root>/hydra/bin/Hydra-OS: what each job runs, a link to config.json's python."""
    return os.path.join(config["root"], "hydra", "bin", PROGRAM)


def real_python(python):
    """The Python a job's link may point at: config.json's own, or, when that's one of Apple's /usr/bin stand-ins, the
    Python it starts, as that Python reports itself. Each stand-in picks its tool by its own name, so a link named
    Hydra-OS to one finds no tool, and macOS would offer to install the developer tools at each login."""
    if os.path.dirname(os.path.realpath(python)) != "/usr/bin":
        return python
    try:
        found = subprocess.run([python, "-I", "-c", "import sys; print(sys.executable)"], capture_output=True, text=True,
                               timeout=60, stdin=subprocess.DEVNULL, env={"PATH": PATH}).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return python
    if os.path.isabs(found) and os.path.isfile(found) and os.path.dirname(os.path.realpath(found)) != "/usr/bin":
        return found
    return python


def link_program(config):
    """Make <root>/hydra/bin/Hydra-OS a link to config.json's python, or to the real Python behind it (real_python), or
    point it there again. Python finds its own library through the link, as it does through its own bin/python3,
    itself a link. Returns its path."""
    path = program(config)
    target = real_python(config["python"])
    if os.path.islink(path) and os.readlink(path) == target:
        return path
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700)
    tmp = os.path.join(folder, ".%s.%d" % (PROGRAM, os.getpid()))
    if os.path.lexists(tmp):
        os.unlink(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, path)
    return path


def agents_folder(home=None):
    """~/Library/LaunchAgents; HYDRA_TEST_AGENTS, for tests only, names another folder, so a run against the real Claude
    app, which needs the real HOME, never writes the person's own LaunchAgents."""
    return os.environ.get("HYDRA_TEST_AGENTS") or os.path.join(home or os.path.expanduser("~"), "Library", "LaunchAgents")


def _job(config, release, label, script, extra=(), **keys):
    root = config["root"]
    doc = {"Label": label,
           "ProgramArguments": [program(config), "-B", "-s", os.path.join(release, "scripts", script), "--root", root,
                                *extra],
           "WorkingDirectory": root,
           # Hydra-OS's own small tools and TMPDIR, never a test's: a job runs on the person's Mac
           "EnvironmentVariables": dict(cfg.session_env(config), HYDRA_ROOT=root),
           "RunAtLoad": True,
           "StandardInPath": "/dev/null", "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}
    doc.update(keys)
    return doc


def plists(config, release):
    """The two jobs, by label. release: the main plugin's installed root."""
    tick = config.get("tick") or {}
    every = int(tick.get("every_minutes") or 15)
    return {
        config["server"]["label"]: _job(config, release, config["server"]["label"], "server.py",
                                        KeepAlive=True, ThrottleInterval=10),
        tick["label"]: _job(config, release, tick["label"], "tick.py", ("--how", "launchd"),
                            StartInterval=max(5, every) * 60, ProcessType="Background", LowPriorityIO=True),
    }


def _write(path, data):
    """Whole or not at all, mode 0600, leaving the folder's own mode as it is: it's the person's LaunchAgents folder."""
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write(config, release, folder, labels=None):
    """Write each plist whole, 0600, into `folder`, with the program each runs linked first. Returns the paths written.
    Nothing is loaded."""
    link_program(config)
    out = []
    for label, doc in plists(config, release).items():
        if labels is not None and label not in labels:
            continue
        path = os.path.join(folder, label + ".plist")
        _write(path, plistlib.dumps(doc))
        out.append(path)
    return out


def _uid():
    return str(os.getuid())


def own_home():
    """Whether this process's HOME is the account's own home folder. launchctl itself is asked nothing otherwise, so a
    test with a throwaway HOME never reaches the person's launchd, even if its stand-in's switch is lost on the way."""
    try:
        import pwd
        return os.path.realpath(os.path.expanduser("~")) == os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return False


def load(paths, runner=subprocess.run):
    """Load each written job for the person, only from setup with --jobs. A job of the same label still loaded, as an
    older or broken install can leave one, is booted out first, so its bootstrap never fails on it. Returns the labels
    that loaded."""
    done = []
    if not own_home():
        applog.note("launchctl", "this isn't the account's own home, so nothing was loaded")
        return done
    for path in paths:
        label = os.path.basename(path)[:-len(".plist")]
        if state(label, runner) != "absent":
            unload(label, runner)
        r = runner(["/bin/launchctl", "bootstrap", "gui/" + _uid(), path], capture_output=True, text=True, timeout=30)
        applog.note("launchctl", "bootstrap %s: exit %d" % (os.path.basename(path), r.returncode))
        if r.returncode == 0:
            done.append(os.path.basename(path)[:-len(".plist")])
    return done


def retire_others(config, home=None):
    """Every os.hydra.* job in the person's LaunchAgents that this build doesn't use, as an older build's os.hydra.seat,
    booted out and its plist removed. Returns the labels it took away."""
    folder = agents_folder(home)
    ours = {config["server"]["label"], (config.get("tick") or {}).get("label")}
    gone = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return gone
    for name in names:
        label = name[:-len(".plist")] if name.endswith(".plist") else ""
        if label.startswith("os.hydra.") and label not in ours:
            unload(label)
            try:
                os.unlink(os.path.join(folder, name))
            except OSError:
                continue
            gone.append(label)
    return gone


def untouchable():
    """True under any HYDRA_TEST_ switch unless HYDRA_TEST_LAUNCHCTL names launchctl's stand-in: such a test asks
    launchd nothing and touches no LaunchAgents folder, the person's own least of all."""
    return any(k.startswith("HYDRA_TEST_") for k in os.environ) and not os.environ.get("HYDRA_TEST_LAUNCHCTL")


def loader(home=None):
    """The way to load jobs: launchctl itself, or, under HYDRA_TEST_LAUNCHCTL, its stand-in (test_load)."""
    record = os.environ.get("HYDRA_TEST_LAUNCHCTL")
    return test_load(record, home or os.path.expanduser("~")) if record else load


def retire_own(config, home=None):
    """With the helpers off, nothing starts at login: this build's own two jobs, Home's server's and the tick's, booted
    out where an older install left them loaded, and their plists removed. Returns {label: its state before} for each
    one it took away."""
    if untouchable():
        return {}
    folder = agents_folder(home)
    gone = {}
    for label in (config["server"]["label"], (config.get("tick") or {}).get("label")):
        if not label:
            continue
        plist = os.path.join(folder, label + ".plist")
        was = state(label)
        if was == "absent" and not os.path.lexists(plist):
            continue
        unload(label)
        if os.path.lexists(plist):
            os.unlink(plist)
        gone[label] = was
    return gone


def test_load(record, home):
    """HYDRA_TEST_LAUNCHCTL, for tests only, in place of launchctl: each job's plist path is added to `record`, and
    Home's server's job is started as launchd would start it, so setup can go on, with the test's own stand-in Claude
    Code. Each one started gets the run's own HYDRA_TEST_* switches beside its plist's environment, as no real job ever
    has them, so a test's job opens and loads nothing real, such as /usr/bin/open. Each one started is kept in `record`.pids, "<label> <pid>", so
    a bootout stops it, as launchd's does. Nothing is loaded."""
    def load(paths):
        switches = {k: v for k, v in os.environ.items() if k.startswith("HYDRA_TEST_")}
        done = []
        for path in paths:
            with open(path, "rb") as f:
                doc = plistlib.load(f)
            _stop_test_job(record, doc["Label"])  # one still loaded is booted out first, as load() does
            with open(record, "a", encoding="utf-8") as f:
                f.write(path + "\n")
            done.append(doc["Label"])
            if any(str(a).endswith(os.sep + "server.py") for a in doc["ProgramArguments"]):
                p = subprocess.Popen(doc["ProgramArguments"], cwd=doc["WorkingDirectory"],
                                     env=dict(doc["EnvironmentVariables"], HOME=home, **switches), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                with open(record + ".pids", "a", encoding="utf-8") as f:
                    f.write("%s %d\n" % (doc["Label"], p.pid))
        return done
    return load


def _stop_test_job(record, label):
    """Tests only: what launchd's bootout does to a job test_load started, its process stopped."""
    try:
        with open(record + ".pids", encoding="utf-8") as f:
            pids = [int(x.split()[1]) for x in f if x.split()[:1] == [label] and len(x.split()) == 2]
    except (OSError, ValueError):
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def unload(label, runner=subprocess.run):
    """Stop the person's own job, `launchctl bootout gui/<uid>/<label>`, which needs no administrator. True when it
    stopped, or wasn't loaded. HYDRA_TEST_LAUNCHCTL, for tests only: "bootout <label>" is added to its record and
    nothing is run."""
    record = os.environ.get("HYDRA_TEST_LAUNCHCTL")
    if record:
        with open(record, "a", encoding="utf-8") as f:
            f.write("bootout %s\n" % label)
        _stop_test_job(record, label)
        return True
    if not own_home():
        return True  # nothing of the person's launchd is touched from a throwaway home
    try:
        r = runner(["/bin/launchctl", "bootout", "gui/%s/%s" % (_uid(), label)], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        applog.note("launchctl", "bootout %s: didn't end" % label)
        return False
    applog.note("launchctl", "bootout %s: exit %d" % (label, r.returncode))
    return r.returncode in (0, 3, 113)  # 3 and 113: no such job loaded


def state(label, runner=subprocess.run):
    """"running" while the job runs, "loaded" when it's loaded and not running, "absent" when it isn't loaded. Under
    HYDRA_TEST_LAUNCHCTL, for tests only, launchd isn't asked: a job its record names is "loaded", any other "absent"."""
    record = os.environ.get("HYDRA_TEST_LAUNCHCTL")
    if record:
        try:
            with open(record, encoding="utf-8") as f:
                named = {os.path.basename(line.strip()) for line in f}
        except OSError:
            named = set()
        return "loaded" if label + ".plist" in named else "absent"
    if not own_home():
        return "absent"
    try:
        r = runner(["/bin/launchctl", "print", "gui/%s/%s" % (_uid(), label)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "absent"
    if r.returncode != 0:
        return "absent"
    return "running" if "state = running" in (r.stdout or "") else "loaded"
