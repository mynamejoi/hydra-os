"""Goals' doctor, Python 3.9 standard library only:

    python3 scripts/doctor.py [--record DIR] [--now ISO]

It prints one line per requirement, in a fixed order, and nothing else: `PASS <name>[: <detail>]` or
`FAIL <name>: <detail>. Fix: <fix>`. It writes doctor.json whole into the record and changes nothing else, and it
exits 0 when every line passes, 1 when any fails. Goals reads no source and starts no `claude`, so it has no source
lines, and its runs pass `servers` with no server at all.

    installed   from a release: release.json beside its plugin.json, naming its version
    python      it's running on config.json's python, Hydra-OS's own
    schedule    the tick's health.json says Goals ran, and its newest scheduled run is within a day and two hours
    servers     its newest run and newest two scheduled runs started no model and listed no server
    record      the record folder is there, 0700, writable, and not in a folder that syncs to a cloud
    fresh       the page and STATUS.md are no older than the newest run
    private     STATUS.md holds states and counts only, and none of the goals' own words
    replaces    one for each routine Goals takes over, from the record's replaces.json, when there is one

Every detail and fix is in plain words, with states, counts and times only: never a goal's words or a figure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import re
import subprocess
import sys

import common
import goalsfile

WINDOW = dt.timedelta(hours=26)  # a daily run, plus two hours
REPAIR = "say 'repair Hydra-OS' to Claude"
REOPEN = "open Hydra-OS again to put it back"  # what the app's setup does for a missing part
PYTHON_MISSING = "part of Hydra-OS is missing from this Mac"  # setup's own words for a missing Python, as a detail
SYNCED_NAMES = ("dropbox", "google drive", "onedrive", "box")
CODES = r"USD|EUR|GBP|CAD|AUD|JPY|CHF|BTC|ETH"
MONEY_WORDS = r"dollars?|cents?|bucks"
# What a line for others never holds, one pattern or more for each kind the states-and-counts check names. Every
# doctor carries its own copy. A key is a token after key, token, secret or password, or one of the common services'
# key shapes.
KINDS = [
    ("money", re.compile(r"[$€£¥₹₩₿]\s?\d")),
    ("money", re.compile(rf"\d[\d,.]*\s?(?:{CODES}|{MONEY_WORDS})\b", re.I)),
    ("money", re.compile(rf"\b(?:{CODES})\s?\d", re.I)),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\d.])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\d.])")),
    ("phone", re.compile(r"(?<!\w)\+\d{10,15}(?!\d)")),
    ("account", re.compile(r"(?<!\d)\d{9,}(?!\d)")),
    ("key", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    ("key", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("key", re.compile(r"\b(?:api[_-]?key|key|token|secret|password|passwd)\b\s*[:=]\s*[\"']?[^\s\"']{8,}", re.I)),
    ("key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("key", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}")),
    ("key", re.compile(r"\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{35}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("home folder", re.compile(r"/Users/[^/\s]+/")),
]
GROUPED_DIGITS = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")


def luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def kinds_in(text: str) -> list:
    """Each kind the text holds, once, in the table's order; a card number is 13 to 19 digits that pass the Luhn check."""
    out = []
    for kind, rx in KINDS:
        if kind not in out and rx.search(text or ""):
            out.append(kind)
    cards = (m.group().replace(" ", "").replace("-", "") for m in GROUPED_DIGITS.finditer(text or ""))
    if "card" not in out and any(luhn(c) for c in cards):
        out.append("card")
    return out


def line(name, ok, detail="", fix=""):
    return {"name": name, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix}


def clock(t: dt.datetime) -> str:
    return f"{t:%a %b} {t.day}, {t:%H:%M}"


def plugin_version() -> str:
    got = common.load_json(common.PLUGIN / ".claude-plugin" / "plugin.json", {})
    return got.get("version", "") if isinstance(got, dict) else ""


# ---- each line ---------------------------------------------------------------------------------------------------

def installed() -> dict:
    """From a release export. Strict validation is the release's own, so release.json stands for it, and the doctor
    starts no `claude`, scheduled or by hand."""
    fix = "install the newest release of Goals, as SETUP.md says"
    rel = common.load_json(common.PLUGIN / "release.json", None)
    if not isinstance(rel, dict):
        return line("installed", False, "running from a working folder, not a release", fix)
    if rel.get("plugin") != common.ID or rel.get("version") != plugin_version():
        return line("installed", False, "its release.json doesn't match its plugin.json", fix)
    return line("installed", True, f"release {rel['version']}", fix)


def python(root) -> dict:
    """Running on config.json's python. A shim such as macOS's /usr/bin/python3 names another file as its own, so
    config's python is asked what it calls itself."""
    config = common.load_json(pathlib.Path(root) / "hydra" / "config.json", None)
    want = config.get("python") if isinstance(config, dict) else None
    if not (isinstance(want, str) and os.path.isabs(want) and os.access(want, os.X_OK)):
        return line("python", False, PYTHON_MISSING, REOPEN)
    here = os.path.realpath(sys.executable)
    same = here == os.path.realpath(want)
    if not same:
        try:
            said = subprocess.run([want, "-c", "import sys; print(sys.executable)"], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=20).stdout.strip()
            same = bool(said) and os.path.realpath(said) == here
        except (OSError, subprocess.TimeoutExpired):
            same = False
    version = "%d.%d.%d" % sys.version_info[:3]
    return line("python", same, f"Python {version}" if same else PYTHON_MISSING, REPAIR if same else REOPEN)


def runs_of(record) -> list:
    return [r for r in common.lines(pathlib.Path(record) / "runs.jsonl") if common.parse_time(r.get("started_at"))]


def schedule(root, runs, now) -> dict:
    sched = common.load_json(common.PLUGIN / "column.json", {}).get("schedule") or {}
    at = sched.get("at", "")
    health = common.load_json(pathlib.Path(root) / "hydra" / "health.json", None)
    entry = None
    if isinstance(health, dict):
        entry = next((r for r in health.get("runs") or [] if isinstance(r, dict) and r.get("app") == common.ID), None)
    if entry is None:
        return line("schedule", False, "the tick hasn't seen this page yet", REPAIR)
    state, said = entry.get("state"), str(entry.get("said") or "").rstrip(".")
    if state == "running":
        return line("schedule", True, "running now")
    if state == "due":
        return line("schedule", False, f"no scheduled run yet, daily at {at}",
                    f"nothing to do: it runs at {at}, or say 'run Goals now' to Claude")
    if state in ("missed", "failed", "waiting"):
        fix = "do what it says, and the run starts by itself" if state == "waiting" else REPAIR
        return line("schedule", False, said or {"missed": "its run was missed", "failed": "its run didn't finish"}.get(
            state, "its run is waiting"), fix)
    if state != "ran":
        return line("schedule", False, "the tick's word for it isn't one this doctor knows", REPAIR)
    scheduled = [r for r in runs if r.get("trigger") == "schedule"]
    if not scheduled:
        return line("schedule", False, "no scheduled run yet", f"nothing to do: it runs at {at}")
    t = common.parse_time(scheduled[-1]["started_at"])
    if now - t > WINDOW:
        return line("schedule", False, f"no scheduled run since {clock(t)}", REPAIR)
    return line("schedule", True, f"ran {clock(t)}, daily at {at}")


def servers(runs) -> dict:
    fix = "start its run with no model and no server, as Goals' run does"
    if not runs:
        return line("servers", False, "no run yet", "nothing to do until its first run, or say 'run Goals now' to Claude")
    newest = [runs[-1]] + [r for r in runs if r.get("trigger") == "schedule"][-2:]
    for r in newest:
        if r.get("model") is not False or r.get("mcp_servers") != [] or any(
                k in r for k in ("mcp_log", "claude_ai_connectors", "setting_sources")):
            return line("servers", False, "a run started a model or listed a server it doesn't need", fix)
    return line("servers", True, "no model and no server, as it needs")


def synced(path: pathlib.Path) -> bool:
    real = pathlib.Path(os.path.realpath(path))
    home = pathlib.Path.home()
    cloud = [home / "Library" / "Mobile Documents", home / "Library" / "CloudStorage"]
    if any(str(real).startswith(os.path.realpath(c) + os.sep) for c in cloud):
        return True
    if any(part.lower() in SYNCED_NAMES for part in real.parts):
        return True
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    for name in ("Desktop", "Documents"):
        mine, theirs = home / name, icloud / name
        try:
            if theirs.exists() and mine.exists() and os.path.samefile(mine, theirs):
                if str(real).startswith(os.path.realpath(mine) + os.sep) or real == pathlib.Path(os.path.realpath(mine)):
                    return True
        except OSError:
            pass
    return False


def record_line(record) -> dict:
    record = pathlib.Path(record)
    fix = REPAIR
    if not record.is_dir():
        return line("record", False, "Goals' folder isn't there", fix)
    if not os.access(record, os.W_OK):
        return line("record", False, "Goals' folder can't be written", fix)
    if record.stat().st_mode & 0o777 != 0o700:
        return line("record", False, "Goals' folder isn't private to you", fix)
    if synced(record):
        return line("record", False, "Goals' folder is in a folder that syncs to a cloud",
                    "move Hydra-OS out of the synced folder, then " + REPAIR)
    page = record / "page"
    if page.is_dir() and page.stat().st_mode & 0o777 != 0o700:
        return line("record", False, "the page's folder isn't private to you", fix)
    index = page / "index.html"
    if index.is_file() and index.stat().st_mode & 0o777 != 0o600:
        return line("record", False, "the page isn't private to you", fix)
    return line("record", True)


def built_at(record):
    try:
        head = (pathlib.Path(record) / "page" / "index.html").read_text(encoding="utf-8")[:4096]
    except OSError:
        return None
    m = re.search(r'<meta name="built-at" content="([^"]+)">', head)
    return common.parse_time(m.group(1)) if m else None


def status_time(record):
    try:
        return dt.datetime.fromtimestamp((pathlib.Path(record) / "STATUS.md").stat().st_mtime).astimezone()
    except OSError:
        return None


def fresh(record, runs) -> dict:
    fix = "say 'run Goals now' to Claude"
    if not runs:
        return line("fresh", False, "no run yet", fix)
    start = common.parse_time(runs[-1]["started_at"])
    page, status = built_at(record), status_time(record)
    if page is None or status is None:
        return line("fresh", False, "the page or STATUS.md isn't there", fix)
    if page < start or status < start:
        return line("fresh", False, f"older than the run of {clock(start)}", fix)
    return line("fresh", True, f"as of the run of {clock(start)}")


def private(root, record) -> dict:
    fix = "say 'run Goals now' to Claude, so STATUS.md is written again"
    try:
        text = (pathlib.Path(record) / "STATUS.md").read_text(encoding="utf-8")
    except OSError:
        return line("private", False, "STATUS.md isn't there", fix)
    kinds = kinds_in(text)
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        doc = goalsfile.empty()
    low = text.lower()
    if any(isinstance(g.get(k), str) and len(g[k]) > 3 and g[k].lower() in low for g in doc["goals"] for k in ("text", "why")):
        kinds.append("a goal's own words")
    if kinds:
        return line("private", False, f"STATUS.md holds {len(kinds)} kind{'s' * (len(kinds) > 1)} of thing it never "
                    "should", fix)
    return line("private", True, "states and counts only")


def replaces(root, record) -> list:
    """One line for each routine Goals takes over: its record's replaces.json, read against Hydra-OS's log of
    what's switched off. A release replaces nothing of its own."""
    got = common.load_json(pathlib.Path(record) / "replaces.json", None)
    items = got.get("items") if isinstance(got, dict) and got.get("contract") == "replaces/v1" else None
    out = []
    try:
        retired = (pathlib.Path(root) / "hydra" / "RETIRE.md").read_text(encoding="utf-8")
    except OSError:
        retired = ""
    for item in items or []:
        rid = item.get("id") if isinstance(item, dict) else None
        if not (isinstance(rid, str) and re.fullmatch(r"[a-z0-9-]{1,40}", rid)):
            continue
        off = re.search(rf"^\|\s*{re.escape(rid)}\s*\|", retired, re.M) is not None
        out.append(line(f"replaces {rid}", off, "switched off" if off else "still running",
                        "Hydra-OS switches it off at cutover, with your yes"))
    return out


# ---- the whole check -----------------------------------------------------------------------------------------------

def check(root, record, now) -> dict:
    """Every line, and doctor.json's document. Writes nothing."""
    runs = runs_of(record)
    lines = [installed(), python(root), schedule(root, runs, now), servers(runs), record_line(record),
             fresh(record, runs), private(root, record)] + replaces(root, record)
    page, status = built_at(record), status_time(record)
    return {
        "contract": "doctor/v1", "pillar": common.ID, "plugin_version": plugin_version(),
        "checked_at": common.iso(now), "ok": all(x["ok"] for x in lines), "lines": lines, "runs": runs[-10:],
        "servers_needed": [], "page_built_at": common.iso(page) if page else None,
        "status_written_at": common.iso(status) if status else None,
    }


def write(record, doc) -> bool:
    """doctor.json whole, unless the record can't take it."""
    record = pathlib.Path(record)
    if not record.is_dir() or not os.access(record, os.W_OK):
        return False
    common.write_json(record / "doctor.json", doc)
    return True


def printed(doc) -> str:
    out = []
    for x in doc["lines"]:
        if x["ok"]:
            out.append(f"PASS {x['name']}" + (f": {x['detail']}" if x["detail"] else ""))
        else:
            out.append(f"FAIL {x['name']}: {x['detail']}. Fix: {x['fix']}.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check everything Goals needs.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    try:
        now = common.now(a.now)
    except ValueError:
        print("FAIL record: --now isn't a time with its offset. Fix: give it as 2026-11-25T07:40:00-05:00.")
        return 1
    try:
        root = common.root_of(a.record)
    except common.NotSetUp:
        print(f"FAIL record: {common.NOT_SET_UP.rstrip('.')}. Fix: install Hydra-OS, as SETUP.md says.")
        return 1
    record = common.record_of(root, a.record)
    doc = check(root, record, now)
    write(record, doc)
    print(printed(doc))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
