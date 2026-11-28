"""Research's doctor: one line per requirement, in
Hydra-OS's order for every page, then doctor.json in Research's folder. It changes nothing else, calls no model, sends nothing and
needs no network.

    python3 scripts/doctor.py [--record DIR] [--now ISO]

Lines, in order: installed, python, one source line for each source column.json declares, schedule, servers, record,
fresh, private, then store, which names any store file a newer version of Research wrote and this one keeps as it is.
Exit 0 when every line passes, 1 when any fails. Details and fixes hold states, counts and times only.

- Each source passes when the newest run read it, within a day. For the notes inbox that means every note dropped on
  the page was read; no note at all is fine. A source that wasn't read says since when, or that a note couldn't be read.
- installed passes from a release export, by its release.json. The doctor starts no other program.
- The schedule line reads Hydra-OS's own <root>/hydra/health.json, this app's entry.
- The servers line says what a run that made no call should: Research's run calls no Claude and lists no
  server. Its searches are the morning review's.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

import common
import privacy
import store

INTERVAL_HOURS = 24
GRACE_HOURS = 2
SYNCED = re.compile(r"/Library/(Mobile Documents|CloudStorage)/|/(Dropbox|Google Drive|OneDrive|Box)(/|$)", re.I)
MODEL_KEYS = ("mcp_log", "claude_ai_connectors", "setting_sources")
REPAIR = "Say 'repair Hydra-OS' to Claude."
REOPEN = "Open Hydra-OS again to put it back."


def line(name, ok, detail="", fix=""):
    """One line. A detail is a phrase, never ending in a full stop, so a FAIL reads "<detail>. Fix: <fix>"."""
    return {"name": name, "ok": bool(ok), "detail": str(detail).strip().rstrip("."), "fix": "" if ok else (fix or REPAIR)}


def when(s):
    return common.parse_time(s) if isinstance(s, str) else None


def clock(t) -> str:
    t = t.astimezone()
    return f"{t:%a %b} {t.day}, {t:%H:%M}"


def runs_of(rec) -> list:
    rows = [r for r in common.read_jsonl(rec / "runs.jsonl") if when(r.get("started_at"))]
    return sorted(rows, key=lambda r: when(r["started_at"]))


def fresh_enough(t, now) -> bool:
    return t is not None and now - t <= dt.timedelta(hours=INTERVAL_HOURS + GRACE_HOURS)


def config(root) -> dict:
    c = common.load_json(root / "hydra" / "config.json", {})
    return c if isinstance(c, dict) else {}


def installed() -> dict:
    """From a release export: the plugin folder's release.json, which only the release writes, names this plugin and
    its version. The release itself ran strict validation before it wrote that file, so the doctor starts nothing."""
    rel = common.load_json(common.ROOT / "release.json", None)
    version = common.plugin_version()
    if not (isinstance(rel, dict) and rel.get("plugin") == common.ID and rel.get("version") == version):
        return line("installed", False, "running from a working folder, not a release",
                    f"Install the newest release of {common.TITLE}, as its SETUP.md says.")
    return line("installed", True, f"release {version}")


def python_line(root) -> dict:
    want = os.path.expanduser(str(config(root).get("python") or ""))
    if not want or not os.path.exists(want):
        return line("python", False, "Part of Hydra-OS is missing from this Mac", REOPEN)
    if os.path.realpath(want) != os.path.realpath(sys.executable):
        return line("python", False, "running on another Python than Hydra-OS's own", REPAIR)
    v = sys.version_info
    return line("python", True, f"Python {v.major}.{v.minor}.{v.micro}")


def source_lines(rec, runs, now) -> list:
    out = []
    for s in common.MANIFEST.get("sources") or []:
        sid = s.get("id") if isinstance(s, dict) else None
        if not isinstance(sid, str):
            continue
        name = f"source {sid}"
        upload = s.get("kind") == "upload"   # the notes inbox: each run reads every note dropped on the page
        tried = [r for r in runs if isinstance(r.get("sources"), dict) and sid in r["sources"]]
        if not tried:
            out.append(line(name, False, "never read", f"It's read at {common.TITLE}'s next run, each morning."))
            continue
        last = tried[-1]
        t = when(last["started_at"])
        if last["sources"][sid] is True and fresh_enough(t, now):
            n = len(store.notes(rec))
            out.append(line(name, True, (f"{n} note{'' if n == 1 else 's'} kept" if n else "no note yet, and none needed")
                            if upload else f"read {clock(t)}"))
        elif upload and last["sources"][sid] is not True:
            out.append(line(name, False, "a note dropped on the page couldn't be read on the newest run",
                            "Drop it again as a .md or .txt file, or tell Claude."))
        else:
            read = [r for r in tried if r["sources"][sid] is True]
            since = f"not read since {clock(when(read[-1]['started_at']))}" if read else "never read"
            out.append(line(name, False, since, f"{common.TITLE} reads it at each morning's run. Check Hydra-OS is running."
                            if upload else "It's a public page, read again each morning. Check this Mac is online."))
    return out


def schedule_line(root, runs, now) -> dict:
    doc = common.load_json(root / "hydra" / "health.json", None)
    entry = None
    if isinstance(doc, dict):
        entry = next((r for r in doc.get("runs") or [] if isinstance(r, dict) and r.get("app") == common.ID), None)
    if entry is None:
        return line("schedule", False, "the tick hasn't seen this app yet",
                    f"Hydra-OS starts {common.TITLE} once a day. Make sure it's set up and running, or say 'repair Hydra-OS' to Claude.")
    state, said = entry.get("state"), str(entry.get("said") or "")
    scheduled = [r for r in runs if r.get("trigger") == "schedule"]
    if state == "running":
        return line("schedule", True, f"running now, daily at {common.AT}")
    if state == "due" or (state == "ran" and not scheduled):
        return line("schedule", False, "no scheduled run yet", f"{common.TITLE} runs at {common.AT} each day. Nothing to do but wait.")
    if state in ("missed", "failed", "waiting"):
        fix = {"missed": "Hydra-OS tries again by itself. If it keeps missing, say 'repair Hydra-OS' to Claude.",
               "failed": "It runs again tomorrow. If it fails again, say 'repair Hydra-OS' to Claude.",
               "waiting": f"Do that in Claude, and {common.TITLE} runs again by itself."}[state]
        return line("schedule", False, said or f"the last run {state}", fix)
    if state == "ran" and fresh_enough(when(scheduled[-1]["started_at"]), now):
        return line("schedule", True, f"ran {clock(when(scheduled[-1]['started_at']))}, daily at {common.AT}")
    return line("schedule", False, "no scheduled run in the last day", REPAIR)


def servers_line(runs) -> dict:
    if not runs:
        return line("servers", False, "no run yet", "It's checked after the first run.")
    looked = []
    for r in [runs[-1]] + [r for r in runs if r.get("trigger") == "schedule"][-2:]:
        if all(r is not x for x in looked):
            looked.append(r)
    for r in looked:
        if r.get("model") is not False or r.get("mcp_servers") != [] or any(k in r for k in MODEL_KEYS):
            return line("servers", False, "a run called Claude or listed a server",
                        f"{common.TITLE}'s run calls no Claude; its searches are the morning review's.")
    return line("servers", True, f"listed no servers, none needed; 0 of {len(looked)} runs called Claude")


def synced(rec) -> bool:
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
    fix = f"Hydra-OS keeps {common.TITLE}'s folder in its own place. Say 'repair Hydra-OS' to Claude."
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
    fix = f"Ask Claude to run {common.TITLE} now, or wait for its next run."
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
    return line("fresh", True, f"page and STATUS.md from the run of {clock(start)}")


def private_line(rec) -> dict:
    try:
        text = (rec / "STATUS.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return line("private", False, "STATUS.md can't be read", "It's written again at the next run.")
    found = privacy.check_text(text, privacy.markers(rec))
    return line("private", not found, f"{len(found)} finding{'s' if len(found) != 1 else ''}" if found else "states and counts only",
                "STATUS.md is written again at the next run. If it happens again, tell Claude.")


def store_line(rec) -> dict:
    newer = store.newer(rec)
    return line("store", not newer, f"{len(newer)} file{'s' if len(newer) != 1 else ''} from a newer version, kept as {'they are' if len(newer) != 1 else 'it is'}"
                if newer else "every file this version's", f"Update {common.TITLE} to the newest version, from the Shop.")


def check(rec, now) -> list:
    root = common.root_of(rec)
    runs = runs_of(rec) if rec.is_dir() else []
    return ([installed(), python_line(root)] + source_lines(rec, runs, now)
            + [schedule_line(root, runs, now), servers_line(runs), record_line(rec), fresh_line(rec, runs),
               private_line(rec), store_line(rec)])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"Check what {common.TITLE} needs to run, and write doctor.json.")
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
    if rec.is_dir() and os.access(rec, os.W_OK):
        page, status = built_at(rec), written_at(rec / "STATUS.md")
        common.write_json(rec / "doctor.json", {
            "contract": "doctor/v1", "pillar": common.ID, "plugin_version": common.plugin_version(),
            "checked_at": common.iso(now), "ok": ok, "lines": lines, "runs": runs_of(rec)[-10:],
            "servers_needed": list(common.MANIFEST.get("servers_needed") or []),
            "page_built_at": common.iso(page) if page else None, "status_written_at": common.iso(status) if status else None})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
