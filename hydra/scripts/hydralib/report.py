"""hydra report: how Hydra-OS is running on this Mac, in states and counts
only, for the person to read whole before they copy it from Help, or for
Claude to read in their chat. Never a record, a goal, a source's name, a figure or anything they typed:

- Hydra-OS's version and build, the Python it runs on, macOS and the chip, and the Claude Code version setup found;
- each installed page's id and version, and how many were added from the shop;
- the morning review on, off or not asked;
- health.json's sign-in state, and each run's app, state and time (never its line, which may hold a figure);
- setup.json's checks, by name, each ok or not;
- the shop's last catalog read, its result and time; the last update's backup, its time and why, and how many are kept;
- the log's last lines (applog.last), each cleaned again, with any word of the person's name or city taken out, and
  in each note's own words, whatever it quoted, every figure (an amount, a number with a point or thousands, a
  percentage, a long run of digits) and every word of their own goals and sources (FIGURES, theirs).

  build(config, env=None, now=None)   the report's text, one line each
"""
import datetime
import os
import platform
import re

from . import applog, backup, files, health, registry, settings, shop, sources, you

LOG_LINES = 40
STAMP = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")  # a log line's own time, kept
FIGURES = [re.compile(p, re.I) for p in (
    r"[$€£¥]\s?\d[\d,]*(?:\.\d+)?",  # an amount with its sign
    r"\b\d[\d,]*(?:\.\d+)?\s?(?:usd|eur|gbp|cad|aud|dollars?|euros?|pounds?)\b",
    r"(?<![\w.-])\d(?:[ -]?\d){7,}(?![\w-])",  # a long run of digits, spaced or dashed: an account, a card
    r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d.,])",  # thousands
    r"(?<![\d.])\d+\.\d+(?![\d.])",  # a number with a point, never a version's x.y.z
    r"\b\d+(?:\.\d+)?\s?%",
)]
STOP = frozenset("a an and the for by to of in on at my your our with or per each from into than then be is it as up "
                 "so all any".split())


def _private(root):
    """The person's own words a report never holds: each word of their name and their city."""
    words = re.findall(r"[^\W\d_][\w'’-]*", you.name(root), re.UNICODE)
    place = you.place(root) or {}
    words += re.findall(r"[^\W\d_][\w'’-]*", str(place.get("city") or ""), re.UNICODE)
    return sorted({w for w in words if len(w) >= 2}, key=len, reverse=True)


def _theirs(root):
    """Every word of the person's own goals (their text and why) and sources (as recorded, and their accounts) but a
    few short joining words (STOP): what a note's own words may have quoted."""
    doc = files.read_json(os.path.join(root, "yours", "goals.json"), {})
    texts = []
    for g in (doc.get("goals") or []) if isinstance(doc, dict) else []:
        if isinstance(g, dict):
            texts += [g.get(k) for k in ("text", "why") if isinstance(g.get(k), str)]
    for r in sources.read(root):
        texts += [r.get(k) for k in ("source", "account") if isinstance(r.get(k), str)]
    words = {w for t in texts for w in re.findall(r"[^\W\d_][\w'’-]*", t, re.UNICODE)}
    return sorted({w for w in words if len(w) >= 2 and w.lower() not in STOP}, key=len, reverse=True)


def scrub(line, private, theirs=()):
    """A line as the report holds it: cleaned as the log is, and no word of the person's name or city. A log line's
    own words lose every figure and every word of their goals and sources too; its time stays."""
    line = applog.clean(line)
    stamp = STAMP.match(line)
    head, body = (line[:stamp.end()], line[stamp.end():]) if stamp else ("", line)
    if stamp or theirs:
        for pattern in FIGURES:
            body = pattern.sub(applog.TAKEN, body)
    for w in list(private) + list(theirs):
        body = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(w), applog.TAKEN, body, flags=re.I)
    return head + body


def _macos():
    try:
        return platform.mac_ver()[0] or "unknown"
    except Exception:
        return "unknown"


def build(config, env=None, now=None):
    root = config["root"]
    now = now or datetime.datetime.now().astimezone()
    apps = registry.read(root).get("apps", [])
    main = next((a for a in apps if a.get("kind") == "main"), {})
    setup = files.read_json(os.path.join(root, "hydra", "setup.json"), {})
    setup = setup if isinstance(setup, dict) else {}
    built = setup.get("build") if isinstance(setup.get("build"), dict) else {}
    out = ["Hydra-OS report, %s" % now.strftime("%A %b %-d, %H:%M"),
           "Hydra-OS %s%s, on Python %s, macOS %s, %s." % (
               main.get("version") or "unknown", " (build %s)" % built["commit"] if built.get("commit") else "",
               platform.python_version(), _macos(), platform.machine() or "unknown chip"),
           "Claude Code %s." % (config.get("claude_version") or "not found")]
    pages = [a for a in apps if a.get("kind") != "main" and a.get("id")]
    bought = shop.bought(root)
    out.append("Pages: %d installed%s%s." % (
        len(pages), ": " + ", ".join("%s %s" % (a["id"], a.get("version") or "?") for a in pages) if pages else "",
        "; %d added from the shop" % len(bought) if bought else ""))
    review = settings.read(root).get("review")
    out.append("Morning review: %s." % ("on" if review is True else "off" if review is False else "not asked yet"))
    doc = health.read(root)
    sign = (doc.get("sign_in") or {}).get("state") if doc else None
    out.append("Sign-in: %s." % (sign or "not checked yet"))
    runs = [r for r in doc.get("runs") or [] if isinstance(r, dict)] if doc else []
    out.append("Runs: %s." % ("; ".join("%s %s%s" % (r.get("app"), r.get("state"), " at %s" % r["at"] if r.get("at")
                                                    else "") for r in runs) if runs else "none yet"))
    checks = [c for c in setup.get("checks") or [] if isinstance(c, dict) and c.get("name")]
    out.append("Setup's checks: %s." % (", ".join("%s %s" % (c["name"], "ok" if c.get("ok") else "not ok")
                                                  for c in checks) if checks else "none kept"))
    read = files.read_json(os.path.join(root, "hydra", "shop", "read.json"), {})
    read = read if isinstance(read, dict) else {}
    out.append("Shop: %s." % ("its list %s at %s" % (read.get("result"), read.get("at")) if read.get("result")
                              else "no list read yet"))
    kept = backup.backups(root)
    if kept:
        try:
            last_backup = backup.manifest(kept[-1])
            out.append("Updates: the last backup %s, %s; %d kept." % (last_backup.get("at", "?"),
                                                                      last_backup.get("why", "?"), len(kept)))
        except backup.Failed:
            out.append("Updates: %d backups kept." % len(kept))
    else:
        out.append("Updates: no backup yet.")
    private, theirs = _private(root), _theirs(root)
    lines = [scrub(l, private, theirs) for l in applog.last(root, LOG_LINES)]
    out.append(("Its log's last line:" if len(lines) == 1 else "Its log's last %d lines:" % len(lines)) if lines
               else "Its log: nothing yet.")
    out += ["  " + l for l in lines]
    return "\n".join(scrub(l, private) for l in out)
