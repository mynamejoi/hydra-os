"""Which build of Hydra-OS a release is, and whether a Hydra-OS folder was set up by an older one. Every build has the
same plugin version, so the version can't tell them apart.

- **A release's own build:** `build.json` in the main plugin's folder, {"commit": "<short hash>", "time": <the commit's
  time, in seconds since 1970>}, written by shell/mac-app/make_app.py into the release it puts in the app. A release with
  none, as a test's or a working folder's, has no build, and nothing is ever an update to it.
- **The folder's build:** `build` in <root>/hydra/setup.json, written by setup's self-test from the release it set up.
  A folder set up before builds were kept has none.
- **An update:** a folder set up by a build older than this release's, or with no build of its own, while this release
  has one. Builds are compared by their commit's time.

Python 3.9 standard library only."""
import os
import re

from . import files

HASH = re.compile(r"[0-9a-f]{7,40}")


def _clean(doc):
    """{"commit", "time"} from a build record, or None when it isn't one."""
    if not isinstance(doc, dict):
        return None
    commit, time = doc.get("commit"), doc.get("time")
    if not isinstance(commit, str) or not HASH.fullmatch(commit) or not isinstance(time, int) or isinstance(time, bool):
        return None
    return {"commit": commit, "time": time}


def own(plugin):
    """The build of the release whose main plugin is in `plugin`, or None."""
    return _clean(files.read_json(os.path.join(plugin, "build.json"), None))


def recorded(root):
    """The build that last set up the folder at `root`, from its setup.json, or None."""
    doc = files.read_json(os.path.join(root, "hydra", "setup.json"), None)
    return _clean(doc.get("build")) if isinstance(doc, dict) else None


def older(a, b):
    """True when build a is older than build b. A missing a is older than any b; nothing is older than a missing b."""
    if b is None:
        return False
    if a is None:
        return True
    return a["time"] < b["time"]


def updates(root, plugin):
    """True when the folder at `root` was set up, by a build older than the one in `plugin`."""
    if not os.path.isfile(os.path.join(root, "hydra", "setup.json")):
        return False
    return older(recorded(root), own(plugin))
