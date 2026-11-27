"""Free space, checked before Hydra-OS writes anything large: setup needs 1 GB free; a page's add or update three times
its pack, and
256 MB more; hydra update three times its zip, and 512 MB more. Short of it, nothing is changed and NEEDS says how much.
The tick starts no run with under 256 MB free, and the run waits, as FULL_RUN says.

HYDRA_TEST_FREE=<bytes>, for tests only, stands for the Mac's free space. Python 3.9 standard library only."""
import math
import os
import shutil

MB = 1024 * 1024
GB = 1024 * MB
SETUP = GB
PAGE_MORE = 256 * MB
CORE_MORE = 512 * MB
TICK_LOW = 256 * MB
NEEDS = "Your Mac needs about %s GB free for this. Free some space, then try again."
FULL_RUN = "Your Mac is nearly full, so %s waits."


class Short(Exception):
    """Not enough room: NEEDS's line."""


def free(path, env=None):
    """Bytes free on the disk that holds path, or the nearest folder above it that's there."""
    env = os.environ if env is None else env
    given = env.get("HYDRA_TEST_FREE")
    if given is not None:
        try:
            return int(given)
        except ValueError:
            pass
    here = os.path.abspath(path)
    while not os.path.exists(here) and os.path.dirname(here) != here:
        here = os.path.dirname(here)
    try:
        return shutil.disk_usage(here).free
    except OSError:
        return 0


def gb(n):
    """About how many GB, as a person reads it: one decimal up to 10, whole above."""
    value = n / GB
    return "%d" % math.ceil(value) if value >= 10 else ("%.1f" % (math.ceil(value * 10) / 10)).rstrip("0").rstrip(".")


def need(path, n, env=None):
    """Short with NEEDS's line when the disk that holds path has under n bytes free."""
    if free(path, env) < n:
        raise Short(NEEDS % gb(n))
