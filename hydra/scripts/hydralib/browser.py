"""A link that leaves a page, opened in the person's own browser: Research's sources, Inbox's "Open in Gmail". Never
inside the Claude app's pane, where Claude can read what a
page shows, and https only, as the checkout is.

  link(text)              the link as it opens, or None: https, a host, and no user info, port, space or hidden character
  open_link(text, env)    opened with /usr/bin/open; HYDRA_TEST_OPENED records it for a test instead
"""
import os
import subprocess
import unicodedata
import urllib.parse

MOST = 1000  # characters in one link, within the server's 1 KB for a small write
OPEN = "/usr/bin/open"


def link(text):
    """The link as it opens, or None when it isn't one Hydra-OS opens: https only, with a host, and no user info, no
    port, no space and no control or format character, in at most 1,000 characters."""
    if not isinstance(text, str) or not text or len(text) > MOST:
        return None
    if any(c.isspace() or unicodedata.category(c) in ("Cc", "Cf", "Co", "Cs", "Cn") for c in text):
        return None
    try:
        u = urllib.parse.urlsplit(text)
        port = u.port
    except ValueError:
        return None
    if u.scheme != "https" or not u.hostname or "@" in u.netloc or port is not None or not text.startswith("https://"):
        return None
    return text


def open_link(text, env=None):
    """Open a link in the person's own browser; raise ValueError for one link() refuses."""
    env = os.environ if env is None else env
    url = link(text)
    if url is None:
        raise ValueError("not a link Hydra-OS opens")
    if env.get("HYDRA_TEST_OPENED"):
        with open(env["HYDRA_TEST_OPENED"], "a") as f:
            f.write(url + "\n")
        return
    subprocess.run([OPEN, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=30)
