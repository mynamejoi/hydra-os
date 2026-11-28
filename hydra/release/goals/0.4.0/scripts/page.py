"""Goals' page, drawn by the main plugin's kit, with no model call and no request:

    python3 scripts/page.py [--record DIR] [--now ISO] [--run ISO|by-hand]

It writes page/index.html, page/summary.json and page/data/<name>.json in Goals' record, each whole or not at all,
and prints one line with a path and counts. Home's server runs it before serving the page, whenever a goal or any
app's progress is newer than the page; a save and the run call build() themselves.

- **What it shows,** top to bottom: "Home / Goals"; the two panes, your goals and one
  goal's detail with its one full plot; Claude asks; Connections; and the kit's footer with the privacy sentence.
- **Every goal is read the one way,** by the kit's kit.read_goals, as Home's
  Toward your goals reads them, so the two can't disagree.
- **It shows only what works:** Connections names the apps that are installed, and nothing else.
- **Everything on it is the kit's.** Its goals block is the kit's two panes (kit.goals_panes):
  every goal in a list, and beside it one goal's detail, picked in the page or by `?g=<id>`.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import checkin
import common
import goalsfile
import pages
import reading

# Claude asks' one line: each answer is saved with its goal at once, as the kit's ANSWER_KEPT says beside Undo
# The header's line by how the goals stand, and the one goal it names when one needs
# the person: the page opens on that goal. NEEDS is the order the header names them in.
NONE_LINE = "What you're working toward, and how each one is going."
FINE_LINE = "Everything is on pace."
NEEDS = ("missed", "behind", "new", "unknown")
# "What counts your goals": one row each, a colon after the name, no paid pages.
COUNTS_TITLE = "What counts your goals"
ASKS_NOTE = "One goal a day. Your answer updates it at once, with Undo."  # Claude asks, while the check-in shows
YOU = {"name": "You", "what": "the numbers you tell Claude, for goals kept by hand"}


class NoKit(Exception):
    """The main plugin's kit isn't in reach, so there's nothing to draw the page with."""


def next_words(move) -> str:
    """A next move in the header's words, its app's suggestion without "I'd" or a full stop: "I'd swim Tuesday or
    Thursday at 6." reads "swim Tuesday or Thursday at 6"."""
    text = " ".join(str((move or {}).get("text") or "").split()).rstrip(".")
    if text.startswith("I'd "):
        text = text[4:]
    return text[:1].lower() + text[1:]


def needs_of(root, r: dict) -> str:
    """What a goal that isn't counted yet needs from the person, as the header's next move: "" when it needs nothing of
    them, as when its app has its source and counts it at its next run."""
    if r["app"] in (None, common.ID):  # kept by hand, or counted by no page: only they know where it stands
        return "tell Claude where it stands"
    if not r["installed"]:  # it names a page that isn't here, which only they can choose to add
        return f"add {r.get('app_title') or 'its page'} from the Shop"
    if not (r["target"] is not None and r["by"] and r["start"]):
        return "tell Claude its target and date"
    info = reading.apps_of(root).get(r["app"]) or {}
    if info.get("source"):
        return ""
    reg = common.load_json(pathlib.Path(root) / "hydra" / "registry.json", None)
    entry = next((a for a in (reg or {}).get("apps") or [] if isinstance(a, dict) and a.get("id") == r["app"]), {})
    home = entry.get("home") if isinstance(entry.get("home"), dict) else {}
    needs = " ".join(str(home.get("needs") or "").split())
    return (needs[:1].lower() + needs[1:]).rstrip(".")


def headline(root, readings: list) -> tuple:
    """The header's line by how the goals in hand stand, and the id of the goal it names, or
    None: the first that needs the person, missed, then behind, then not counted yet, then can't be told, each in the
    file's order; else "Everything is on pace." once one has a pace and every pace is on it; else the line for none."""
    hand = [r for r in readings if r["in_hand"]]
    for state in NEEDS:
        for r in hand:
            if r["state"] != state:
                continue
            name = r["text"]
            if state == "missed":
                return f"{name} is past its date. Next: set a new date, or set it aside.", r["id"]
            if state == "behind":
                nxt = next_words(r.get("move"))
                return f"{name} is behind." + (f" Next: {nxt}." if nxt else ""), r["id"]
            if state == "unknown":
                return f"{name} can't be told yet.", r["id"]
            nxt = needs_of(root, r)
            if nxt:
                return f"{name} isn't counted yet. Next: {nxt}.", r["id"]
    if any(r["state"] in ("on", "ahead") for r in hand):
        return FINE_LINE, None
    return NONE_LINE, None


def datasets(root, now=None) -> dict:
    """What the kit's blocks need beyond the goals themselves: the header's line (the first visit's tip is column.json's,
    which the kit draws from there), the goal the page opens on, Claude asks hidden before any goal (Goals asks
    nothing, so the kit's own line shows), and "What counts your goals", its `title` and `rows`, which the kit draws
    in place of Connections: each installed app that counts goals, with the last day its data reaches and the way to
    add more, then "You" while a goal is kept by hand."""
    installed = reading.apps_of(root)
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        doc = {"goals": []}
    kept = any(g.get("status") == "active" and (g.get("measured_by") or {}).get("app") == common.ID for g in doc["goals"])
    out = {"header": {}, "questions": {}}
    if not doc["goals"]:  # Claude asks isn't drawn before any goal
        out["questions"]["hidden"] = True
    else:  # what the day's check-in does, under it
        out["questions"]["note"] = ASKS_NOTE
    rows = []  # what counts the goals, one row each
    for page_ in pages.installed(root):  # each installed page's own words for what it counts, its `fits.what`
        app_id, what, info = page_["id"], page_["fits"]["what"], installed.get(page_["id"])
        if not (what and info):
            continue
        row = {"app": app_id, "what": what.rstrip(".")}
        say = common.load_json(info["record"] / "say.json", None) if info.get("record") else None
        to = common.day((say or {}).get("data_to") or "") if isinstance(say, dict) else None
        if to is not None:
            row["counted_to"] = to.isoformat()
        words = ("Add a fresh export" if to is not None else info.get("needs_line")) if info.get("uploads_only") else ""
        if words:  # an export is a snapshot, so a fresher one is always the way in; before any, the app's needs line
            row["do"] = {"words": words, "link": f"{app_id}#drop"}
        rows.append(row)
    if kept:
        rows.append(dict(YOU))
    out["connections"] = {"title": COUNTS_TITLE, "rows": rows}
    if now is not None:
        import build  # the run's own reading of every goal, through the kit's kit.read_goals
        try:
            got = build.readings(root, now)["goals"]
        except goalsfile.Broken:
            got = None
        line, open_on = headline(root, got) if got is not None else (NONE_LINE, None)
        out["header"]["line"] = line
        if open_on:
            out["goals"] = {"selected": open_on}
    return out


def build(root, record, now, run: str = "by-hand") -> dict:
    """Builds the page into the record, through the kit's own build: {"path", "blocks", "bytes"}, a path and counts,
    never a goal's words."""
    kit = common.load_kit(root)
    if kit is None:
        raise NoKit("Hydra-OS's own files aren't where Goals can find them, so its page can't be drawn.")
    data, words = datasets(root, now), {}
    try:
        doc, _ = goalsfile.load(root)
    except goalsfile.Broken:
        doc = None
    if doc is not None and now is not None:  # each goal's newest check-in in its detail, and today's in Claude asks
        said = checkin.said(doc, record, now.date())
        if said:
            data.setdefault("goals", {})["said"] = said
        words = checkin.today_words(doc, record, now)
    return kit.build(str(common.PLUGIN), str(record), root=str(root), now=now, run=run, data=data, answers=words)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build Goals' page from the goals and each page's progress.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    ap.add_argument("--run", default="by-hand")
    a = ap.parse_args(argv)
    try:
        root = common.root_of(a.record)
        now = common.now(a.now)
    except (common.NotSetUp, ValueError) as e:
        print(f"page: not written: {e}", file=sys.stderr)
        return 1
    record = common.record_of(root, a.record)
    if not record.is_dir():
        print("page: not written: Goals has no folder of its own yet", file=sys.stderr)
        return 1
    run = a.run if a.run == "by-hand" or common.parse_time(a.run) else "by-hand"
    try:
        got = build(root, record, now, run)
    except NoKit as e:
        print(f"page: not written: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001  (its words might hold a goal's, so only its kind)
        print(f"page: not written: {type(e).__name__}", file=sys.stderr)
        return 1
    home = str(pathlib.Path.home())
    path = got["path"]
    path = "~" + path[len(home):] if path.startswith(home + "/") else path
    print(f"page: wrote {path} ({got['blocks']} blocks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
