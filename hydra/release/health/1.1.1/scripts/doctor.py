#!/usr/bin/env python3
"""Health's doctor: one line per requirement, in a fixed order, then doctor.json in Health's folder. It changes nothing
else, calls no model, starts no other program, sends nothing and needs no network.

    python3 scripts/doctor.py [--record DIR] [--now ISO]

Lines, in order: installed, python, one source line for each source column.json declares, schedule, servers, record,
fresh, private, then a replaces line for each item in the folder's own replaces.json. Exit 0 when every line passes,
1 when any fails. Details and fixes hold states, counts and times only, in plain words a person can act on.

- A source line judges the newest run that tried that source. A source the person didn't choose in
  <root>/yours/sources.json passes as not chosen; with no choice recorded at all, every source is judged by the runs.
- The schedule line reads Hydra-OS's own <root>/hydra/health.json, this app's entry.
- The servers line holds the newest run, and each of the newest two scheduled runs, to the rules
  for a run: a run that called Claude loaded no server Health doesn't need, by its own stream's first message,
  and kept claude.ai connectors off and the person's own settings out; it carries no debug-log finding. A run that
  made no call says so and lists no server. The schedule's launcher is `run`.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

import common
import privacy

INTERVAL_HOURS = 24
GRACE_HOURS = 2
SYNCED = re.compile(r"/Library/(Mobile Documents|CloudStorage)/|/(Dropbox|Google Drive|OneDrive|Box)(/|$)", re.I)
MODEL_KEYS = ("mcp_log", "claude_ai_connectors", "setting_sources")
CONNECT = "Connect a wearable, in Claude."
DROP = f"Drop your Apple Health export on the {common.TITLE} page."   # an upload source's way in, the page's drop place
REPAIR = "Repair, in Help, finds what's wrong and puts it right."
REOPEN = "Repair, in Help, puts it back."   # the app's setup runs again when a part is gone


def line(name, ok, detail="", fix=""):
    """One line. A detail is a phrase, never ending in a full stop, so a FAIL reads "<detail>. Fix: <fix>"."""
    return {"name": name, "ok": bool(ok), "detail": str(detail).strip().rstrip("."), "fix": "" if ok else (fix or REPAIR)}


def when(s):
    return common.parse_time(s) if isinstance(s, str) else None


def runs_of(rec) -> list:
    rows = [r for r in common.read_jsonl(rec / "runs.jsonl") if when(r.get("started_at"))]
    return sorted(rows, key=lambda r: when(r["started_at"]))


def fresh_enough(t, now) -> bool:
    return t is not None and now - t <= dt.timedelta(hours=INTERVAL_HOURS + GRACE_HOURS)


# ---- the lines ----

def installed() -> dict:
    """From a release export: its release.json names this app and this version. The export checked the plugin when it
    was made, so release.json stands for that check, and nothing is started here to check it again."""
    rel = common.load_json(common.ROOT / "release.json", None)
    version = common.plugin_version()
    if not (isinstance(rel, dict) and rel.get("plugin") == common.ID and rel.get("version") == version):
        return line("installed", False, "running from a working folder, not a release",
                    f"Hydra-OS's next update brings in {common.TITLE}'s newest release.")
    return line("installed", True, f"release {version}")


def python_line(root) -> dict:
    """The doctor runs on Hydra-OS's own Python, config.json's `python`."""
    conf = common.config(root)
    want = conf.get("python") or ""
    if not want or not os.path.exists(want):   # the words for a missing Python, across the detail and the fix
        return line("python", False, "Part of Hydra-OS is missing from this Mac", REOPEN)
    here = os.path.realpath(sys.executable)
    if os.path.realpath(want) != here:
        return line("python", False, "running on another Python than Hydra-OS's own", REPAIR)
    v = sys.version_info
    return line("python", True, f"Python {v.major}.{v.minor}.{v.micro}")


def chosen(root, rec=None):
    """The declared sources the person chose, or None when no choice is recorded at all. With none recorded, no file
    ever read and workouts logged through Claude, it's none: that person has no iPhone and reads no file."""
    path = root / "yours" / "sources.json"
    if not path.exists():
        import days  # noqa: PLC0415
        read = rec is not None and (rec / "store" / "days.jsonl").exists()
        return set() if rec is not None and not read and days.logged(rec) else None
    import sources  # noqa: PLC0415 (only when there's a file to read)
    reads, _ = sources.chosen(root)
    return {e["id"] for e in reads}


def source_lines(rec, root, runs, now) -> list:
    picked = chosen(root, rec)
    out = []
    for s in common.MANIFEST.get("sources") or []:
        sid = s.get("id") if isinstance(s, dict) else None
        if not isinstance(sid, str):
            continue
        name = f"source {sid}"
        what = s.get("service") or ("a file of days" if s.get("kind") == "upload" else sid)
        if picked is not None and sid not in picked:
            out.append(line(name, True, "not chosen"))
            continue
        tried = [r for r in runs if isinstance(r.get("sources"), dict) and sid in r["sources"]]
        if not tried:
            fix = DROP if s.get("kind") == "upload" else CONNECT if picked is None else \
                f"It's read at the next run. Say yes when Claude offers to fill {common.TITLE} now."
            out.append(line(name, False, "never answered", fix))
            continue
        last = tried[-1]
        t = when(last["started_at"])
        if last["sources"][sid] is True and fresh_enough(t, now):
            out.append(line(name, True, f"answered {common.clock(t)}"))
        else:
            answered = [r for r in tried if r["sources"][sid] is True]
            since = f"no answer since {common.clock(when(answered[-1]['started_at']))}" if answered else "never answered"
            fix = DROP if s.get("kind") == "upload" else f"{common.TITLE} can't see {what}. Connect it in Claude."
            out.append(line(name, False, since, fix))
    return out


def schedule_line(root, runs, now) -> dict:
    doc = common.load_json(root / "hydra" / "health.json", None)
    entry = None
    if isinstance(doc, dict):
        entry = next((r for r in doc.get("runs") or [] if isinstance(r, dict) and r.get("app") == common.ID), None)
    if entry is None:
        return line("schedule", False, "Hydra-OS hasn't started it yet",
                    f"Hydra-OS starts {common.TITLE} once a day. If it hasn't by tomorrow, Repair, in Help, sets it up again.")
    state, said = entry.get("state"), str(entry.get("said") or "")
    at = str((common.MANIFEST.get("schedule") or {}).get("at") or "")
    scheduled = [r for r in runs if r.get("trigger") == "schedule"]
    if state == "running":
        return line("schedule", True, f"running now, daily at {at}")
    if state == "due" or (state == "ran" and not scheduled):
        return line("schedule", False, "no scheduled run yet", f"{common.TITLE} runs at {at} each day, by itself.")
    if state in ("missed", "failed", "waiting"):
        fix = {"missed": "Hydra-OS tries again by itself. If it keeps missing, Repair, in Help, finds why.",
               "failed": "It runs again tomorrow by itself. If it fails again, Repair, in Help, finds why.",
               "waiting": f"Do that in Claude, and {common.TITLE} runs again by itself."}[state]
        return line("schedule", False, said or f"the last run {state}", fix)
    if state == "ran" and fresh_enough(when(scheduled[-1]["started_at"]), now):
        return line("schedule", True, f"ran {common.clock(when(scheduled[-1]['started_at']))}, daily at {at}")
    return line("schedule", False, "no scheduled run in the last day", REPAIR)


def run_servers_ok(r, needed: set) -> str:
    """Why one run line breaks the servers rule, or ""."""
    servers = r.get("mcp_servers")
    if r.get("model") is False:
        sched = common.MANIFEST.get("schedule") or {}
        if not (sched.get("run") or sched.get("command")):
            return f"a run said it made no call, though {common.TITLE}'s schedule names no launcher"
        if servers != [] or any(k in r for k in MODEL_KEYS):
            return "a run that made no call listed a server or claimed a debug log"
        return ""
    if not isinstance(servers, list):
        return "a run recorded no servers"
    extra = [s for s in servers if s not in needed]
    if extra:
        return f"listed {len(extra)} server{'s' if len(extra) != 1 else ''} it doesn't need: " + ", ".join(sorted(map(str, extra)))
    if r.get("claude_ai_connectors") != "off":
        return "a run had claude.ai connectors on"
    if r.get("setting_sources") != "":
        return "a run let the person's own settings in"
    return ""


def servers_line(runs) -> dict:
    needed = set(common.MANIFEST.get("servers_needed") or [])
    if not runs:
        return line("servers", False, "no run yet", "It's checked after the first run.")
    looked = []
    for r in [runs[-1]] + [r for r in runs if r.get("trigger") == "schedule"][-2:]:   # each run once
        if all(r is not x for x in looked):
            looked.append(r)
    for r in looked:
        why = run_servers_ok(r, needed)
        if why:
            return line("servers", False, why, f"Start {common.TITLE}'s runs only with the servers it needs, and deny the rest by name.")
    calls = sum(1 for r in looked if r.get("model") is not False)
    listed = "listed no servers, none needed" if not needed else f"listed only the {len(needed)} it needs"
    return line("servers", True, f"{listed}; {calls} of {len(looked)} runs called Claude")


def synced(rec) -> bool:
    """Under iCloud Drive or a cloud folder, or in a Desktop or Documents that iCloud keeps (links resolved first)."""
    real = os.path.realpath(rec)
    if SYNCED.search(real):
        return True
    cloud = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
    for d in ("Desktop", "Documents"):
        local, icloud = os.path.expanduser("~/" + d), os.path.join(cloud, d)
        try:
            same = os.path.exists(icloud) and os.path.samefile(local, icloud)
        except OSError:
            same = False
        if same and (real + "/").startswith(os.path.realpath(local) + "/"):
            return True
    return False


def record_line(rec) -> dict:
    fix = f"Hydra-OS keeps {common.TITLE}'s folder in its own place. Repair, in Help, puts it back."
    if not rec.is_dir():
        return line("record", False, f"{common.TITLE}'s folder isn't there", fix)
    if synced(rec):
        return line("record", False, f"{common.TITLE}'s folder is in a folder that syncs to a cloud", fix)
    mode = os.stat(rec).st_mode & 0o777
    if mode != 0o700:
        return line("record", False, f"{common.TITLE}'s folder is mode {mode:o}, not 700", fix)
    if not os.access(rec, os.W_OK):
        return line("record", False, f"{common.TITLE}'s folder can't be written", fix)
    page, index = rec / "page", rec / "page" / "index.html"
    if page.is_dir() and os.stat(page).st_mode & 0o777 != 0o700:
        return line("record", False, "the page's folder isn't mode 700", fix)
    if index.exists() and os.stat(index).st_mode & 0o777 != 0o600:
        return line("record", False, "the page isn't mode 600", fix)
    return line("record", True, "")


def built_at(rec):
    try:
        text = (rec / "page" / "index.html").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = re.search(r'<meta name="built-at" content="([^"]+)"', text)
    return when(m.group(1)) if m else None


def written_at(path):
    try:
        return dt.datetime.fromtimestamp(os.stat(path).st_mtime).astimezone()
    except OSError:
        return None


def fresh_line(rec, runs) -> dict:
    fix = f"{common.TITLE}'s next run writes it again, by itself."
    page, status = built_at(rec), written_at(rec / "STATUS.md")
    if page is None or status is None:
        return line("fresh", False, "the page or STATUS.md is missing", fix)
    if not runs:
        return line("fresh", False, "no run yet", fix)
    start = when(runs[-1]["started_at"])
    if page < start:
        return line("fresh", False, "the page is older than the newest run", fix)
    if status < start:
        return line("fresh", False, "STATUS.md is older than the newest run", fix)
    return line("fresh", True, f"page and STATUS.md from the run of {common.clock(start)}")


def private_line(rec) -> dict:
    try:
        text = (rec / "STATUS.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return line("private", False, "STATUS.md can't be read", "It's written again at the next run.")
    found = privacy.check_text(text, privacy.private_terms(rec))
    return line("private", not found, f"{len(found)} finding{'s' if len(found) != 1 else ''}" if found else "states and counts only",
                "STATUS.md is written again at the next run. If it happens again, Repair, in Help, finds why.")


def replaces_lines(rec, root) -> list:
    """One for each item in the folder's own replaces.json. It passes once Hydra-OS's log of what's switched off,
    <root>/hydra/RETIRE.md, names it."""
    doc = common.load_json(rec / "replaces.json", None)
    try:
        retired = (root / "hydra" / "RETIRE.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        retired = ""
    out = []
    for item in (doc.get("items") or []) if isinstance(doc, dict) and doc.get("contract") == "replaces/v1" else []:
        rid = item.get("id") if isinstance(item, dict) else None
        if isinstance(rid, str) and re.fullmatch(r"[a-z0-9-]{1,40}", rid):
            off = re.search(rf"^- {re.escape(rid)}\b", retired, re.M) is not None
            out.append(line(f"replaces {rid}", off, "switched off, by Hydra-OS's log" if off else "still on",
                            "Hydra-OS switches it off at cutover, with your yes."))
    return out


def check(rec, now) -> list:
    root = common.root_of(rec)
    runs = runs_of(rec) if rec.is_dir() else []
    return ([installed(), python_line(root)] + source_lines(rec, root, runs, now)
            + [schedule_line(root, runs, now), servers_line(runs), record_line(rec), fresh_line(rec, runs),
               private_line(rec)] + replaces_lines(rec, root))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"Check {common.TITLE} against its contract and write doctor.json.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    now = common.now(a.now)
    lines = check(rec, now)
    for l in lines:
        print(f"PASS {l['name']}" + (f": {l['detail']}" if l["detail"] else "") if l["ok"]
              else f"FAIL {l['name']}: {l['detail']}. Fix: {l['fix']}")
    ok = all(l["ok"] for l in lines)
    writable = rec.is_dir() and os.access(rec, os.W_OK)
    if writable:
        page, status = built_at(rec), written_at(rec / "STATUS.md")
        common.write_json(rec / "doctor.json", {
            "contract": "doctor/v1", "pillar": common.ID, "plugin_version": common.plugin_version(),
            "checked_at": common.iso(now), "ok": ok, "lines": lines, "runs": runs_of(rec)[-10:],
            "servers_needed": list(common.MANIFEST.get("servers_needed") or []),
            "page_built_at": common.iso(page) if page else None, "status_written_at": common.iso(status) if status else None})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
