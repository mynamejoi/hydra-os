"""Hydra-OS's kit, the Python side: the one set of parts every page is drawn with.

An app's scripts/page.py works its own datasets out, then hands them here. The kit draws the page from the app's
stock layout, writes page/index.html and page/summary.json, and holds the one reading of a goal that Goals, Home
and every app's band share. Each part's docstring below says what its dataset looks like.

Python 3.9, standard library only. It makes no model call and no request, and reads only the files it's handed.
"""
import calendar as _calendar
import datetime as _dt
import html as _html
import json
import math
import os
import re
import tempfile

KIT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(KIT, "icons.json"), encoding="utf-8") as _f:
    ICONS = json.load(_f)

# Each app's symbol, in the rail's order. Its colour is the stylesheet's own pair, by the app's id.
APPS = {"goals": "target", "health": "heart", "finance": "wallet", "network": "users", "building": "hammer",
        "content": "video", "research": "scope", "learning": "scope", "dreams": "moon"}
# A page whose id isn't its colour pair's name wears that pair: Research keeps the id learning, in research's colours.
PAIR = {"learning": "research"}
PRIVACY = ("Your records stay as files on your Mac, and there's no server of ours. "
           "Claude reads what each page uses, under your own account.")
POLICY = ("default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self'; "
          "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
TYPES = ("header", "goals", "today", "suggestions", "chart", "note", "list", "table", "questions", "connections")
ROWS_MOST = 20  # a list or a table draws at most this many rows; its caption says how many more
ID = re.compile(r"[A-Za-z0-9._:][A-Za-z0-9._:-]{0,63}")  # an action's id field
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
FIXED = ("header", "goals", "questions", "connections")
WIDTHS = {"full": 1, "half": 2, "third": 3}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
PACE_WORDS = {"behind": "Behind", "on": "On pace", "ahead": "Ahead"}
SUMMARY_MAX = 24 * 1024
GOAL_EXAMPLES = ("Run a 10K by spring", "Save $5,000 for a trip", "Ship my side project")
# The name of an app that isn't installed, as the Goals app's list has it: Wellbeing for health, and the id with a
# capital for the others.
LISTED = {"health": "Wellbeing"}
NO_PLOT = "A goal's plot draws once it has a target, a date and its first counted day."


class KitError(ValueError):
    """A layout or a dataset the kit can't draw. Its message says which block, in plain words."""


# ---------------------------------------------------------------------------------------------------------------
# Small things every part uses

def esc(text):
    """Text made safe to put in a page, in an element or in an attribute."""
    return _html.escape("" if text is None else str(text), quote=False).replace('"', "&quot;")


def icon(name, cls="ic"):
    """One Tabler outline symbol, drawn at the size of the text it sits with."""
    paths = ICONS.get(name) or ICONS["apps"]
    return '<svg class="%s" viewBox="0 0 24 24" aria-hidden="true">%s</svg>' % (cls, "".join('<path d="%s"/>' % p for p in paths))


def app_icon(app_id, registry_icon=None):
    """The symbol's name for an app: the kit's own (APPS), else the registry's when the kit has it."""
    return APPS.get(app_id) or (registry_icon if registry_icon in ICONS else "apps")


def tint(app_id, accent=None):
    """(class, style) that set --c to an app's colour: its approved pair, else its accent number as a hue."""
    if app_id in APPS:
        return "", "--c:var(--%s)" % PAIR.get(app_id, app_id)
    try:
        return "hx", "--hx:%d" % (int(accent) % 360)
    except (TypeError, ValueError):
        return "", "--c:var(--ink)"


def _attrs(cls="", style="", **more):
    out = ""
    if cls:
        out += ' class="%s"' % esc(cls)
    if style:
        out += ' style="%s"' % esc(style)
    for key, value in more.items():
        if value is None or value is False:
            continue
        name = key.rstrip("_").replace("_", "-")
        out += " %s" % name if value is True else ' %s="%s"' % (name, esc(value))
    return out


def day(text):
    """A YYYY-MM-DD day, or None when it isn't one."""
    try:
        return _dt.date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


def moment(text):
    """An ISO 8601 moment with its offset, or None."""
    try:
        got = _dt.datetime.fromisoformat(str(text)) if text else None
    except ValueError:
        return None
    return got if got is not None and got.tzinfo is not None else None


def short_day(d):
    """Jun 3"""
    return "%s %d" % (MONTHS[d.month - 1], d.day)


def day_words(d, today):
    """A day as a caption reads it: "Sep 20" in this year, and "Apr 2026" in another."""
    return short_day(d) if d.year == today.year else "%s %d" % (MONTHS[d.month - 1], d.year)


def weekday_day(d):
    """Mon Sep 21"""
    return "%s %s" % (WEEKDAYS[d.weekday()], short_day(d))


def clock(t):
    """7:40 am"""
    return "%d:%02d %s" % (t.hour % 12 or 12, t.minute, "am" if t.hour < 12 else "pm")


def num(x):
    """A figure in words: thousands grouped, and a whole number with no decimals."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return ""
    if float(x).is_integer():
        return "{:,}".format(int(x))
    return "{:,.2f}".format(x).rstrip("0").rstrip(".")


def singular(unit):
    """A unit's first word for exactly one: "swims" is "swim", "stories" "story",
    "classes" "class", "people" "person", and "km" stays "km"."""
    first, sep, rest = unit.partition(" ")
    low = first.lower()
    if low == "people":
        one = first[:2] + "rson"
    elif low.endswith("ies") and len(low) > 3:
        one = first[:-3] + ("Y" if first[-3:].isupper() else "y")
    elif low.endswith(("sses", "shes", "ches", "xes")):
        one = first[:-2]
    elif low.endswith("s") and not low.endswith("ss") and len(low) > 1:
        one = first[:-1]
    else:
        one = first
    return one + sep + rest


def amount(x, unit):
    """A figure with its unit: a word after it ("17 swims", "1 swim"), or a sign before it ("$11,500")."""
    unit = (unit or "").strip()
    if not unit:
        return num(x)
    if any(ch.isalnum() for ch in unit):
        return "%s %s" % (num(x), singular(unit) if x == 1 else unit)
    return "%s%s%s" % ("-" if x < 0 else "", unit, num(abs(x)))


def _clamp(x):
    return max(0.0, min(1.0, x))


def _pc(x):
    return int(round(x * 100))


def read_json(path, default=None):
    """A JSON file's value, or `default` when it's missing or can't be read. A missing file is never an error."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_whole(path, text, mode=0o600):
    """Write a file whole or not at all: a temporary file in the same folder, then a rename."""
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".kit-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------------------------------------------
# Reading a goal: the one way every page reads goals.json beside a measuring app's say.json

def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _next_month(d):
    """The same day of the next month, or that month's last day when it's shorter."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return _dt.date(y, m, min(d.day, _calendar.monthrange(y, m)[1]))


def first_window(goal, on, by):
    """How long a pace needs before it means anything: one of the rate's day, week or month,
    else 7 days, and never more than half the days from its start to its due day."""
    rate = goal.get("rate") or {}
    per = rate.get("per") if _is_number(rate.get("n")) else None
    days = 1 if per == "day" else (_next_month(on) - on).days if per == "month" else 7
    return min(days, (by - on).days / 2)


def goal_line(goal, today):
    """The bare target line, "17 swims by Aug 1, at 2 a week", or "" for a goal that isn't read yet."""
    start, by = goal.get("start") or {}, day(goal.get("by"))
    if not (_is_number(goal.get("target")) and by and _is_number(start.get("value")) and day(start.get("on"))):
        return ""
    line = "%s by %s" % (amount(goal["target"], goal.get("unit")), day_words(by, today))
    rate = goal.get("rate") or {}
    if _is_number(rate.get("n")) and rate.get("per") in ("day", "week", "month"):
        line += ", at %s a %s" % (num(rate["n"]), rate["per"])
    return line


def _who(goal, read, app):
    """Who counts a goal that isn't counted yet, in one line: the first row that holds. Count, not measure, and a
    page, not an app, as Goals says them."""
    if not app:
        return "No page counts this yet."
    title = app["title"]
    if not app.get("installed"):
        return "Add %s to count this." % title
    if not read:
        return "%s counts it once it has a target and a date." % title
    needs = (app.get("needs") or "").strip()
    if needs and not app.get("has_source"):  # a file dropped on its page is "in"; anything else is "connected"
        thing = needs.split(" ", 1)[1] if " " in needs else needs
        return "%s counts it once %s %s %s." % (title, thing, "are" if thing.endswith("s") else "is", "in" if app.get("uploads_only") else "connected")
    if app.get("ran") and not app.get("measures"):
        return "%s doesn't count goals yet." % title
    return "%s starts counting it tonight." % title


def read_goal(goal, entry, app, today, stale=False, move=None, quiet=False):
    """One goal and its measuring app's say.json entry in, one reading out.

    goal   a goal from yours/goals.json.
    entry  that goal's entry in the measuring app's say.json `goals`, or None when there's none.
    app    None when no app measures it, else {"id", "title", "installed", "needs", "has_source", "ran", "measures",
           "accent", "uploads_only"}: `ran` says its say.json exists, `measures` that it holds a `goals` list, and
           `uploads_only` that every source its column.json declares is an upload, as Goals' reading has it.
    today  the day the page is built.
    stale  the app's say.json is past its stale_after.
    move   the app's first suggestion that names this goal, {"text", "why"}, or None.
    quiet  they said no to the morning review (review_off), so where a move would show and there's none, the reading's
           `review_off` says the line goes there.
    """
    start, target, by = goal.get("start") or {}, goal.get("target"), day(goal.get("by"))
    on = day(start.get("on"))
    read = bool(_is_number(target) and by and on and _is_number(start.get("value")) and target != start["value"] and by > on)
    line = goal_line(goal, today) if read else ""
    value = entry.get("value") if entry else None
    # The plan mark and the first window run to the day the measuring app's data runs to, its entry's `to`, never past
    # today, so a goal doesn't turn Behind on days no data has reached.
    upto = day(entry.get("to")) if entry else None
    at = upto if upto and upto < today else today
    share = plan = None
    if read and _is_number(value):
        share = _clamp((value - start["value"]) / (target - start["value"]))
        plan = _clamp((at - on).days / (by - on).days)
    step, do = "", None  # the state's own next step, said after its words, and its page action
    drop = {"words": "", "link": "%s#drop" % app["id"]} if app and app.get("uploads_only") else None
    status, ended = goal.get("status"), day(goal.get("ended"))
    lands = day(entry.get("lands")) if entry else None
    reaches = entry.get("reaches") if entry else None
    pace = entry.get("pace") if entry else None
    measured = who = figure = ""
    if status == "aside":
        state, word, caption = "aside", "Set aside", day_words(ended, today) if ended else ""
    elif status == "done" or share == 1:
        at = ended or lands
        state, word, caption = "done", "Done", "Reached %s" % day_words(at, today) if at else ""
        step = "Tell Claude what's next."
    elif not read or not app or not app.get("installed") or entry is None:
        state, word = "new", ""
        if read:
            measured = "Counted as " + line
        else:  # its row says it, and its caption adds what it still needs
            measured = "Not counted yet"
        who = _who(goal, read, app)
        caption = "%s. %s" % (measured, who)
        needs = ((app or {}).get("needs") or "").strip()
        if not app:  # nothing here counts it: Goals keeps such a goal by hand, at once
            caption = "Not counted yet."
        elif read and app.get("installed") and drop and needs and not app.get("has_source"):  # no data in yet
            caption, step = "Not counted yet.", "%s needs %s." % (app["title"], needs.split(" ", 1)[1] if " " in needs else needs)
            do = dict(drop, words=needs)
    elif today > by:
        state, word, caption = "missed", "Missed", "Its date has passed."  # its two buttons, on the goal
    elif pace not in PACE_WORDS or stale:
        as_of = moment(entry.get("as_of"))
        state, word, caption = "unknown", "Can't tell yet", "As of " + short_day(as_of.date()) if as_of else ""
    elif (at - on).days < first_window(goal, on, by):  # its first window, to the data's day: a pace this soon can't mean much
        since = {0: "today", 1: "yesterday", -1: "tomorrow"}.get((today - on).days) or day_words(on, today)
        first = on + _dt.timedelta(days=math.ceil(first_window(goal, on, by)))
        state, word, caption = "started", "Not started yet" if on > today else "Just started", "First update " + weekday_day(first)
    else:
        state, word = pace, PACE_WORDS[pace]
        if lands:
            caption = "Lands %s, due %s" % (day_words(lands, today), day_words(by, today))
        elif _is_number(reaches):
            caption = "Reaches %d%% by %s" % (_pc(_clamp((reaches - start["value"]) / (target - start["value"]))), day_words(by, today))
        else:
            caption = ""
    # An export that ends before yesterday: the reading says where it's counted to, and offers a fresh one.
    if upto and (today - upto).days > 1 and state in ("behind", "on", "ahead", "unknown", "started"):
        caption = "Counted to %s." % weekday_day(upto)
        do = dict(drop, words="Add a fresh export") if drop else None
    if read and _is_number(value):
        unit = (goal.get("unit") or "").strip()
        if unit and not any(ch.isalnum() for ch in unit):
            figure = "%s of %s" % (amount(value, unit), amount(target, unit))
        else:
            figure = ("%s of %s %s" % (num(value), num(target), singular(unit) if target == 1 else unit)).strip()
    shown = state not in ("aside", "done", "new")
    done_on = ended or lands
    in_hand = state not in ("aside", "done") or (state == "done" and (done_on is None or 0 <= (today - done_on).days <= 7))
    if status != "active" and state != "done":
        in_hand = False
    return {
        "id": goal.get("id", ""), "text": goal.get("text", ""), "why": goal.get("why", ""), "status": goal.get("status"),
        "app": app["id"] if app else None, "app_title": app["title"] if app else "", "accent": app.get("accent") if app else None,
        "installed": bool(app and app.get("installed")),
        "state": state, "word": word, "caption": caption, "share": share if shown or state == "done" else None,
        "plan": plan if shown or state == "done" else None, "figure": figure, "line": line, "measured": measured, "who": who,
        "in_hand": in_hand, "move": move if shown and not stale and state not in ("on", "ahead") else None,
        "review_off": bool(quiet and not move and shown and not stale and state not in ("on", "ahead")),
        "step": step, "do": do, "counted_to": upto.isoformat() if upto else None,
        "start": {"value": start.get("value"), "on": start.get("on")} if read else None, "target": target if read else None,
        "by": goal.get("by") if read else None, "unit": goal.get("unit", ""),
        "value": value if _is_number(value) else None, "lands": entry.get("lands") if entry else None,
        "reaches": reaches if _is_number(reaches) else None,
        "points": (entry.get("points") or []) if entry else [], "changes": (entry.get("changes") or []) if entry else [],
        "counting": (entry.get("counting") or "") if entry else "", "why_pace": (entry.get("why") or "") if entry else "",
        "as_of": (entry.get("as_of") or "") if entry else "", "then": _then(entry, goal.get("id", "")),
    }


def _then(entry, gid):
    """One more move of Goals' own that the measuring page's entry offers for this goal, as "Count it in nights":
    {"words", "act", "fields"}, its fields naming this goal, or None."""
    t = entry.get("then") if isinstance(entry, dict) else None
    if not isinstance(t, dict):
        return None
    words, name, fields = t.get("words"), t.get("act"), t.get("fields")
    if (not isinstance(words, str) or not 0 < len(words.strip()) <= 40 or not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z-]{0,23}", name)
            or not isinstance(fields, dict) or fields.get("goal") != gid
            or not all(isinstance(k, str) and isinstance(v, (str, int, float)) and not isinstance(v, bool) for k, v in fields.items())):
        return None
    return {"words": words.strip(), "act": name, "fields": fields}


def tally(readings):
    """"2 of 4 on pace, 2 new", or "" when there's none to count."""
    hand = [r for r in readings if r["in_hand"]]
    counted = [r for r in hand if r["state"] in ("behind", "on", "ahead", "unknown", "missed")]
    if not counted:
        return ""
    new = sum(1 for r in hand if r["state"] in ("new", "started"))
    words = "%d of %d on pace" % (sum(1 for r in counted if r["state"] in ("on", "ahead")), len(counted))
    return words + (", %d new" % new if new else "")


def registry_apps(root):
    """The installed apps, by id, from <root>/hydra/registry.json. {} when there's no registry."""
    reg = read_json(os.path.join(root, "hydra", "registry.json"), {})
    apps = reg.get("apps") if isinstance(reg, dict) else None
    return {a["id"]: a for a in apps or [] if isinstance(a, dict) and isinstance(a.get("id"), str)}


def record_of(root, app_id, apps=None):
    """An app's record folder: the registry's, else <root>/<id>."""
    entry = (apps if apps is not None else registry_apps(root)).get(app_id) or {}
    rec = entry.get("record")
    if isinstance(rec, str) and rec:
        rec = rec.replace("<root>", root, 1)
        return os.path.expanduser(rec)
    return os.path.join(root, app_id)


def sources_of(root):
    """yours/sources.json's entries, each {"app", "id", "source", "via", "account", "reads", "since"}."""
    got = read_json(os.path.join(root, "yours", "sources.json"), {})
    if isinstance(got, dict) and isinstance(got.get("sources"), list):
        return [s for s in got["sources"] if isinstance(s, dict) and isinstance(s.get("app"), str)]
    if isinstance(got, dict) and "contract" not in got:  # the connect kit's first shape, keyed by app
        return [dict(s, app=app) for app, rows in got.items() if isinstance(rows, list) for s in rows if isinstance(s, dict)]
    return []


# Where a suggestion would show while they said no to the morning review: yours/settings.json's "review" is false.
# Missing (not asked yet) or true changes nothing.
REVIEW_OFF = "Suggestions start with the morning review. It uses some of your Claude plan each morning."  # what, then the cost
PAGE_REMOVE_ASK = "Remove %s? Its records go to the Trash, so you can take them back."  # asked on the page, in Remove's place
REVIEW_ON = '<button type="button" class="alt" data-do="review" data-fields=\'{"on": true}\' data-then="hide">Turn on</button>'  # then how: on the page


def review_off(settings):
    """They said no to the morning review, and haven't turned suggestions off."""
    return settings.get("review") is False and settings.get("suggestions") is not False


def settings_of(root):
    """yours/settings.json, with its defaults for whatever is missing."""
    got = read_json(os.path.join(root, "yours", "settings.json"), {})
    got = got if isinstance(got, dict) else {}
    look = got.get("appearance")
    seen, tips = got.get("walkthroughs"), got.get("tips")
    return {"appearance": look if look in ("sun", "light", "dark", "system") else "sun",
            "phone": got.get("phone") is True, "suggestions": got.get("suggestions") is not False,
            "review": got.get("review") if isinstance(got.get("review"), bool) else None,
            "walkthroughs": [w for w in seen if isinstance(w, str)] if isinstance(seen, list) else [],
            "tips": {k: [i for i in v if isinstance(i, str)] for k, v in tips.items() if isinstance(k, str) and isinstance(v, list)} if isinstance(tips, dict) else {}}


def read_goals(root, today=None, app=None, now=None):
    """Every goal, read the one way, for a page built today.

    Returns {"goals": the goals in hand, in the file's order; "record": the rest, done and set aside, which only
    Goals' page shows; "tally": "2 of 4 on pace, 2 new" or ""}. `app` keeps only the goals that app measures, for the
    band on its page. `now` is the build's moment, for a say.json past its stale_after; `today` is its day.
    """
    now = now or _dt.datetime.now().astimezone()
    today = today or now.date()
    file = read_json(os.path.join(root, "yours", "goals.json"), {})
    goals = [g for g in (file.get("goals") if isinstance(file, dict) else None) or [] if isinstance(g, dict)]
    apps, sources, settings = registry_apps(root), sources_of(root), settings_of(root)
    says, columns, out = {}, {}, []
    for goal in goals:
        by = goal.get("measured_by")
        app_id = by.get("app") if isinstance(by, dict) else None
        if app is not None and app_id != app:
            continue
        info = entry = move = None
        stale = quiet = False
        if isinstance(app_id, str) and app_id:
            reg = apps.get(app_id)
            if app_id not in says:
                says[app_id] = read_json(os.path.join(record_of(root, app_id, apps), "say.json")) if reg else None
                columns[app_id] = read_json(os.path.join(reg["root"], "column.json"), {}) if reg and isinstance(reg.get("root"), str) else {}
            say = says[app_id] if isinstance(says[app_id], dict) else None
            home = (reg or {}).get("home") or {}
            info = {"id": app_id, "title": (reg or {}).get("title") or LISTED.get(app_id) or app_id[:1].upper() + app_id[1:], "installed": reg is not None,
                    "needs": home.get("needs", "") if isinstance(home, dict) else "", "accent": (reg or {}).get("accent"),
                    "has_source": any(s["app"] == app_id for s in sources), "ran": say is not None,
                    "measures": isinstance((say or {}).get("goals"), list), "uploads_only": file_only(columns[app_id])}
            if say:
                entry = next((e for e in say.get("goals") or [] if isinstance(e, dict) and e.get("id") == goal.get("id")), None)
                after = moment(say.get("stale_after"))
                stale = bool(after and now > after)
                quiet = review_off(settings) and not stale
                if settings["suggestions"] and not stale:
                    hit = next((s for s in say.get("suggestions") or [] if isinstance(s, dict) and s.get("goal") == goal.get("id")), None)
                    if hit and hit.get("text"):
                        move = {"text": hit["text"], "why": hit.get("why", "")}
        out.append(read_goal(goal, entry, info, today, stale=stale, move=move, quiet=quiet))
    hand = [r for r in out if r["in_hand"]]
    return {"goals": hand, "record": [r for r in out if not r["in_hand"]], "tally": tally(out)}


# ---------------------------------------------------------------------------------------------------------------
# The parts

def goal_bar(reading):
    """A goal's small plot: a bar filled to its share, with a tick where the plan has today."""
    if reading["share"] is None:
        return '<span class="gb no" role="img" aria-label="No progress to show yet."><i></i><b></b></span>'
    return '<span class="gb" role="img" aria-label="%d%% of the way. The plan has %d%% by today."><i></i><b></b></span>' % (
        _pc(reading["share"]), _pc(reading["plan"]))


def _goal_style(reading):
    cls, style = tint(reading["app"], reading["accent"]) if reading["app"] else ("", "--c:var(--goals)")
    if reading["share"] is not None:
        style += ";--at:%s%%;--due:%s%%" % (_trim(reading["share"] * 100), _trim(reading["plan"] * 100))
    return cls, style


def _trim(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


# A goal not read yet, with no target or date: Goals' list and every band say it alike, and its detail says why, once:
# one state, one phrase. The same words as a goal no page counts, period and all.
NOT_COUNTED = "Not counted yet."


def capital(text):
    """A line a person reads starts with a capital letter: its first letter upper
    case, unless its first word is written with a capital inside, as "iPhone" is."""
    if not isinstance(text, str) or not text[:1].islower():
        return text
    first = text.split(" ", 1)[0]
    return text if any(c.isupper() for c in first[1:]) else text[0].upper() + text[1:]


def goal_status(reading):
    """A goal's one status line: its word, then its caption. A word never stands alone. A goal with no target or date
    yet says what Goals' list says for it, "Not counted yet"."""
    if reading["state"] == "new" and not reading["line"]:
        return '<span class="gs">%s</span>' % esc(NOT_COUNTED)
    said = " ".join(t for t in (reading["caption"], reading.get("step", "")) if t)
    if reading["state"] == "new":
        return '<span class="gs">%s</span>' % esc(said)
    if not said:
        return '<span class="gs"><b>%s</b></span>' % esc(reading["word"])
    return '<span class="gs"><b>%s</b> <span class="dt">\u00b7 %s</span></span>' % (esc(reading["word"]), esc(said))


# Goals' one offer, when a page arrives: the question's id is o-, the goal's six characters,
# a dash and the page's id.
OFFER_ID = re.compile(r"o-[0-9a-f]{6}-([a-z][a-z0-9-]{0,31})")


def offer_app(q):
    """The page a question of Goals' offers a goal to, or None when it isn't one of Goals' offers."""
    m = OFFER_ID.fullmatch(str(q.get("id") or "")) if isinstance(q, dict) else None
    return m.group(1) if m and q.get("kind") == "one" and isinstance(q.get("goal"), str) else None


def goal_item(reading, home=False, under=""):
    """One goal in the band. On an app's page its name opens Goals at that goal; on Home it lights what feeds it.
    `under` is what goes under it: on Home, Goals' offer for it."""
    cls, style = _goal_style(reading)
    off = reading["state"] in ("behind", "missed")
    classes = " ".join(c for c in ("g", "off" if off else "", "new" if reading["state"] == "new" else "", cls) if c)
    if home:
        name = '<span class="gn">%s</span>' % esc(reading["text"])
        head = "<li%s>" % _attrs(classes, style, tabindex="0", data_g=reading["id"], data_item=reading["id"],
                                 data_by=reading["app"] or "", data_pace=reading["word"])
    else:
        name = '<a class="gn" href="/goals/?g=%s" target="_top">%s</a>' % (esc(reading["id"]), esc(reading["text"]))
        head = "<li%s>" % _attrs(classes, style, data_item=reading["id"])
    move = ""
    if reading["move"]:  # the measuring app's suggestion; none on pace or ahead
        move = '<span class="mv">Next: %s</span>' % esc(reading["move"]["text"])
    return head + name + goal_bar(reading) + goal_status(reading) + move + under + "</li>"


def field(ident, label, placeholder, maxlength=120, hint="done", label_cls="", short="", aria="", button="Save", kind="text", low=""):
    """One line to type in, with its label. Return saves it, and Save shows once there's something to save.

    label_cls  a style for the label ("tag"). short  a shorter placeholder for a phone, which the kit's script swaps in.
    aria       the field's name when it has no visible label: label is then "".
    button     its button's word: "Send" for a box that hands its words to Claude; "" for none, where the page's own
               script sends it (the Shop's key, which a paste sends).
    kind       "date" for a date, from `low` on (a missed goal's new date).
    """
    head = ""
    if label:
        head = '<label%s for="%s">%s</label>' % (' class="%s"' % esc(label_cls) if label_cls else "", esc(ident), esc(label))
    if kind == "date":
        return ('%s<div class="fld"><input type="date" id="%s"%s%s>%s</div>') % (
            head, esc(ident), ' min="%s"' % esc(low) if low else "", ' aria-label="%s"' % esc(aria) if aria and not label else "",
            '<button type="button" class="save" hidden>%s</button>' % esc(button) if button else "")
    return ('%s<div class="fld"><input type="text" id="%s" maxlength="%d" enterkeyhint="%s" autocomplete="off"%s%s%s>'
            '%s</div>') % (
        head, esc(ident), maxlength, hint, ' placeholder="%s"' % esc(placeholder) if placeholder else "",
        ' data-short="%s"' % esc(short) if short else "", ' aria-label="%s"' % esc(aria) if aria and not label else "",
        '<button type="button" class="save" hidden>%s</button>' % esc(button) if button else "")


def saved_line(ident, undo=True):
    """Where an entry says what was saved, with Undo beside it for ten seconds; or, for a box that hands its words to
    Claude, what came back, with nothing to undo."""
    return ('<div class="got"><p class="svl"><span role="status"></span>%s</p></div>'
            % ('<button type="button" class="undo" id="%s" hidden>Undo</button>' % esc(ident) if undo else ""))


GOAL_LINE = "Tell Claude what you're working toward, in the chat beside this page."
GOAL_ZERO = "No goals yet. Tell Claude one thing you're working toward, in the chat beside this page."  # day zero
# Under goals already in hand, on Home's band and Goals' list.
SOMETHING_ELSE = "Working toward something else? Tell Claude, in the chat beside this page."
# Goals' day zero: its first line no longer says the first-visit
# tip's sentence, "Goals are set by telling Claude, in the chat beside this page.", so it isn't said twice.
DAY_ZERO = GOAL_LINE
DAY_ZERO_EXAMPLES = ("Swim twice a week", "Walk three times a week", "Read 12 books this year")
DAY_ZERO_ROWS = "Your goals show here, with how each one is going."  # under day zero's three faint rows


def goal_field(page_app=None, first=True, examples=False, label=None, placeholder=None, ident="e-goal"):
    """Where a new goal goes: one line pointing to Claude's conversation, in the chat beside this page,
    with no box. A goal needs Claude to shape it, find what measures it and save it, with the
    person's yes. With examples, a few goals in plain words, to show what one looks like.

    page_app, first, label and placeholder stay for the callers that pass them: the line is the same everywhere.
    """
    out = '<p class="cl0" id="%s">%s<span>%s</span></p>' % (esc(ident), icon("message"), esc(GOAL_ZERO if examples else GOAL_LINE))  # examples: day zero
    if examples:
        said = ["\u201c%s\u201d" % esc(t) for t in GOAL_EXAMPLES]
        out += '<p class="egs0">Like %s or %s.</p>' % (", ".join(said[:-1]), said[-1])
    return out


def goals_band(readings, tally_words="", page_app=None, new=False, block="goals", under=None, ask=True):
    """The goals band at the top of an app's page: the goals this app measures, in Home's band style.

    With no goal, or while the page is just installed, it carries the line that points a new goal to Claude, while
    `ask`: only when the person has no goal at all. `under` is what goes under a goal, by its id: Goals' offer to
    this page.
    """
    under = under or {}
    head = ('<div class="gt"><h2 class="h" id="h-%s"><a href="/goals/" target="_top">Goals</a></h2>%s</div>'
            % (esc(block), _tally(tally_words)))
    if readings and not new:
        body = '<ul class="gl2">%s</ul>' % "".join(goal_item(r, under=under.get(r["id"], "")) for r in readings)
    else:
        rows = "".join('<li%s><span class="gn">%s</span>%s%s%s</li>' % (_attrs(*_goal_style(r)), esc(r["text"]), goal_bar(r), goal_status(r),
                                                                     under.get(r["id"], "")) for r in readings)
        body = '<div class="g0"><ul class="g0l">%s</ul>%s</div>' % (rows, goal_field(
            page_app, label="Add a goal" if readings else "No goal yet", placeholder="Add a goal in a line, then Return") if ask else "")
    return '<section class="t gband" data-block="%s" aria-labelledby="h-%s">%s%s</section>' % (esc(block), esc(block), head, body)


def _tally(words):
    if not words:
        return ""
    count, _, rest = words.partition(" on pace")
    return '<p class="tally"><b>%s</b> on pace%s</p>' % (esc(count), esc(rest))


def chart_scale(days):
    """The value at the foot and at the top of the bars: the dataset's own, else zero to a little over the largest."""
    lo, hi = days.get("min"), days.get("max")
    seen = [v for v in days.get("values") or [] if _is_number(v)]
    ref = days.get("ref") or {}
    if _is_number(ref.get("value")):
        seen.append(ref["value"])
    if not _is_number(lo):
        lo = 0
    if not _is_number(hi) or hi <= lo:
        top = max(seen) if seen else 0
        hi = lo + (top - lo) * 1.28 if top > lo else lo + 1
    return lo, hi


def chart_parts(days, to=None, label_on_line=False):
    """A chart's two parts, (its fourteen bars with the reference line, its axis line), for chart() and the days grid."""
    values = list(days.get("values") or [])
    if len(values) != 14:
        raise KitError("a chart needs 14 values, one a day, and this one has %d" % len(values))
    lo, hi = chart_scale(days)
    lit, planned = set(days.get("lit") or []), set(days.get("planned") or [])
    bars = ""
    for i, v in enumerate(values):
        if not _is_number(v):
            bars += "<span></span>"
            continue
        h = _clamp((v - lo) / (hi - lo))
        cls = " ".join(c for c in ("z" if h == 0 else "", "a" if i in lit else "", "pln" if i in planned else "") if c)
        bars += '<i%s style="--h:%.3f"></i>' % (' class="%s"' % cls if cls else "", h)
    ref, key = days.get("ref") or None, ""
    if ref and _is_number(ref.get("value")):
        y = _clamp((ref["value"] - lo) / (hi - lo))
        if label_on_line:
            bars += '<span class="rf" style="--y:%.3f"><em>%s</em></span>' % (y, esc(ref.get("label", "")))
        else:
            bars += '<span class="rf" style="--y:%.3f"></span>' % y
            key = "<span><i></i>%s</span>" % esc(ref.get("label", ""))
    last = day(days.get("to")) or to
    first = short_day(last - _dt.timedelta(days=13)) if last else ""
    # The axis ends on the data's own last day: "Today" only when that's the page's today.
    end = "Today" if not last or not to or last == to else weekday_day(last)
    return ('<div class="pl" aria-hidden="true">%s</div>' % bars,
            '<p class="ax lb" aria-hidden="true"><span>%s</span><span class="ky">%s</span><span>%s</span></p>' % (esc(first), key, esc(end)))


def chart(days, to=None, label_on_line=False, group=False, block_label=None, says=None):
    """The one chart: the last 14 days ending today as fourteen bars, the first day and Today under them.

    days  {"values": 14 numbers, or None for a day with nothing; "lit": the days, 0 to 13, that prove the finding;
           "ref": {"value", "label"} or None, one dashed reference line; "min" and "max": the values at the foot and
           the top of the bars (optional); "planned": days still to come, drawn as open slots; "to": the last day;
           "label": the picture in one sentence}.
    label_on_line  Home names the reference at the right end of its line; an app's page names it in the key.
    group          Home's charts take the pointer and the keyboard, so they're a group with a tab stop.
    says           Home's alone: what each of the 14 days was, in the app's own words, read out when a day is pointed at.
    """
    bars, axis = chart_parts(days, to, label_on_line)
    label = days.get("label") or block_label or "The last 14 days."
    if group:
        words = [w if isinstance(w, str) else None for w in (says or [])][:14]
        said = ' data-says="%s"' % esc(json.dumps(words, ensure_ascii=False)) if any(words) else ""
        return ('<div class="ins" role="group" aria-roledescription="chart" tabindex="0" aria-label="%s"%s><span class="vl"></span>%s%s</div>'
                % (esc(label), said, bars, axis))
    return '<div class="ins" role="img" aria-label="%s">%s%s</div>' % (esc(label), bars, axis)


MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def months_chart(data):
    """A bar a month (People's Your rhythm). `series`: one or two {"id", "label",
    "values"}, each 2 to 12 months, oldest first, the first at the foot of each bar and the second above it. `to`: the
    last month, YYYY-MM, which names the months under the bars. `lit`: the months, from 0, that prove the finding, in
    the page's colour. `ref`: one dashed line, {"value", "label"}. `max`: the top, optional. `label`: the takeaway in
    words, which is what VoiceOver reads ("More people than usual this month: 14, against your usual 11.")."""
    series = [s for s in data.get("series") or [] if isinstance(s, dict) and plain(s.get("id")) and plain(s.get("label")) and isinstance(s.get("values"), list)]
    if not 1 <= len(series) <= 2:
        raise KitError("a months chart has one or two series, and this one has %d" % len(series))
    n = len(series[0]["values"])
    if not 2 <= n <= 12 or any(len(s["values"]) != n for s in series):
        raise KitError("a months chart's series each hold the same 2 to 12 months")
    when = re.fullmatch(r"(\d{4})-(\d{2})", str(data.get("to") or ""))
    if not when or not 1 <= int(when.group(2)) <= 12:
        raise KitError("a months chart's `to` is its last month, as YYYY-MM")
    last = int(when.group(2)) - 1
    totals = []
    for i in range(n):
        got = [s["values"][i] for s in series if _is_number(s["values"][i]) and s["values"][i] >= 0]
        totals.append(sum(got) if got else None)
    lo, hi = chart_scale({"values": totals, "ref": data.get("ref"), "min": 0, "max": data.get("max")})
    lit = set(i for i in data.get("lit") or [] if isinstance(i, int))
    bars = ""
    for i, total in enumerate(totals):
        if total is None:
            bars += "<span></span>"
            continue
        parts = "".join('<b class="m%d" style="--s:%.3f"></b>' % (k, s["values"][i] / total) for k, s in enumerate(series)
                        if total and _is_number(s["values"][i]) and s["values"][i] > 0)
        h = _clamp((total - lo) / (hi - lo))
        bars += '<i class="%s" style="--h:%.3f">%s</i>' % (" ".join(c for c in ("mb", "z" if h == 0 else "", "a" if i in lit else "") if c), h, parts)
    ref, key = data.get("ref") if isinstance(data.get("ref"), dict) else None, ""
    if ref and _is_number(ref.get("value")):
        bars += '<span class="rf" style="--y:%.3f"></span>' % _clamp((ref["value"] - lo) / (hi - lo))
        key = '<span><i class="rk"></i>%s</span>' % esc(plain(ref.get("label")))
    names = "".join("<span>%s</span>" % MONTH_NAMES[(last - (n - 1 - i)) % 12] for i in range(n))
    keys = "".join('<span><i class="m%d"></i>%s</span>' % (k, esc(plain(s["label"]))) for k, s in enumerate(series)) + key
    return ('<div class="ins mo" role="img" aria-label="%s" style="--n:%d"><div class="pl" aria-hidden="true">%s</div>'
            '<p class="mx lb" aria-hidden="true">%s</p><p class="mk lb" aria-hidden="true">%s</p></div>') % (
        esc(plain(data.get("label")) or "Month by month."), n, bars, names, keys)


def measures(items):
    """A list row's measures against its usual (Content's videos): up to four, each
    {"label", "value", "low", "mid", "high", "min", "max", "words"}, drawn as its label and its standing in words
    ("Clicked: above your usual"), then a hairline from its own `min` to `max`, the usual's middle half (`low` to `high`)
    as a band, a tick at its median (`mid`) and a dot at `value`. With no value there's no dot ("Not in this export"),
    and with no low and high the band is ghosted ("Shows once a few weeks of exports are in.")."""
    if not isinstance(items, list) or not 1 <= len(items) <= 4:
        raise KitError("a row holds one to four measures")
    out = ""
    for m in items:
        m = m if isinstance(m, dict) else {}
        label, words, lo, hi = plain(m.get("label")), plain(m.get("words")), m.get("min"), m.get("max")
        if not label or not words or not (_is_number(lo) and _is_number(hi) and hi > lo):
            raise KitError("a measure has its label, its words, and a min under its max")

        def at(v):
            return _clamp((v - lo) / (hi - lo))
        whole = _is_number(m.get("low")) and _is_number(m.get("high")) and m["high"] >= m["low"]
        band = '<span class="mband" style="--a:%.3f;--b:%.3f"></span>' % (at(m["low"]), at(m["high"])) if whole else '<span class="mband g"></span>'
        tick = '<span class="mtick" style="--x:%.3f"></span>' % at(m["mid"]) if whole and _is_number(m.get("mid")) else ""
        dot = '<span class="mdot" style="--x:%.3f"></span>' % at(m["value"]) if _is_number(m.get("value")) else ""
        out += '<li><span class="mlb"><b>%s:</b> %s</span><span class="mline" aria-hidden="true">%s%s%s</span></li>' % (esc(label), esc(words), band, tick, dot)
    return '<ul class="msr">%s</ul>' % out


def empty_marks():
    """The 14 days before anything has filled them: fourteen empty marks, and what will show there."""
    return ('<div class="ins0" aria-hidden="true"><div class="pl">%s</div><p class="ax lb"><span></span>'
            '<span class="ky">Your last 14 days show here</span><span>Today</span></p></div>') % ("<i></i>" * 14)


def page_link(link, app_id=None):
    """A home.json or say.json `link`, "health#drop", as the address it opens: "/health/#drop", or "#drop" on that app's
    own page (app_id). None for anything else."""
    if not isinstance(link, str):
        return None
    app, _, part = link.partition("#")
    app = app.strip("/")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", app) or (part and not re.fullmatch(r"[a-z0-9-]{1,40}", part)):
        return None
    if app_id and app == app_id:
        return "#%s" % part if part else "/%s/" % app
    return "/%s/%s" % (app, "#" + part if part else "")


# The button a move gets, by what its link opens: the drop place takes a fresh file.
MOVE_DO = {"drop": "Add a fresh export"}


def connect(app_id, words="Connect", service=None, label=None, kind="connect"):
    """A calm tinted action that hands Claude a request. It names what's needed, never one service."""
    return '<button type="button"%s>%s</button>' % (_attrs("cta", data_connect=True, data_app=app_id, data_kind=kind if kind != "connect" else None,
                                                           data_service=service, aria_label=label), esc(words))


def empty_state(symbol, line, action="", via="", steps=(), drop="", step=None, link=""):
    """An empty section: its symbol, one line on what will appear there, and the one thing it needs.

    steps  a few plain lines, in order, for what to do first; step  which of them they're on, from 1, marked as the
           current one (none when it's missing or out of range).
    drop   a drop place (drop_place()), in place of an action. link  a link that leaves the page (out_link()), among
           the actions.
    """
    out = '<div class="es">%s<p>%s</p>' % (icon(symbol), esc(line))
    lines = [t for t in steps or () if isinstance(t, str) and t.strip()]
    on = step if isinstance(step, int) and not isinstance(step, bool) and 1 <= step <= len(lines) else 0
    if lines:
        out += '<ol class="steps">%s</ol>' % "".join(
            '<li class="on" aria-current="step">%s</li>' % esc(t) if i == on else "<li>%s</li>" % esc(t) for i, t in enumerate(lines, 1))
    if drop:
        out += drop
    if action or link:
        out += '<p class="acts">%s</p>' % (action + link)
    if via:
        out += '<p class="via">%s</p>' % esc(via)
    return out + "</div>"


def needs_setup(column):
    """Whether a page has something only the person can set up: its column.json's home line names the one thing it
    needs, a connector to connect or a file to give. A page that needs neither, as Research doesn't, says nothing
    there and starts by itself, so it has no Set up."""
    needs = column.get("home").get("needs") if isinstance(column, dict) and isinstance(column.get("home"), dict) else ""
    return isinstance(needs, str) and bool(needs.strip())


def file_only(column):
    """True when every way in a column.json declares is a file dropped on the app's own page (`kind` "upload"), as
    Health's export is: Claude has nothing to connect."""
    sources = column.get("sources") if isinstance(column, dict) else None
    return isinstance(sources, list) and bool(sources) and all(isinstance(s, dict) and s.get("kind") == "upload" for s in sources)


def upload_source(column):
    """The app's one upload source from its column.json (`kind` "upload"), or None."""
    return next((s for s in column.get("sources") or [] if isinstance(s, dict) and s.get("kind") == "upload"), None)


def first_visit(text, key, cls="hint"):
    """A one-line hint for the person's first visit: drawn hidden, and the
    kit's script shows it until they've left the page once, remembered in this browser under `key`. "" without words."""
    text = " ".join(text.split()) if isinstance(text, str) else ""
    return '<p class="%s" data-hint="%s" hidden>%s</p>' % (esc(cls), esc(key), esc(text)) if text else ""


def drop_place(app_id, accepts, line, title="", hint=None):
    """A file's drop place: the app's own line, one button that opens the Mac's own open panel,
    a hidden file field, and one line that says how it went. The kit's script sends the file from disk, one at a time.

    accepts  the upload source's extensions ("zip", "xml"). title  the app's name, for the line a wrong file gets.
    hint     a first-visit hint over it, from the empty state's "hint" (first_visit()).
    """
    kinds = [k.strip().lower().lstrip(".") for k in accepts or () if isinstance(k, str) and k.strip().lstrip(".").isalnum()]
    if not kinds:
        raise KitError("a drop place needs its upload source's accepts")
    return ('<div class="drop" data-drop="%s" data-accepts="%s" data-title="%s">%s<p class="dl">%s</p>'
            '<button type="button" class="cta" data-choose>Choose the file</button>'
            '<input type="file" class="vh" tabindex="-1" aria-hidden="true" accept="%s">'
            '<p class="dmsg" role="status" aria-live="polite"></p></div>') % (
        esc(app_id), esc(",".join(kinds)), esc(title), first_visit(hint, "%s-drop" % app_id), esc(line or "Drop your file here."),
        esc(",".join("." + k for k in kinds)))


def badges(items):
    """What Research and Dreams brought: a glyph and a count, each opening its top item."""
    out = ""
    for b in items or []:
        eng = b.get("eng")
        if eng not in ("research", "dreams") or not b.get("n"):
            continue
        what = "find" if eng == "research" else "pattern"
        more = b.get("more") or ("%d %s%s from %s" % (b["n"], what, "" if b["n"] == 1 else "s", eng.capitalize()))
        out += ('<button type="button" class="bd" data-eng="%s" data-n="%d" aria-label="%s, %d %s%s. %s">%s%d'
                '<span class="pop" aria-hidden="true"><span>%s</span><em>%s</em></span></button>') % (
            eng, int(b["n"]), eng.capitalize(), int(b["n"]), what, "" if b["n"] == 1 else "s", esc(b.get("top", "")),
            icon(APPS[eng]), int(b["n"]), esc(b.get("top", "")), esc(more))
    return '<span class="bds">%s</span>' % out if out else ""


# An app that keeps an answer straight away rather than for Claude's next morning, and what its answer shows: Goals, which
# saves a why as the goal's own.
ANSWER_KEPT = {"goals": "Saved with your goal", "learning": "Saved. Research uses it at its next scout."}  # Research reads answers on Mondays


def fill_goal(q, texts):
    """A question that names its goal as {goal}, with that goal's own words. Goals keeps a goal's typed words out of
    say.json and home.json, so the page fills them in from goals.json, by the question's "goal".
    None when that goal isn't there; a question without {goal} comes back as it is.

    texts  each goal's words by its id, as read_goals() reads them."""
    text = q.get("text")
    if not isinstance(text, str) or "{goal}" not in text:
        return q
    words = texts.get(q.get("goal"))
    return dict(q, text=text.replace("{goal}", words)) if isinstance(words, str) and words else None


def fill_names(q, names):
    """A question that names one of its app's own things as {project} (Research's, from its own store), as fill_goal
    fills {goal}: `names` is {"project": {"p-3fa9c1": "their words"}}, from the app's build, and the question's own
    "project" picks the words; a pick's {project} is filled by the pick's own "project". The words never sit in say.json.
    A question whose name isn't there is left out, and so is such a pick; a question left with
    fewer than two picks is left out too. None when it's left out; else the question, filled."""
    text = q.get("text")
    for key, words in (names or {}).items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z]{1,16}", key) or key == "goal" or not isinstance(words, dict):
            continue
        mark = "{%s}" % key
        if isinstance(text, str) and mark in text:
            got = words.get(q.get(key))
            if not isinstance(got, str) or not got.strip():
                return None
            text = text.replace(mark, " ".join(got.split()))
        picks = q.get("picks")
        if isinstance(picks, list) and any(isinstance(p, dict) and mark in str(p.get("label") or "") for p in picks):
            kept = []
            for p in picks:
                if isinstance(p, dict) and mark in str(p.get("label") or ""):
                    got = words.get(p.get(key))
                    if not isinstance(got, str) or not got.strip():
                        continue
                    p = dict(p, label=p["label"].replace(mark, " ".join(got.split())))
                kept.append(p)
            if len([p for p in kept if isinstance(p, dict) and p.get("id")]) < 2:
                return None
            q = dict(q, picks=kept)
    if re.search(r"\{[a-z]{1,16}\}", text or "") or any(isinstance(p, dict) and re.search(r"\{[a-z]{1,16}\}", str(p.get("label") or ""))
                                                          for p in q.get("picks") or []):
        return None  # a name left to fill, such as an app that passed none: never braces on the page
    return dict(q, text=text) if text != q.get("text") else q


def plain(value):
    """A dataset's words as one plain line, or "" for anything that isn't words."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def out_link(link, cls=""):
    """A link that leaves the page, {"href", "text"} (a find's source, a release note, a thread in Gmail, an empty
    state's way in, drawn as a button with cls "cta"): https to a named host, with no user info, port, space or hidden
    character, in at most 1,000 characters, its words plain and at most 80, else nothing. The kit's script opens it
    through Home's server in the person's own browser, never inside the pane, where Claude can read what a page shows."""
    if not isinstance(link, dict):
        return ""
    href, text = link.get("href"), plain(link.get("text"))
    if (not isinstance(href, str) or len(href) > 1000 or not text or len(text) > 80
            or not re.fullmatch(r"https://[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+([/?#][^\s\"'<>\\`]*)?", href)):
        return ""
    return '<a%s href="%s" data-open rel="noopener noreferrer">%s</a>' % (' class="%s"' % esc(cls) if cls else "", esc(href), esc(text))


def question(q, app_id, tag="", accent=None, words=None, ident=None, tint_app=None, saved=None):
    """One of Claude's questions, open or answered. A typed answer saves on Return, and a pick on its tap.

    q         a question from say.json: {"id", "kind", "text", "picks", "only", "max", "answer"}.
    words     what was typed, when this is the app's own page and it has it. Home never has it.
    tint_app  the app whose colour it wears, when that isn't the app that asks: on Goals' page, its goal's app.
    saved     what an answer shows beside Undo, for an app that keeps it straight away: else "Saved. Claude reads it tomorrow morning."
    """
    kind = q.get("kind") or "words"
    if kind not in ("words", "one", "multi"):
        raise KitError("a question's kind is words, one or multi, and %r isn't" % kind)
    key = ident or "%s-%s" % (app_id, q.get("id", ""))
    answer = q.get("answer") if isinstance(q.get("answer"), dict) else None
    cls, style = tint(tint_app or app_id, accent)
    undo = '<button type="button" class="undo" id="u-%s">Undo</button>' % esc(key)
    saved = esc(saved or ANSWER_KEPT.get(app_id) or "Saved. Claude reads it tomorrow morning.") + " " + undo
    head = '<p class="tag">%s</p>' % esc(tag) if tag else ""
    if kind == "words":
        try:
            most = max(1, min(120, int(q.get("max") or 120)))
        except (TypeError, ValueError):
            most = 120
        body = ('<label class="q" id="q-%s" for="a-%s">%s</label><div class="fld"%s><input type="text" id="a-%s" maxlength="%d" '
                'enterkeyhint="send" autocomplete="off" placeholder="Your answer, then Return">'
                '<button type="button" class="save" hidden>Save</button></div>'
                '<div class="ans" aria-live="polite"%s><p class="said">%s</p><p class="sv">%s</p></div>') % (  # said when it shows
            esc(key), esc(key), esc(q.get("text", "")), " hidden" if answer else "", esc(key), most,
            "" if answer else " hidden", esc(words or ""), saved)
    else:
        picks = [p for p in q.get("picks") or [] if isinstance(p, dict) and p.get("id")]
        if not 2 <= len(picks) <= 8:
            raise KitError("a pick question has 2 to 8 picks, and %s has %d" % (q.get("id"), len(picks)))
        only = q.get("only") if kind == "multi" else None
        if isinstance(only, dict):  # say/v1: {"id", "label"} beside the picks, drawn as the last
            if isinstance(only.get("id"), str) and only["id"] and not any(p["id"] == only["id"] for p in picks):
                picks = picks + [{"id": only["id"], "label": only.get("label") if isinstance(only.get("label"), str) and only["label"].strip() else only["id"]}]
            only = only.get("id") if isinstance(only.get("id"), str) and only["id"] else None
        elif not isinstance(only, str) or not only:
            only = None  # an older page's own: one of its picks, by id
        picks = [p for p in picks if p["id"] != only] + [p for p in picks if p["id"] == only]
        if kind == "one":
            chosen = {answer.get("pick")} if answer else set()
            role, each = "radiogroup", 'role="radio" aria-checked="%s"'
        else:
            chosen = set(answer.get("picks") or []) if answer else set()
            role, each = "group", 'aria-pressed="%s"'
        chips = "".join('<button type="button" class="pk" id="p-%s-%s" %s data-pick="%s">%s</button>' % (
            esc(key), esc(p["id"]), each % ("true" if p["id"] in chosen else "false"), esc(p["id"]), esc(p.get("label", p["id"]))) for p in picks)
        body = ('<p class="q" id="q-%s">%s</p><div class="picks" role="%s" aria-labelledby="q-%s">%s</div>'
                '<p class="sv"%s>%s</p>') % (esc(key), esc(q.get("text", "")), role, esc(key), chips, "" if chosen else " hidden", saved)
    return '<div%s>%s%s<p class="msg" role="status"></p></div>' % (_attrs(
        " ".join(c for c in ("ask", cls) if c), style, role="group", aria_labelledby="q-" + key, data_app=app_id,
        data_q=q.get("id", ""), data_kind=kind, data_only=only if kind == "multi" else None), head, body)


ASKS_NONE = "Nothing to ask yet."  # Claude asks with nothing in it, the same on every page


def asks(items, note="", block="questions", own=True):
    """Claude asks: the one place for questions, at the foot of the page.

    items  the questions as drawn, each from question(). With none it's one quiet line.
    """
    title = '<h2 class="h%s" id="h-%s">Claude asks</h2>' % (" hh" if own else "", esc(block))
    if not items:
        return ('<section class="t asks quiet" data-block="%s" aria-labelledby="h-%s">%s<p class="note">%s</p></section>'
                % (esc(block), esc(block), title, esc(note or ASKS_NONE)))
    n = max(2, min(3, len(items)))
    return ('<section class="t asks" data-block="%s" aria-labelledby="h-%s">%s<p class="note">%s</p>'
            '<div class="qs" style="--n:%d">%s</div></section>') % (
        esc(block), esc(block), title, esc(note or "Written from your goals and your last two weeks. Your answers shape tomorrow's page."),
        n, "".join(items))


def footer(built_at=None):
    """The foot of every page: where the records stay, and when the page was last updated, "Updated today at 11:16 pm."
    The day is the build's own; the kit's script says it as the reader's today, yesterday or
    the day itself, so a page that hasn't been rebuilt never claims today. Then Help and Privacy, each
    opening in the same tab, as the rail's Shop does."""
    when = ""
    if built_at is not None:
        when = ' <span data-updated="%s">Updated today at %s.</span>' % (built_at.date().isoformat(), esc(clock(built_at)))
    return '<footer class="t foot">%s%s<span class="fl"><a href="/help/" target="_top">Help</a><a href="/privacy/" target="_top">Privacy</a></span></footer>' % (esc(PRIVACY), when)


def _in(x, unit):
    """A figure on the plot's side: its sign when it's money, else the bare number."""
    unit = (unit or "").strip()
    return amount(x, unit) if unit and not any(ch.isalnum() for ch in unit) else num(x)


def last_counted(reading):
    """The detail's one line of the last change its app counted: "Last counted: 1 swim, Thu Jun 12". "" with none."""
    before, last = (reading.get("start") or {}).get("value"), None
    for p in reading.get("points") or []:
        if isinstance(p, (list, tuple)) and len(p) == 2 and day(p[0]) and _is_number(p[1]):
            if _is_number(before) and p[1] != before:
                last = (day(p[0]), p[1] - before)
            before = p[1]
    if last is None:
        return ""
    return "Last counted: %s, %s" % (amount(abs(last[1]), reading.get("unit")), weekday_day(last[0]))


def goal_plot(reading, today):
    """The one full plot, the same for every goal, in its own numbers: time across from its start to its due day, and
    up its side the start, the midway and the target. Solid is what's done, dashed the plan, dotted where this pace
    gets to, named beside its open dot. "" for a goal with no plot yet."""
    if reading["share"] is None or not reading["start"]:
        return ""
    a, d = day(reading["start"]["on"]), day(reading["by"])
    v0, target, unit = reading["start"]["value"], reading["target"], reading.get("unit")
    started = reading["state"] == "started"

    def share(v):
        return _clamp((v - v0) / (target - v0))
    lands = None if started else day(reading["lands"])
    ls = 1.0 if lands else share(reading["reaches"]) if reading["reaches"] is not None and not started else reading["share"]
    end = max(d, lands) if lands else d
    span = max(1, (end - a).days)

    def X(when):
        return _f(_clamp((when - a).days / span) * 100)

    def Y(part):
        return _f(100 - part * 100)
    tx, dx = X(min(today, end)), X(d)
    lx = X(lands) if lands else dx
    ly, ty = Y(ls), Y(reading["share"])
    late = float(dx) < 99.5
    inside = a < today < end  # "Today" only where it's on the plot: on its start or end, the day's own label says it
    tdy = '<i class="tdy" style="left:%s%%"></i>' % tx if inside else ""
    now = '<span class="c now" style="left:%s%%">Today</span>' % tx if inside else ""
    steps = [(day(p[0]), p[1]) for p in reading["points"] if isinstance(p, (list, tuple)) and len(p) == 2 and day(p[0]) and _is_number(p[1])]
    steps = [(w, v) for w, v in steps if a <= w <= today]
    if not steps or share(steps[-1][1]) != reading["share"]:
        steps.append((min(today, end), reading["value"]))
    path = "M0 100" + "".join("H%sV%s" % (X(w), Y(share(v))) for w, v in steps) + "H%s" % tx
    name, by = reading["text"], day_words(d, today)
    goal_end = "%s by %s" % (amount(target, unit), by)
    places = 0 if float(target).is_integer() and float(v0).is_integer() else 1  # a count reads whole: "4 swims"
    reach = target if lands else v0 + ls * (target - v0)
    landing = "%s by %s at this pace" % (amount(round(reach, places), unit), day_words(lands, today) if lands else by)
    plan_value = round(v0 + (reading["plan"] or 0) * (target - v0), places)
    label = "%s, from %s to %s, toward %s. %s so far, and the plan has %s by today. %s" % (
        name, day_words(a, today), by, reading["line"], reading.get("figure") or amount(reading["value"], unit),
        amount(plan_value, unit), "There's no pace yet. %s." % reading["caption"].rstrip(".") if started
        else "At this pace it gets to %s." % landing.replace(" at this pace", ""))
    side = ('<div class="yl" aria-hidden="true"><span style="top:0">%s</span><span style="top:50%%">%s</span>'
            '<span style="top:100%%">%s</span></div>') % (esc(_in(target, unit)), esc(_in(round(v0 + (target - v0) / 2, 1), unit)),
                                                         esc(_in(v0, unit)))
    if started:
        return ('<figure class="pic" role="img" aria-label="%s">'
                '<p class="key" aria-hidden="true"><span><i></i>Done</span><span><i class="kn"></i>The plan</span></p>%s'
                '<div class="plot" aria-hidden="true"><svg viewBox="0 0 100 100" preserveAspectRatio="none"><path class="ar" d="%sV100Z"/>'
                '<path class="gd" d="M0 0H100M0 50H100"/><path class="bs" d="M0 100H100"/><path class="pn" d="M0 100L%s 0"/><path class="hs" d="%s"/></svg>'
                '%s<i class="pt" style="left:%s%%;top:%s%%"></i></div>'
                '<p class="axl" aria-hidden="true"><span style="left:0">%s</span>%s'
                '<span style="right:0">%s</span></p></figure>') % (
            esc(label), side, path, dx, path, tdy, tx, ty, esc(day_words(a, today)), now, esc(goal_end))
    return ('<figure class="pic" role="img" aria-label="%s">'
            '<p class="key" aria-hidden="true"><span><i></i>Done</span><span><i class="kn"></i>The plan</span><span><i class="kp"></i>At this pace</span></p>%s'
            '<div class="plot" aria-hidden="true"><svg viewBox="0 0 100 100" preserveAspectRatio="none"><path class="ar" d="%sV100Z"/>'
            '<path class="gd" d="M0 0H100M0 50H100"/><path class="bs" d="M0 100H100"/><path class="pn" d="M0 100L%s 0"/>'
            '<path class="pc" d="M%s %sL%s %s"/><path class="hs" d="%s"/></svg>%s%s'
            '<i class="pt" style="left:%s%%;top:%s%%"></i><i class="pt land" style="left:%s%%;top:%s%%"></i>'
            '<span class="pll" style="right:%s%%;bottom:calc(%s%% + .5rem)">%s</span></div>'
            '<p class="axl" aria-hidden="true"><span style="left:0">%s</span>%s'
            '<span %s>%s</span></p></figure>') % (
        esc(label), side, path, dx, tx, ty, lx, ly, path, '<i class="due" style="left:%s%%"></i>' % dx if late else "", tdy, tx, ty, lx, ly,
        _f(100 - float(lx)), _f(100 - float(ly)), esc(landing), esc(day_words(a, today)), now,
        'class="c" style="left:%s%%"' % dx if late else 'style="right:0"', esc(goal_end))


def _f(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------------------------------------------
# Goals' own page: the list of goals, and one goal's detail. The kit's script picks a goal and opens Change target or date.

def _goal_row(reading, selected):
    """One goal in the list: its name, which picks it, its small plot, and its one status line."""
    cls, style = _goal_style(reading)
    off, new = reading["state"] in ("behind", "missed"), reading["state"] == "new"
    classes = " ".join(c for c in ("gr", "off" if off else "", "new" if new else "", "sel" if selected else "", cls) if c)
    name = '<button type="button" class="gn"%s>%s</button>' % (
        _attrs(data_pick=reading["id"], aria_controls="d-" + reading["id"], aria_pressed="true" if selected else "false"), esc(reading["text"]))
    if new and not reading["line"]:  # no target or date yet: its detail says so, once
        status = '<p class="gs">%s</p>' % esc(NOT_COUNTED)
    elif new:  # its caption, then its step, each on its own line, in the band's words: one state, one phrase
        status = '<p class="gs">%s</p>%s' % (esc(reading["caption"]), '<p class="sv"><span>%s</span></p>' % esc(reading["step"]) if reading.get("step") else "")
    elif reading["caption"]:
        status = '<p class="gs"><b>%s</b> · %s</p>' % (esc(reading["word"]), esc(reading["caption"]))
    else:
        status = '<p class="gs"><b>%s</b></p>' % esc(reading["word"])
    return "<li%s>%s%s%s</li>" % (_attrs(classes, style, data_g=reading["id"], data_item=reading["id"]), name, goal_bar(reading), status)


def goals_list(readings, tally_words="", record=(), selected=None, block="goals"):
    """"Your goals": the goals in hand in the file's order, a row each, and under them the line that asks for another;
    then the ones done and set aside, a quiet list under "Done and set aside", each with "Bring it back".
    The tally shows from three goals in hand. With no goal at all it says what will line up here and what to do
    first."""
    readings, record = list(readings), list(record)
    rows = readings + record
    if selected is None and rows:
        selected = rows[0]["id"]
    tally = _tally(tally_words) if len(readings) >= 3 else ""
    head = '<div class="lh"><h2 class="h" id="h-%s">Your goals</h2>%s</div>' % (esc(block), tally)
    body = '<ul class="rows">%s</ul>' % "".join(_goal_row(r, r["id"] == selected) for r in readings) if readings else ""
    if not rows:  # day zero, one tile
        said = ["\u201c%s\u201d" % esc(t) for t in DAY_ZERO_EXAMPLES]
        zero = ('<p class="cl0" id="e-add">%s<span>%s</span></p><p class="egs0">Like %s or %s.</p>'
                '<ul class="rows faint" aria-hidden="true">%s</ul><p class="via">%s</p>') % (
            icon("message"), esc(DAY_ZERO), ", ".join(said[:-1]), said[-1],
            '<li class="gr"><span class="gb no"><i></i><b></b></span></li>' * 3, esc(DAY_ZERO_ROWS))
        return '<section%s>%s%s</section>' % (_attrs("t list new", aria_labelledby="h-" + block), head, zero)
    add = '<div class="addg">%s</div>' % _something_else()
    ended = ""
    if record:  # the quiet record, under the line that asks for another
        ended = ('<h3 class="eh" id="h-%s-e">Done and set aside</h3><ul class="rows ended" aria-labelledby="h-%s-e">%s</ul>'
                 % (esc(block), esc(block), "".join(_ended_row(r, r["id"] == selected) for r in record)))
    return '<section%s>%s%s%s%s</section>' % (_attrs("t list", aria_labelledby="h-" + block), head, body, add, ended)


def _ended_row(reading, selected):
    """A goal done or set aside, in the quiet list: its name, which picks it, its one line, and "Bring it back"."""
    cls, style = _goal_style(reading)
    classes = " ".join(c for c in ("gr", "sel" if selected else "", cls) if c)
    name = '<button type="button" class="gn"%s>%s</button>' % (_attrs(
        data_pick=reading["id"], aria_controls="d-" + reading["id"], aria_pressed="true" if selected else "false"),
        esc(reading["text"]))
    said = "%s · %s" % (reading["word"], reading["caption"]) if reading["caption"] else reading["word"]
    return '<li%s>%s<p class="gs">%s</p><span class="bb">%s</span></li>' % (
        _attrs(classes, style, data_g=reading["id"], data_item=reading["id"]), name, esc(said), _back(reading))


def _saves(gid):
    """A save's attributes on the page: Goals' action with the goal fixed, and Undo."""
    return dict(data_app="goals", data_undo="undo", data_takes="change",
                data_fixed=json.dumps({"goal": gid}, separators=(",", ":")))


def _back(reading):
    return '<button type="button" class="tb"%s>Bring it back</button>' % _attrs(data_act="back", **_saves(reading["id"]))


def _goal_entry(ent, act, value, placeholder, maxlength, aria, gid):
    """A line that opens in place of the one its button sits in (the kit's `.tb[data-edit]`): Return saves it through
    Goals' action, Cancel or Escape close it, and its saved line and Undo show under it."""
    return ('<div%s><div class="edit" hidden>%s<span class="lb">Return saves it</span>'
            '<button type="button" class="lk" data-cancel>Cancel</button></div>%s</div>') % (
        _attrs("ent", id=ent, data_act=act, data_value=value, **_saves(gid)),
        field(ent + "-i", "", placeholder, maxlength=maxlength, aria=aria), saved_line(ent + "-u"))


def _date_entry(gid, today):
    """A missed goal's new date: a date field in place of its step, from tomorrow, saved through Goals' set with the goal
    fixed, and Undo."""
    tomorrow = (today + _dt.timedelta(days=1)).isoformat()
    return ('<div%s><div class="edit" hidden>%s<button type="button" class="lk" data-cancel>Cancel</button></div>%s</div>') % (
        _attrs("ent", id="e-date-" + gid, data_act="set", data_field="by", data_value="", **_saves(gid)),
        field("e-date-%s-i" % gid, "", "", aria="Its new date. Return saves it.", kind="date", low=tomorrow), saved_line("e-date-%s-u" % gid))


def _set_entry(gid, line):
    return _goal_entry("e-set-" + gid, "set", line, "Like '12 swims by Sep 1'", 80, "Target and date. Return saves it.", gid)


def _why_entry(gid, why):
    return _goal_entry("e-why-" + gid, "because", why or "", "Why it matters to you", 120, "Why it matters. Return saves it.",
                  gid)


def _verdict(reading):
    """The detail's one line of where the goal stands: its word, then the pace in its app's own words."""
    if reading["state"] == "new":
        return " ".join(t for t in (reading["caption"], reading.get("step", "")) if t)
    if reading["state"] in ("behind", "on", "ahead", "unknown") and reading["why_pace"]:
        return "%s: %s" % (reading["word"], reading["why_pace"])
    return "%s · %s" % (reading["word"], reading["caption"]) if reading["caption"] else reading["word"]


def _changes(reading, today):
    """The last changes, newest first, at most two: the app's own words for them, else each step of its points."""
    out = []
    for c in reversed(reading["changes"]):
        when = day(c.get("on")) if isinstance(c, dict) else None
        if when and isinstance(c.get("text"), str) and c["text"].strip():
            out.append((c["text"].strip(), day_words(when, today)))
    if out:
        return out[:2]
    unit = (reading["unit"] or "").strip()
    sign = unit if unit and not any(ch.isalnum() for ch in unit) else ""
    before = (reading["start"] or {}).get("value")
    for p in reading["points"]:
        if not (isinstance(p, (list, tuple)) and len(p) == 2 and day(p[0]) and _is_number(p[1])):
            continue
        if _is_number(before) and p[1] != before:
            step = p[1] - before
            out.append(("%s%s%s" % ("+" if step > 0 else "−", sign, num(abs(step))), day_words(day(p[0]), today)))
        before = p[1]
    return out[::-1][:2]


# What it takes, and the detail in its order.
def what_it_takes(reading, today):
    """What's left to do in the time left, under the verdict: "What it takes: 16 swims in the 7 weeks left." "" with no
    number to go by, nothing left, or no time left. A goal to come down counts down."""
    target, value, start = reading.get("target"), reading.get("value"), (reading.get("start") or {}).get("value")
    by = day(reading.get("by") or "")
    if reading["state"] not in ("behind", "on", "ahead", "started", "unknown") or by is None:
        return ""
    if not (_is_number(target) and _is_number(value)):
        return ""
    left = value - target if _is_number(start) and target < start else target - value
    days = (by - today).days
    if left <= 0 or days <= 0:
        return ""
    weeks = int(days / 7 + 0.5)
    span = "the %d weeks left" % weeks if weeks >= 2 else "the day left" if days == 1 else "the %d days left" % days
    return "What it takes: %s in %s." % (amount(left, reading.get("unit")), span)


def goal_detail(reading, today, shown=True, you_said=None):
    """One goal's detail, in the build-out's order: its name and the app that measures it, why it matters in the
    person's own words, where it stands with what it takes, its next move in full weight, the one full plot, its last
    changes, then its target with its quiet actions, each its own button: "Change target or date", "Edit
    why", "Set aside" and "Mark done" in hand, "Bring it back" once ended. A missed goal's step, "Set a new date" and
    "Set it aside", stands in for two of them, and its date field opens in place of the step."""
    gid = reading["id"]
    cls, style = tint(reading["app"], reading["accent"]) if reading["app"] else ("", "--c:var(--goals)")
    src = ""
    if reading["app"]:
        chip = icon(app_icon(reading["app"])) + esc(reading["app_title"])
        if reading["installed"]:
            chip = '<a href="/%s/" target="_top">%s</a>' % (esc(reading["app"]), chip)
        src = '<ul class="src" aria-label="Counted by"><li>%s</li></ul>' % chip
    parts = [("auto", '<header class="dh"><h2 class="h" id="dn-%s">%s</h2>%s</header>' % (esc(gid), esc(reading["text"]), src))]
    if reading["why"]:
        parts.append(("auto", '<p class="why">\u201c%s\u201d</p>' % esc(reading["why"])))
    takes = what_it_takes(reading, today)
    said = _verdict(reading)
    step, do, acts = reading.get("step") or "", reading.get("do"), ""
    missed = reading["state"] == "missed" and reading["in_hand"]
    if missed:  # its step, as two buttons
        acts = ('<button type="button" class="tb" data-edit="e-date-%s">Set a new date</button>'
                '<button type="button" class="tb"%s>Set aside</button>') % (esc(gid), _attrs(
                    data_act="aside", **_saves(gid)))
    elif step and step not in said:
        said = "%s. %s" % (said.rstrip("."), step)
    then = reading.get("then")
    if then and reading["in_hand"]:  # the measuring page's one more move, through Goals' own action, with Undo
        acts += '<button type="button" class="tb"%s>%s</button>' % (_attrs(
            data_act=then["act"], data_app="goals", data_undo="undo", data_takes="change",
            data_fixed=json.dumps(then["fields"], separators=(",", ":"))), esc(then["words"]))
    if isinstance(do, dict) and do.get("words") and do.get("link"):
        acts += '<a class="tb" href="%s" target="_top">%s</a>' % (esc(page_link(do["link"])), esc(do["words"]))
    parts.append(("auto", '<p class="dsay">%s</p>' % esc(said)))  # each part its own row, one element each,
    if takes:  # so the row that grows is the plot's
        parts.append(("auto", '<p class="via">%s</p>' % esc(takes)))
    if missed:  # the date field opens in place of the step, as the kit opens a line in place of its `.meta`
        parts.append(("auto", '<div class="dstep"><p class="acts meta">%s</p>%s</div>' % (acts, _date_entry(gid, today))))
    elif acts:
        parts.append(("auto", '<p class="acts">%s</p>' % acts))
    if isinstance(you_said, dict) and isinstance(you_said.get("words"), str) and you_said["words"].strip():  # what they said, in their words
        parts.append(("auto", '<p class="dsaid">You said: \u201c%s\u201d</p>' % (
            esc(you_said["words"].strip()))))
    if reading["move"]:
        why = reading["move"].get("why", "")
        parts.append(("auto", '<p class="dnext">Next: %s%s</p>' % (esc(reading["move"]["text"]), '<span>%s</span>' % esc(why) if why else "")))
    elif reading.get("review_off"):  # where Next would be, while they said no to the morning review
        parts.append(("auto", '<p class="dnext nrv">%s %s</p>' % (esc(REVIEW_OFF), REVIEW_ON)))
    plot = goal_plot(reading, today) or '<p class="via">%s</p>' % esc(NO_PLOT)
    parts.append(("minmax(0,1fr)", '<div class="picw">%s</div>' % plot))
    counted = last_counted(reading)
    if counted:
        parts.append(("auto", '<p class="via">%s</p>' % esc(counted)))
    if reading["app"] == "goals" and reading["in_hand"] and reading["state"] != "done" and reading.get("target") is not None:
        told = "e-told-" + gid  # where a goal kept by hand stands, told on the page
        parts.append(("auto", '<div%s>%s%s</div>' % (_attrs("ent told", id=told, data_app="goals", data_act="progress",
                      data_field="value", data_undo="undo", data_takes="change", data_fixed=json.dumps({"goal": gid}, separators=(",", ":"))),
                      field(told + "-i", "Where does it stand today?", reading.get("unit") or "", maxlength=24,
                            aria="Where it stands today, as a number. Return saves it.", button="Save"),
                      saved_line(told + "-u"))))
    line = reading["line"]
    unset = not line and reading["state"] == "new"  # no target or date yet: the verdict says so, once
    meta = "" if unset else '<span data-meta>%s</span>' % esc(line or reading["measured"] or reading["word"])
    quiet, edits = [], ""  # the quiet actions, each its own button; a missed goal's step above has two of them
    # by the goal's own status: a goal marked done stays in hand for seven days, and one that reached its target is
    # read as done while it's still active (the kit's read_goal gives `status`, as Goals' reading.py does)
    status = reading.get("status") or ("aside" if reading["state"] == "aside" else "active" if reading["in_hand"] else "done")
    if status == "active" and unset:  # its one move until it has a target and a date
        quiet.append('<button type="button" class="tb" data-edit="e-set-%s">Set a target and a date</button>' % esc(gid))
        edits += _set_entry(gid, line)
    elif status == "active":
        if not missed:
            quiet.append('<button type="button" class="tb" data-edit="e-set-%s">%s</button>' % (
                esc(gid), "Change target or date" if line else "Set a target and a date"))
            edits += _set_entry(gid, line)
        quiet.append('<button type="button" class="tb" data-edit="e-why-%s">Edit why</button>' % esc(gid))
        edits += _why_entry(gid, reading["why"])
        if not missed:
            quiet.append('<button type="button" class="tb"%s>Set aside</button>' % _attrs(data_act="aside", **_saves(gid)))
        quiet.append('<button type="button" class="tb"%s>Mark done</button>' % _attrs(data_act="done", **_saves(gid)))
    else:  # done or set aside
        quiet.append(_back(reading))
    parts.append(("auto", '<div class="ft"><p class="meta">%s<span class="qa">%s</span></p>%s</div>' % (
        meta, "".join(quiet), edits)))
    style += ";grid-template-rows:" + " ".join(size for size, _ in parts)  # its own rows: the plot's is the one that grows
    return "<section%s>%s</section>" % (_attrs(("t detail " + cls).strip(), style, id="d-" + gid, data_goal=gid, aria_labelledby="dn-" + gid,
                                               hidden=not shown), "".join(html for _, html in parts))


def _something_else():
    """The line under goals in hand that asks for another, as Goals' list draws it."""
    return '<p class="cl0" id="e-add">%s<span>%s</span></p>' % (icon("message"), esc(SOMETHING_ELSE))


def goals_panes(readings, tally_words="", record=(), today=None, selected=None, block="goals", said=None):
    """Goals' two panes: the list, and beside it every goal's detail, one of them showing. One goal in all is said
    once: its detail alone, with the line that asks for another under it."""
    rows = list(readings) + list(record)
    if not rows:  # day zero's one tile, with no explainer plot
        return '<section class="panes one" data-block="%s">%s</section>' % (esc(block), goals_list((), tally_words, block=block))
    if len(rows) == 1:
        return '<section class="panes one" data-block="%s">%s<div class="addg">%s</div></section>' % (
            esc(block), goal_detail(rows[0], today, shown=True, you_said=(said or {}).get(rows[0]["id"])),
            _something_else())
    if selected not in [r["id"] for r in rows]:
        selected = rows[0]["id"]
    details = "".join(goal_detail(r, today, shown=r["id"] == selected, you_said=(said or {}).get(r["id"]))
                      for r in rows)
    return '<section class="panes" data-block="%s">%s%s</section>' % (esc(block), goals_list(readings, tally_words, record, selected, block), details)


def place_of(root):
    """The person's place, {"lat", "lon"}, from <root>/hydra/home/you.json's "place" ({"city", "lat", "lon"}), which
    Claude saves with their yes; None without one. Every page passes it to
    document(), so the sky follows the same sun on every page."""
    you = read_json(os.path.join(root, "hydra", "home", "you.json"), {}) if root else {}
    got = you.get("place") if isinstance(you, dict) else None
    if not isinstance(got, dict) or not _is_number(got.get("lat")) or not _is_number(got.get("lon")):
        return None
    if not (-90 <= got["lat"] <= 90 and -180 <= got["lon"] <= 180):
        return None
    return {"lat": got["lat"], "lon": got["lon"]}


# Tips, not a tour. A page's own tips
# come from its column.json, "tips": [{"id", "block", "at", "text", "when"}], at most three: each one line on its part.
# The kit's script shows them one at a time, at most one a visit, each once, anchored to its part and closed with x;
# Home's server keeps what was seen (POST /api/tips/seen, yours/settings.json "tips"), and a seen tip isn't drawn again.
TIP_AT = ("block", "acts", "field", "drop")  # the block's heading, its first item's buttons, its add field, its drop place
TIP_WHEN = ("data", "first-visit", "day-2", "day-3", "after-review")
TIP_MOST = 3
TIP_LONGEST = 90
TIP_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")  # lowercase letters, digits and dashes


def tips_of(declared, seen=(), most=TIP_MOST, blocks=None):
    """A page's tips as its column.json declares them, the first `most`, those whole, in order, minus those seen:
    [{"id", "block", "at", "text", "when"}]. A tip's text is one plain line of at most 90 characters, and its block one
    the page has (`blocks`, when given)."""
    out = []
    for t in (declared if isinstance(declared, list) else [])[:most]:
        t = t if isinstance(t, dict) else {}
        tip = {"id": t.get("id"), "block": t.get("block"), "at": t.get("at") or "block", "text": plain(t.get("text")), "when": t.get("when") or "data"}
        whole = (isinstance(tip["id"], str) and TIP_ID.fullmatch(tip["id"]) and isinstance(tip["block"], str) and ID.fullmatch(tip["block"])
                 and (blocks is None or tip["block"] in blocks)
                 and tip["at"] in TIP_AT and tip["when"] in TIP_WHEN and 0 < len(tip["text"]) <= TIP_LONGEST)
        if whole and tip["id"] not in seen and all(x["id"] != tip["id"] for x in out):
            out.append(tip)
    return out


def installed_on(root):
    """The day Hydra-OS was set up on this Mac, from <root>/hydra/config.json's installed_at, or None."""
    cfg = read_json(os.path.join(root, "hydra", "config.json"), {}) if root else {}
    at = moment(cfg.get("installed_at")) if isinstance(cfg, dict) else None
    return at.date() if at else None


def tip_due(tip, today, since=None, reviewed=False):
    """Whether a tip may show today: "day-2" from setup's second day and "day-3" from its third, "after-review" once a
    morning review has run, the others always. The kit's script holds a "data" tip until its block has data."""
    if tip["when"] in ("day-2", "day-3"):
        return since is not None and (today - since).days >= (1 if tip["when"] == "day-2" else 2)
    return reviewed if tip["when"] == "after-review" else True


def tips_html(app_id, tips):
    """The page's tips, hidden, in order, for the kit's script: each its id, its block, where on it, when, and its line.
    Home's own may name their part by a selector of their own ("sel")."""
    if not tips:
        return ""
    return '<ol class="tips" hidden data-app="%s">%s</ol>' % (esc(app_id), "".join(
        '<li data-tip="%s" data-for="%s" data-at="%s" data-when="%s"%s>%s</li>' % (
            esc(t["id"]), esc(t.get("block") or ""), esc(t.get("at") or "block"), esc(t.get("when") or "data"),
            ' data-sel="%s"' % esc(t["sel"]) if t.get("sel") else "", esc(t["text"])) for t in tips))


# The Shop: the main app's catalog of pages to add, each explained, with where it stands, and the buying path: no
# price until the catalog gives one, and "Get" only once a page has a checkout.
CATALOG = os.path.join(os.path.dirname(KIT), "home", "catalog.json")
SHOP_LINE = "Pages you can add to Hydra-OS."
SHOP_NONE = "Every page in the Shop is already in your rail."
SHOP_EMPTY = "No pages to add right now."  # while the catalog in force lists none for sale
ASK_ABOUT = "Ask Claude about it"


KEY_LABEL = "Have a key? Paste it here."
# Under the foot's line, quiet and plain
SHOP_AI = ("Hydra-OS uses Claude, an AI. Its answers can be wrong.", "Hydra-OS isn't affiliated with or endorsed by Anthropic.")
KEY_HINT = "Your key"  # a paste adds its page at once; Return sends a typed one
SHOP_PICTURES = os.path.join(os.path.dirname(KIT), "home", "shop")  # each catalog page's picture, light and dark
PICTURE_SIZE = (450, 312)  # as tests/shop_pictures.mjs makes them: the top of the page at 750 wide, at 0.6


def shop_price(page):
    """The catalog's price, in its own words ("$29, paid once"): one plain line of at most 40
    characters, never an address, else "" and the card shows none."""
    text = " ".join(str(page.get("price") or "").split()) if isinstance(page, dict) else ""
    return "" if len(text) > 40 or "://" in text or "www." in text else text


def shop_picture(page_id, title):
    """The card's picture of the page, drawn from made-up data, in the theme that's showing:
    the main app's home/shop/<id>-light.webp and -dark.webp, served beside the Shop. "" while it has none."""
    if not all(os.path.isfile(os.path.join(SHOP_PICTURES, "%s-%s.webp" % (page_id, t))) for t in ("light", "dark")):
        return ""
    # its own class: `.pic` is the goal plot's grid, which would draw this in a 2.75rem column
    return '<p class="spic">%s</p>' % "".join(
        '<img data-for="%s" src="/home/shop-%s-%s.webp" alt="%s" width="%d" height="%d" loading="lazy" decoding="async">' % (
            t, esc(page_id), t, esc("%s's page, drawn from made-up data" % title), PICTURE_SIZE[0], PICTURE_SIZE[1]) for t in ("light", "dark"))
SHOP_STATE = {"in-rail": "In your rail", "needs-hydra": "Update Hydra-OS first."}  # and "<Page> <version> is ready"
_VERSION = re.compile(r"\d{1,4}(\.\d{1,4}){0,3}")
MAIN_VERSION = str((read_json(os.path.join(os.path.dirname(KIT), ".claude-plugin", "plugin.json"), {}) or {}).get("version") or "")


def _vt(version):
    """A version as a tuple of numbers, for comparing as the shop does (hydralib/shop.py); () for one that isn't."""
    return tuple(int(x) for x in version.split(".")) if isinstance(version, str) and _VERSION.fullmatch(version) else ()


def shown_version(version):
    """A version as the Shop says it: 1.2.0 as 1.2."""
    return re.sub(r"^(\d+\.\d+)\.0$", r"\1", str(version or ""))


def shop_doc(root=None):
    """The catalog in force: <root>/hydra/shop/catalog.json, the daily read's copy, when it's
    there and whole; otherwise the main app's own (catalog/v1)."""
    for path in ([os.path.join(root, "hydra", "shop", "catalog.json")] if root else []) + [CATALOG]:
        got = read_json(path, None)
        if isinstance(got, dict) and got.get("contract") == "catalog/v1" and isinstance(got.get("pages"), list):
            return got
    return {"contract": "catalog/v1", "pages": []}


def bought(root):
    """The pages added from the Shop, {id: version}, from <root>/hydra/shop/bought.json."""
    doc = read_json(os.path.join(root, "hydra", "shop", "bought.json"), {}) if root else {}
    pages = doc.get("pages") if isinstance(doc, dict) else None
    return {k: v["version"] for k, v in pages.items() if isinstance(v, dict) and _vt(v.get("version"))} if isinstance(pages, dict) else {}


def on_sale(page):
    """Whether the catalog in force lists a page for sale: its pack and its sha256 both given.
    A card goes in early with its buying fields empty, and until the signed catalog lists its pack it
    never shows: no card, no placeholder, and no Shop in the rail for it."""
    return isinstance(page, dict) and all(isinstance(page.get(k), str) and page[k].strip() for k in ("pack", "sha256"))


def catalog(apps, root=None, every=False):
    """The Shop's pages, from the catalog in force: those on sale (on_sale) that aren't installed, or with `every` all
    of those on sale. Each {"id", "title", "icon", "accent", "does", "for_goal", "fits", "reads", "needs", "version",
    "pack", "sha256", "checkout", "min_hydra"}. [] for a page built with no registry."""
    if apps is None:
        return []
    return [p for p in shop_doc(root)["pages"] if isinstance(p, dict) and isinstance(p.get("id"), str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", p["id"])
            and (every or p["id"] not in apps) and all(isinstance(p.get(k), str) and p[k].strip() for k in ("title", "does", "reads", "needs"))
            and on_sale(p)]


def shop_state(page, installed, have, hydra=None):
    """Where a catalog page stands, as Home's server says it: "update" (a newer version of a
    page added from the Shop is ready), "in-rail" (added from the Shop, or installed with the rest), "needs-hydra"
    (Update Hydra-OS first), "not-ready" (no pack yet, so it isn't on sale and has no card) or "available". `have` is
    bought(root)."""
    hydra = MAIN_VERSION if hydra is None else hydra
    had = have.get(page["id"], "")
    if had and _vt(page.get("version")) > _vt(had):
        return "update"
    if had or page["id"] in installed:
        return "in-rail"
    if page.get("min_hydra") and _vt(hydra) and _vt(hydra) < _vt(page["min_hydra"]):
        return "needs-hydra"
    return "available" if page.get("pack") and page.get("sha256") else "not-ready"


def shop_open(apps, root=None):
    """Whether the rail shows the Shop: while a catalog page isn't in the rail, or while a newer version of one added
    from the Shop is ready, since its Update is there."""
    if apps is None:
        return False
    have = bought(root)
    return any(shop_state(p, apps, have) != "in-rail" for p in catalog(apps, root, every=True))


def shop_body(pages, readings, installed=(), have=None, foot="", pending=()):
    """The Shop page. Its header, then a card per page on sale (on_sale): what it does (in your
    own goal's words when one fits: a goal its page measures, or one in a unit it counts), what it reads and what it
    needs, and where it stands beside its name ("In your rail", "Finance 1.2 is ready", "Update Hydra-OS first."). The
    pages to add come first, in the catalog's order, then any with an update ready, then those already in the rail, which
    the stylesheet draws as one slim row.
    "Get <Page>" shows only while it's on sale with a checkout, and opens the checkout in your own browser; Update
    shows while a newer version is ready; "Ask Claude about it" files an `about` request. A page in the rail that
    hasn't run yet (`pending`, its ids) has "Set up <Page>", which hands Claude a `setup` request. Then the
    foot: the catalog's line and "Have a key? Paste it here." Home's own script (home/shop.js) keeps each card's state
    from Home's server. `have` is bought(root). Returns (header, main)."""
    have = have or {}
    pages = [p for p in pages if on_sale(p)]  # a card with empty buying fields never shows
    head = ('<section data-block="header"><h1 class="crumb"><a href="/" target="_top">Home</a><i aria-hidden="true">/</i>'
            '<span>Shop</span></h1><p class="sub">%s</p></section>') % esc(
        SHOP_LINE if any(p["id"] not in installed and p["id"] not in have for p in pages) else SHOP_NONE if pages else SHOP_EMPTY)
    cards = ""
    last = {"update": 1, "in-rail": 2}  # sorted() keeps the catalog's order within each
    for p in sorted(pages, key=lambda p: last.get(shop_state(p, installed, have), 0)):
        units = p["fits"].get("units") if isinstance(p.get("fits"), dict) and isinstance(p["fits"].get("units"), list) else []
        fit = next((r for r in readings if r.get("app") == p["id"] or (r.get("unit") and r.get("unit") in units)), None)
        said = p.get("for_goal") if isinstance(p.get("for_goal"), str) and "{goal}" in p["for_goal"] else ""
        does = said.replace("{goal}", fit["text"]) if fit and said else p["does"]
        state = shop_state(p, installed, have)
        sale = state == "available" and str(p.get("checkout") or "").startswith("https://")
        line = SHOP_STATE.get(state) or ("%s %s is ready" % (p["title"], shown_version(p.get("version"))) if state == "update" else "")
        price = shop_price(p) if state not in ("in-rail", "update") else ""  # the catalog's; none once it's in the rail
        cls, style = tint(p["id"], p.get("accent"))
        setup = ('<p class="act0 su"><button type="button" class="cta" data-connect data-kind="setup" data-app="%s">Set up %s</button></p>'
                 % (esc(p["id"]), esc(p["title"])) if state == "in-rail" and p["id"] in pending else "")
        cards += ('<article%s><header class="ch"><h2>%s%s</h2><span class="st" data-line>%s</span></header>%s<div class="sw"><p class="say">%s</p>'
                  '<p class="via">%s</p><p class="via">%s</p>%s<p class="act0"><button type="button" class="cta" data-get%s>Get %s</button>'
                  '<button type="button" class="cta" data-update%s>Update</button>'
                  '<button type="button" class="%s" data-connect data-kind="about" data-app="%s">%s</button></p>%s'
                  '<p class="said" data-said role="status" aria-live="polite"></p></div></article>') % (
            _attrs(" ".join(c for c in ("t", "sc", cls) if c), style, id="s-" + p["id"], data_page=p["id"], data_title=p["title"], data_state=state),
            icon(p.get("icon") or "apps"), esc(p["title"]), esc(line), shop_picture(p["id"], p["title"]), esc(does), esc(p["reads"]), esc(p["needs"]),
            '<p class="price">%s</p>' % esc(price) if price else "",
            "" if sale else " hidden", esc(p["title"]), "" if state == "update" else " hidden",
            "alt" if sale or state == "update" else "cta", esc(p["id"]), esc(ASK_ABOUT), setup)
    if not cards:
        return head, ""
    foot = foot.strip() if isinstance(foot, str) else ""
    key = '<section class="t sf">%s%s%s<p class="said" id="shop-said" role="status" aria-live="polite"></p></section>' % (
        '<p class="via">%s</p>' % esc(foot) if foot else "", "".join('<p class="via">%s</p>' % esc(t) for t in SHOP_AI),
        field("shop-key", KEY_LABEL, KEY_HINT, maxlength=160, button=""))
    return head, '<section class="shop" data-block="shop" aria-label="Pages you can add">%s</section>\n%s' % (cards, key)


def rail_apps(apps):
    """The installed apps the rail holds, after Home, in the kit's order (APPS): every registry app but the main one."""
    order = list(APPS)
    return sorted((i for i, a in apps.items() if a.get("kind") != "main"), key=lambda i: order.index(i) if i in order else len(order))


def rail(apps, current, root=None):
    """Every page's own slim left rail: Home, then each installed app in the rail's order (rail_apps), each opening its own
    page in the same tab, the current one marked. Its labels are the registry's titles.

    apps     the registry's apps by id (registry_apps), or None for a page built with no root, which has no rail.
    current  "home", "shop", or the id of the app whose page it is.
    root     the Hydra-OS folder, for the catalog in force and what was added from the Shop.
    """
    if apps is None:
        return ""
    ids = rail_apps(apps)
    links = ['<a href="/" target="_top"%s>%s<span class="lbl">Home</span></a>' % (
        _attrs("on" if current == "home" else "", "", aria_current="page" if current == "home" else None), icon("home"))]
    for app_id in ids:
        entry = apps[app_id]
        cls, style = tint(app_id, entry.get("accent"))
        on = current == app_id
        links.append('<a href="/%s/" target="_top"%s>%s<span class="lbl">%s</span></a>' % (
            esc(app_id), _attrs(" ".join(c for c in (cls, "on" if on else "") if c), style, aria_current="page" if on else None),
            icon(app_icon(app_id, entry.get("icon"))), esc(entry.get("title") or app_id[:1].upper() + app_id[1:])))
    if current == "shop" or shop_open(apps, root):  # the Shop, set apart at the rail's foot, while it has something to do
        links.append('<a href="/shop/" target="_top"%s>%s<span class="lbl">Shop</span></a>' % (
            _attrs("shop on" if current == "shop" else "shop", "", aria_current="page" if current == "shop" else None), icon("store")))
    on = current == "help"  # Help, the ? at the rail's very foot, on every page
    links.append('<a href="/help/" target="_top"%s>%s<span class="lbl">Help</span></a>' % (
        _attrs("help on" if on else "help", "", aria_current="page" if on else None), icon("help")))
    return ('<div class="rail"><nav class="nav" aria-label="Your pages"><div class="mark"><b aria-hidden="true"></b>'
            '<span class="lbl">Hydra-OS</span></div>%s</nav></div>') % "".join(links)


def document(app_id, title, body, accent=205, built_at="", run="by-hand", as_of="", appearance="sun", place=None,
             contract="v4", styles=(), scripts=(), policy=POLICY, rail=""):
    """A whole page: the kit's head, the sky, the rail, the body, and the kit's
    script last.

    styles and scripts are extra files for a page that isn't an app's, which is Home's alone. rail is rail()'s markup.
    """
    try:
        hue = int(accent) % 360
    except (TypeError, ValueError):
        hue = 205
    where = ""
    if place and _is_number(place.get("lat")) and _is_number(place.get("lon")):
        where = ' data-lat="%s" data-lon="%s"' % (_f(place["lat"]), _f(place["lon"]))
    head = [
        "<!doctype html>",
        '<html lang="en" style="--hue:%d">' % hue,
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        '<meta name="color-scheme" content="light dark">',
        '<meta http-equiv="Content-Security-Policy" content="%s">' % policy,
        '<meta name="referrer" content="no-referrer">',
        '<meta name="robots" content="noindex, nofollow">',
        '<meta name="page-contract" content="%s">' % esc(contract),
        '<meta name="pillar" content="%s">' % esc(app_id),
        '<meta name="built-at" content="%s">' % esc(built_at),
        '<meta name="run" content="%s">' % esc(run),
        '<meta name="as-of" content="%s">' % esc(as_of),
        "<title>%s</title>" % esc(title),
        '<link rel="stylesheet" href="/kit/style.css">',
    ]
    head += ['<link rel="stylesheet" href="%s">' % esc(s) for s in styles]
    head.append("</head>")
    tail = ['<script src="/kit/app.js"></script>'] + ['<script src="%s"></script>' % esc(s) for s in scripts]
    return "\n".join(head) + '\n<body data-app="%s" data-appearance="%s"%s>\n' % (esc(app_id), esc(appearance), where) + (
        '<div class="sky" aria-hidden="true"><i class="stars"></i></div>\n%s<div class="wrap">\n%s\n</div>\n%s\n</body>\n</html>\n'
        % (rail + "\n" if rail else "", body, "\n".join(tail)))


# ---------------------------------------------------------------------------------------------------------------
# The block renderer: an app's page from its layout, its say.json and its datasets

def preview_of(root, app_id):
    """The layout Claude proposed for a page, waiting on Keep or Undo:
    <root>/hydra/panel/preview.json while it names this page, {"layout", "change", "blocks"}, else None. `hydra yours`
    writes it, and Home's server drops it on Keep, Undo or after 30 minutes."""
    doc = read_json(os.path.join(root, "hydra", "panel", "preview.json"), None) if root else None
    if not isinstance(doc, dict) or doc.get("app") != app_id or not isinstance(doc.get("layout"), dict):
        return None
    return {"layout": doc["layout"], "change": plain(doc.get("change")) or "This page has a new layout.",
            "blocks": [b for b in doc.get("blocks") or [] if isinstance(b, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", b)]}


def layout_bar(app_id, preview):
    """The layout-changed bar: the change in one line, then Keep and Undo. It belongs to no
    block, and sits at the foot of the window while the page is read; the kit's script outlines the changed blocks."""
    return ('<div class="t lbar" role="region" aria-label="This page\'s new layout" data-yours="%s" data-blocks="%s"><p class="lch">%s</p>'
            '<p class="act0"><button type="button" class="cta" data-yours-keep>Keep</button><button type="button" class="alt" data-yours-drop>Undo</button></p>'
            '<p class="said" role="status" aria-live="polite"></p></div>') % (esc(app_id), esc(" ".join(preview["blocks"])), esc(preview["change"]))


def lay_out(stock, yours=None):
    """The stock layout with the person's own laid over it: order, hidden, widths, titles and added blocks.

    A layout naming a block stock doesn't have falls back to stock for that block, but where stock's `was` names that
    block's new id, {"old-id": "new-id"}, the person's order, hidden, width and title follow it.
    Fixed blocks never move or hide.
    """
    blocks = [dict(b) for b in (stock or {}).get("blocks") or [] if isinstance(b, dict)]
    seen = set()
    for b in blocks:
        if not isinstance(b.get("id"), str) or not b["id"] or b["id"] in seen:
            raise KitError("every block has its own id, and %r is missing or used twice" % b.get("id"))
        if b.get("type") not in TYPES:
            raise KitError("the kit doesn't draw a %r block yet (%s). Ask Home to add it." % (b.get("type"), b["id"]))
        if b.get("width", "full") not in WIDTHS:
            raise KitError("a block's width is full, half or third, and %s has %r" % (b["id"], b.get("width")))
        seen.add(b["id"])
    for kind in FIXED:
        have = [b for b in blocks if b["type"] == kind]
        if len(have) != 1:
            raise KitError("a page has one %s block, and this layout has %d" % (kind, len(have)))
        for b in have:
            b["fixed"] = True
    if not isinstance(yours, dict):
        return blocks
    was = (stock or {}).get("was") if isinstance((stock or {}).get("was"), dict) else {}
    if was:  # a release renamed a block: what the person set for its old id is the new id's
        here = {b["id"] for b in blocks}
        moved = lambda i: was[i] if isinstance(i, str) and i in was and i not in here and was[i] in here else i
        yours = dict(yours, order=[moved(i) for i in yours.get("order") or []], hidden=[moved(i) for i in yours.get("hidden") or []],
                     widths={moved(k): v for k, v in (yours.get("widths") or {}).items()} if isinstance(yours.get("widths"), dict) else {},
                     titles={moved(k): v for k, v in (yours.get("titles") or {}).items()} if isinstance(yours.get("titles"), dict) else {})
    for extra in yours.get("added") or []:
        if isinstance(extra, dict) and isinstance(extra.get("id"), str) and extra["id"] not in seen and extra.get("type") in TYPES \
                and extra["type"] not in FIXED and extra.get("width", "full") in WIDTHS:
            blocks.insert(max(i for i, b in enumerate(blocks) if b["type"] != "questions" and b["type"] != "connections") + 1, dict(extra))
            seen.add(extra["id"])
    hidden = set(yours.get("hidden") or [])
    widths, titles = yours.get("widths") or {}, yours.get("titles") or {}
    for b in blocks:
        if b.get("fixed"):
            continue
        if widths.get(b["id"]) in WIDTHS:
            b["width"] = widths[b["id"]]
        if isinstance(titles.get(b["id"]), str) and titles[b["id"]].strip():
            b["title"] = titles[b["id"]].strip()
    order = [i for i in yours.get("order") or [] if i in seen]
    movable = [b for b in blocks if not b.get("fixed") and b["id"] not in hidden]
    if order:
        place = {i: n for n, i in enumerate(order)}
        movable.sort(key=lambda b: (place.get(b["id"], len(place)), 0))
    by_type = {b["type"]: b for b in blocks if b.get("fixed")}
    return [b for b in (by_type.get("header"), by_type.get("goals")) if b] + movable + [b for b in (by_type.get("questions"), by_type.get("connections")) if b]


AGAIN_SLOT = "<!--kit:again-->"  # where Connections' drop place goes; no app's words can make it, since every one is escaped


class Page(object):
    """One app's page, drawn from its layout. html() gives the page and summary() what it says, from one pass.

    column    the app's column.json: its id, title, accent, home and actions.
    layout    its stock layout.json (layout/v1).
    say       its say.json, or None while it's just installed.
    data      its datasets by name, as page.py worked them out.
    root      <root>, for the registry, yours/ and the other apps' names. None draws without them.
    now       the build's moment, with its offset. run is the run's started_at, or "by-hand".
    answers   what was typed for each answered words question, by its id: the app's own, from its own record.
    move      the one thing the person must do for the app to work, in plain words, or "".
    yours     the person's own layout for this page, or None.
    """

    def __init__(self, column, layout, say=None, data=None, root=None, now=None, run="by-hand", answers=None, move="", yours=None,
                 names=None):
        self.column = column or {}
        self.names = names if isinstance(names, dict) else {}  # {"project": {id: words}}: Claude asks' {project} (fill_names)
        self.app = self.column.get("id") or ""
        if not self.app:
            raise KitError("column.json has no id")
        self.title = self.column.get("title") or self.app.capitalize()
        self.home = self.column.get("home") if isinstance(self.column.get("home"), dict) else {}
        self.say = say if isinstance(say, dict) else None
        self.new = self.say is None
        self._dropped, self._again = False, ""  # a block's day-zero drop place drawn; Connections' drop place, once the readings are in
        self.data = data or {}
        self.root = root
        self.now = now or _dt.datetime.now().astimezone()
        self.today = self.now.date()
        self.run = run
        self.answers = answers or {}
        self.move = move or ""
        self.preview = preview_of(root, self.app)  # Claude's proposed layout, drawn until Keep or Undo
        self.blocks = lay_out(layout, self.preview["layout"] if self.preview else yours)
        self.apps = registry_apps(root) if root else {}
        self.sources = [s for s in (sources_of(root) if root else []) if s["app"] == self.app]
        self.settings = settings_of(root) if root else {"appearance": "sun", "phone": False, "suggestions": True, "review": None}
        after = moment(self.say.get("stale_after")) if self.say else None
        self.stale = bool(after and self.now > after)
        self.as_of = (self.say.get("as_of") if self.say else None) or self.now.isoformat(timespec="seconds")
        mine = None if self.app == "goals" else self.app  # Goals' own page is every goal; another app's band is the goals it measures
        self.goals = read_goals(root, self.today, mine, self.now) if root else {"goals": [], "record": [], "tally": ""}
        # whether the person has any goal in hand, anywhere: the band's line for a first goal is only for no goal at all
        self.any_goals = bool(self.goals["goals"] if not mine or not root else read_goals(root, self.today, None, self.now)["goals"])
        self._drawn = None

    # What say.json gives a block

    def insight(self, block_id):
        """The block's conclusion line: the first insight that names it."""
        for i in (self.say or {}).get("insights") or []:
            if isinstance(i, dict) and i.get("block") == block_id and i.get("text"):
                return i
        return None

    def suggestions(self):
        """The suggestions that may show: none past stale_after, and none with suggestions off."""
        if self.new or self.stale or not self.settings["suggestions"]:
            return []
        return [s for s in self.say.get("suggestions") or [] if isinstance(s, dict) and s.get("text")][:3]

    def _review_off(self):
        """Where a suggestion would show and none does, the line says how to turn the morning review on: never on day
        zero, and never once the data is stale."""
        return review_off(self.settings) and not self.new and not self.stale

    def _suggestion_for(self, block_id):
        if any(b["type"] == "suggestions" for b in self.blocks):
            return None
        ids = {i.get("id") for i in (self.say or {}).get("insights") or [] if isinstance(i, dict) and i.get("block") == block_id}
        return next((s for s in self.suggestions() if s.get("answers") in ids and not s.get("goal")), None)

    def _goal_text(self, goal_id):
        return next((r["text"] for r in self.goals["goals"] + self.goals["record"] if r["id"] == goal_id), "")

    def _block_title(self, block_id):
        return next((b.get("title", "") for b in self.blocks if b["id"] == block_id), "")

    # The blocks

    def _header(self, block, data):
        lines = []
        if isinstance(data.get("line"), str) and data["line"].strip():  # the page's own line, by how its goals stand
            lines.append(" ".join(data["line"].split()))
        elif self.new and self.home.get("line"):
            lines.append(self.home["line"])
        if self.stale:
            as_of = moment(self.say.get("as_of"))
            lines.append("As of %s. Today's read hasn't come in." % weekday_day(as_of.date()) if as_of else "Today's read hasn't come in.")
        do, why, label = "", "", None
        if isinstance(self.move, dict) and isinstance(self.move.get("text"), str) and self.move["text"].strip():
            # every page leads here: the move, then its why as a quieter line; the
            # summary gets the move's label, never its words, which may hold what a summary can't (Inbox's subject)
            if not lines:
                label = plain(self.move.get("label"))
            lines.append(self.move["text"])
            why = plain(self.move.get("why"))
            href = page_link(self.move.get("link"), self.app)
            words = MOVE_DO.get(href[1:]) if href and href.startswith("#") else None
            if words:  # under the title, the move's one button: on Wellbeing's page, its drop place
                do = '<p class="hd-act"><a class="cta" href="%s">%s</a></p>' % (esc(href), esc(words))
        elif isinstance(self.move, str) and self.move:
            lines.append(self.move)
        out = ('<section data-block="%s"><h1 class="crumb"><a href="/" target="_top">Home</a><i aria-hidden="true">/</i>'
               '<span>%s</span></h1>%s%s%s%s</section>') % (esc(block["id"]), esc(self.title), "".join('<p class="sub">%s</p>' % esc(t) for t in lines),
                                                             '<p class="sub swhy">%s</p>' % esc(why) if why else "", do,
                                                             first_visit(data.get("hint"), "%s-page" % self.app, "sub hint"))
        return out, {"id": block["id"], "title": self.title, "says": label if label is not None else (lines[0] if lines else ""), "figures": [], "items": []}

    def _goals(self, block, data):
        if self.app == "goals":
            return self._panes(block, data)
        readings = self.goals["goals"]
        if not readings and self.any_goals:  # none of theirs counted here: the band stays quiet
            return "", None
        says = self.goals["tally"]
        out = goals_band(readings, says, page_app=self.app, new=self.new, block=block["id"], ask=not self.any_goals)
        figures = [{"label": r["text"], "value": " · ".join(x for x in (r["word"], r["caption"]) if x)} for r in readings]
        return out, {"id": block["id"], "title": "Goals", "says": says, "figures": figures,
                     "items": [{"id": r["id"], "label": r["text"]} for r in readings] if readings and not self.new else []}

    def _panes(self, block, data):
        """The kit's own `_panes`, with one more keyword: the page data's `said`, each goal's "You said"."""
        hand, record = self.goals["goals"], self.goals["record"]
        rows = hand + record
        out = goals_panes(hand, self.goals["tally"], record, self.today, selected=data.get("selected"), block=block["id"],
                          said=data.get("said") if isinstance(data.get("said"), dict) else None)
        figures = [{"label": r["text"], "value": " \u00b7 ".join(x for x in (r["word"], r["caption"]) if x)
                    if r["state"] != "new" else r["measured"]} for r in rows]
        return out, {"id": block["id"], "title": "Your goals", "says": self.goals["tally"], "figures": figures,
                     "items": [{"id": r["id"], "label": r["text"]} for r in rows]}

    def _lane(self, block):
        return '<div class="lane"><h2 class="h plate hh" id="h-%s">%s</h2></div>' % (esc(block["id"]), esc(block.get("title", "")))

    def _empty(self, data, symbol="apps"):
        empty = data.get("empty") if isinstance(data.get("empty"), dict) else {}
        action = drop = ""
        if empty.get("action") == "connect" and self.home.get("needs"):
            action = connect(self.app, self.home["needs"])
        elif empty.get("action") == "drop":  # the app's upload source, where it's wanted
            drop = self._drop_place(empty.get("drop") or "Drop your file here.", empty.get("hint"))
            self._dropped = True
        return empty_state(empty.get("icon") or symbol, empty.get("line") or "Nothing here yet.", action, empty.get("via", ""),
                           steps=empty.get("steps") or (), drop=drop, step=empty.get("step"), link=out_link(empty.get("link"), "cta"))

    def _drop_place(self, line, hint=None):
        source = upload_source(self.column)
        if source is None:
            raise KitError("a drop place needs an upload source in column.json, and %s has none" % self.app)
        return drop_place(self.app, source.get("accepts"), line, self.title, hint=hint)

    def _today(self, block, data):
        """Today's readings: up to four cards, each its symbol and name, today's figure, the finding, the 14 days, and its
        move when the data gives one, {"text", "why"}. Each card is a place to land,
        `#c-<card id>`, so a suggestion's link opens the page on the card it answers."""
        bid = block["id"]
        cards = [c for c in data.get("cards") or [] if isinstance(c, dict) and c.get("id")]
        if self.new or not cards:
            body = '<div class="t e0">%s</div>' % self._empty(data, app_icon(self.app, self.column.get("icon")))
            return ('<section data-block="%s" aria-labelledby="h-%s">%s%s</section>' % (esc(bid), esc(bid), self._lane(block), body),
                    {"id": bid, "title": block.get("title", ""), "says": (data.get("empty") or {}).get("line", ""), "figures": [], "items": []})
        if len(cards) > 4:
            raise KitError("a today block shows at most four readings, and %s has %d" % (bid, len(cards)))
        out, figures, items, moved = "", [], [], False
        for c in cards:
            fig = '<p class="fig"><b>%s</b>%s</p>' % (esc(c.get("value", "")), '<span class="u">%s</span>' % esc(c["unit"]) if c.get("unit") else "")
            days = dict(c.get("days") or {})
            days.setdefault("to", data.get("to"))
            move = c.get("move") if isinstance(c.get("move"), dict) and isinstance(c["move"].get("text"), str) and c["move"]["text"].strip() else None
            why = move["why"].strip() if move and isinstance(move.get("why"), str) else ""
            end = '<p class="mv"><b>%s</b>%s</p>' % (esc(move["text"].strip()), "<span>%s</span>" % esc(why) if why else "") if move else ""
            moved = moved or bool(move)
            note = '<p class="lnote">%s</p>' % esc(plain(c.get("note"))) if plain(c.get("note")) else ""
            pic = chart(days, to=self.today) if c.get("days") else ""  # a card with no days, as People's person, has no picture
            out += ('<article class="t rd" id="c-%s" data-item="%s"><header class="rh"><h3 class="kh">%s%s</h3>%s</header><p class="say">%s</p>%s%s%s%s</article>'
                    % (esc(c["id"]), esc(c["id"]), icon(c.get("icon") or "pulse"), esc(c.get("label", "")), fig if c.get("value") not in (None, "") else "",
                       esc(c.get("says", "")), note, pic, end, self._acts(c, card=True)))
            if c.get("value") not in (None, ""):
                figures.append({"label": c.get("label", ""), "value": "%s%s" % (c["value"], c.get("unit") or "")})
            items.append({"id": c["id"], "label": c.get("label", "")})
        lead = self.insight(bid)
        quiet = not moved and not self.suggestions() and self._review_off() and not any(b["type"] == "suggestions" for b in self.blocks)
        return ('<section data-block="%s" aria-labelledby="h-%s">%s<div class="row">%s</div>%s</section>' % (
                    esc(bid), esc(bid), self._lane(block), out, '<p class="t nrv">%s %s</p>' % (esc(REVIEW_OFF), REVIEW_ON) if quiet else ""),
                {"id": bid, "title": block.get("title", ""), "says": lead["text"] if lead else cards[0].get("says", ""),
                 "figures": figures, "items": items})

    def _entry(self, block, data):
        name = block.get("entry")
        if not name:
            return ""
        action = next((a for a in self.column.get("actions") or [] if isinstance(a, dict) and a.get("name") == name), None)
        if action is None:
            raise KitError("block %s names the entry %r, which column.json doesn't declare" % (block["id"], name))
        words = (action.get("fields") or {}).get("words") or {}
        if words.get("kind") != "words":
            raise KitError("an entry's action has one words field, and %r has none" % name)
        about = data.get("entry") if isinstance(data.get("entry"), dict) else {}
        try:
            most = max(1, min(120, int(words.get("max") or 120)))
        except (TypeError, ValueError):
            most = 120
        fixed = about.get("fixed") if isinstance(about.get("fixed"), dict) else {}
        ident = "e-" + block["id"]
        back = next((a for a in self.column.get("actions") or [] if isinstance(a, dict) and a.get("name") == action.get("undo")), None)
        takes = " ".join(sorted((back.get("fields") or {}).keys())) if back else ""
        return '<div class="ent"%s><div class="mf">%s</div>%s</div>' % (
            _attrs(id=ident, data_app=self.app, data_act=name, data_undo=action.get("undo") or "", data_takes=takes,
                   data_fixed=json.dumps(fixed, separators=(",", ":"))),
            field(ident + "-i", about.get("label") or name.replace("-", " ").capitalize(), about.get("placeholder") or "Say it in a line, then Return", most,
                  short=about.get("short") or ""),
            saved_line(ident + "-u"))

    def _section(self, block, data, body, items=(), figures=(), lead=None, live=False):
        """A section's frame: its title with what the engines brought, its entry, its finding, its picture, one caption.

        lead  the block's own first line, {"text", "why", "label"} (a list's), drawn in place of say.json's finding. The
              summary gets its `label`, never its text, which may hold what a summary can't, such as an email's subject.
        live  draw the body whenever there is one, even before the app's first run: a list's or a table's rows are only
              ever what the app gives, such as the person's own plan (Content's), so nothing made up can show."""
        bid = block["id"]
        found = self.insight(bid)
        says = found["text"] if found else ""
        mine = lead if isinstance(lead, dict) and plain(lead.get("text")) else None
        out = '<header class="fh"><h2 class="h hh" id="h-%s">%s</h2>%s</header>' % (esc(bid), esc(block.get("title", "")), "" if self.new else badges(data.get("badges")))
        out += self._entry(block, data)
        if (self.new and not live) or body is None:
            out += self._empty(data)
            says = (data.get("empty") or {}).get("line", "") if isinstance(data.get("empty"), dict) else ""
            items, figures = (), ()
        else:
            if mine:
                why = plain(mine.get("why"))
                out += '<p class="lead">%s</p>%s' % (esc(plain(mine["text"])), '<p class="lwhy">%s</p>' % esc(why) if why else "")
                says = plain(mine.get("label"))
            elif says:
                out += '<p class="lead">%s</p>' % esc(says)
            out += body
            hint = self._suggestion_for(bid)
            if hint:
                out += '<p class="sg"><b>%s</b> <span>%s</span></p>' % (esc(hint["text"]), esc(hint.get("why", "")))
            if data.get("caption"):
                out += '<p class="bcap">%s</p>' % esc(data["caption"])
        return ('<section class="t sec" id="%s" data-block="%s" aria-labelledby="h-%s">%s</section>' % (esc(bid), esc(bid), esc(bid), out),
                {"id": bid, "title": block.get("title", ""), "says": says, "figures": list(figures), "items": list(items)})

    def _chart(self, block, data):
        """A section with one picture. Its dataset's `kind` is "bars", the 14 days as bars, "days", the days as a grid, or
        "months", a bar a month (months_chart)."""
        kind = data.get("kind", "bars")
        if kind == "bars":
            if not data.get("values"):
                return self._section(block, data, None)
            days = dict(data)
            return self._section(block, data, chart(days, to=self.today, block_label=block.get("title")))
        if kind == "days":
            rows = [r for r in data.get("rows") or [] if isinstance(r, dict) and r.get("id")]
            if not rows:
                return self._section(block, data, None)
            return self._section(block, data, self._days(block, data, rows), items=[{"id": r["id"], "label": r.get("label", "")} for r in rows],
                                 figures=[{"label": r.get("label", ""), "value": r["count"]} for r in rows if r.get("count")])
        if kind == "months":
            if not data.get("series"):
                return self._section(block, data, None)
            return self._section(block, data, months_chart(data))
        raise KitError("a chart's kind is bars, days or months, and %s has %r" % (block["id"], kind))

    def _days(self, block, data, rows):
        last = day(data.get("to")) or self.today
        letters = "".join('<span%s>%s</span>' % (' class="now"' if i == 13 else "", WEEKDAYS[(last - _dt.timedelta(days=13 - i)).weekday()][0]) for i in range(14))
        out = '<div class="mr wd" aria-hidden="true"><span></span><span class="dz lb">%s</span><span></span></div>' % letters
        for r in rows:
            marks = list(r.get("marks") or [])
            if len(marks) != 14:
                raise KitError("a row of days has 14 marks, and %s has %d" % (r["id"], len(marks)))
            dots = "".join('<i%s></i>' % {"y": ' class="y"', "a": ' class="a"', "t": ' class="td"'}.get(m, "") for m in marks)
            out += '<div class="mr" aria-hidden="true" data-item="%s"><span class="nm">%s</span><span class="dz">%s</span><span class="ct">%s</span></div>' % (
                esc(r["id"]), esc(r.get("label", "")), dots, esc(r.get("count", "")))
        under = data.get("bars") if isinstance(data.get("bars"), dict) else None
        if under and under.get("values"):
            bars, axis = chart_parts(dict(under, to=data.get("to")), to=self.today)
            mark = '<i class="a"></i>' if under.get("count") and under.get("lit") else ""
            out += '<div class="mr rc" aria-hidden="true"><span class="nm">%s</span><div class="ins">%s</div><span class="ct">%s%s</span></div>' % (
                esc(under.get("label", "")), bars, mark, esc(under.get("count", "")))
            out += '<div class="mr axr" aria-hidden="true"><span></span>%s<span></span></div>' % axis
        return '<div class="wkm" role="img" aria-label="%s">%s</div>' % (esc(data.get("label") or block.get("title", "")), out)

    def _acts(self, item, card=False):
        """An item's own buttons:
        its `acts`, each {"action", "words", "fields"}, at most three. The action is one the app declares for a button
        (confirm "undo" or "read-back", never one that is only an undo), its words plain and at most 60 characters, and
        its fields only those the action declares, each an id, a listed choice or a day. Drawn as Goals' "Set it aside"
        is, which the kit's script saves: a card's first tinted and the rest quiet, a row's all quiet."""
        most = 3
        acts = item.get("acts")
        if acts is None or acts == []:
            return ""
        if not isinstance(acts, list) or len(acts) > most:
            raise KitError("%s carries at most %d of its own buttons, and %s has %s" % (
                "a card" if card else "a row", most, item.get("id"), len(acts) if isinstance(acts, list) else "something else"))
        declared = {a["name"]: a for a in self.column.get("actions") or [] if isinstance(a, dict) and isinstance(a.get("name"), str)}
        out = []
        for n, a in enumerate(acts):
            a = a if isinstance(a, dict) else {}
            decl = declared.get(a.get("action"))
            if decl is None or decl.get("confirm") not in ("undo", "read-back"):
                raise KitError("%s's button names %r, which %s doesn't declare as a button's action" % (item.get("id"), a.get("action"), self.app))
            words = plain(a.get("words"))
            if not words or len(words) > 60:
                raise KitError("a button's words are plain text of at most 60 characters, and %s's aren't" % item.get("id"))
            fields = {} if a.get("fields") is None else a.get("fields")
            spec = decl.get("fields") if isinstance(decl.get("fields"), dict) else {}
            if not isinstance(fields, dict):
                raise KitError("a button's fields are one object, and %s's aren't" % item.get("id"))
            for k, v in fields.items():
                f = spec.get(k) if isinstance(spec.get(k), dict) else {}
                kind = f.get("kind")
                if not isinstance(v, str) or not ((kind == "id" and ID.fullmatch(v)) or (kind == "choice" and v in (f.get("of") or []))
                                                  or (kind == "date" and DAY.fullmatch(v) and day(v))):
                    raise KitError("%s's button sends %s as %r, which isn't an id, a listed choice or a day %s declares" % (
                        item.get("id"), k, v, decl["name"]))
            out.append('<button type="button" class="%s"%s>%s</button>' % ("cta" if n == 0 and card else "alt", _attrs(
                data_app=self.app, data_act=decl["name"], data_fixed=json.dumps(fields, separators=(",", ":"), ensure_ascii=False),
                data_undo=decl.get("undo") or None, data_confirm="read-back" if decl.get("confirm") == "read-back" else None), esc(words)))
        return '<p class="lact">%s</p>' % "".join(out)

    def _list(self, block, data):
        """A list of rows. A row is
        {"id", "title", "label", "tag", "when", "line", "note", "move", "link", "acts"}: its title in the headline weight
        and a quiet tag, then its line, when and note in words, in that order so VoiceOver reads it as one sentence, its
        move ({"text", "why"}, as a card's), its link (out_link) and up to three buttons. The block's
        `lead` comes first, `ordered` numbers the rows, and at most 20 are drawn. The summary and a tap's focus get each
        row's `label`, else its title, never its line: a row whose title is private, such as an invite's, gives a label."""
        bid = block["id"]
        rows = [r for r in data.get("rows") or [] if isinstance(r, dict) and plain(r.get("id"))]
        if len(rows) > ROWS_MOST:
            raise KitError("a list draws at most %d rows, and %s has %d: its caption says how many more" % (ROWS_MOST, bid, len(rows)))
        if not rows:
            return self._section(block, data, None)
        out, items = "", []
        for r in rows:
            title = plain(r.get("title"))
            if not title:
                raise KitError("every row has a title, and %s's %s has none" % (bid, r["id"]))
            tag = plain(r.get("tag"))
            words = "".join('<p class="%s">%s</p>' % (cls, esc(plain(r.get(k)))) for k, cls in (("line", "ll"), ("when", "lw"), ("note", "lnote"))
                            if plain(r.get(k)))
            move = r.get("move") if isinstance(r.get("move"), dict) else {}
            why = plain(move.get("why"))
            mv = '<p class="mv"><b>%s</b>%s</p>' % (esc(plain(move.get("text"))), "<span>%s</span>" % esc(why) if why else "") if plain(move.get("text")) else ""
            link, acts = out_link(r.get("link")), self._acts(r)
            end = '<div class="lend">%s%s</div>' % ('<p class="llink">%s</p>' % link if link else "", acts) if link or acts else ""  # one line
            out += '<li class="lr" id="r-%s-%s" data-item="%s"><p class="lt"><b>%s</b>%s</p>%s%s%s%s</li>' % (
                esc(bid), esc(r["id"]), esc(r["id"]), esc(title), '<span class="ltag">%s</span>' % esc(tag) if tag else "", words,
                measures(r["measures"]) if r.get("measures") is not None else "", mv, end)
            items.append({"id": r["id"], "label": plain(r.get("label")) or title})
        kind = "ol" if data.get("ordered") is True else "ul"
        return self._section(block, data, '<%s class="lst">%s</%s>' % (kind, out, kind), items=items, lead=data.get("lead"), live=True)

    def _table(self, block, data):
        """A real table (Research's projects by its six questions, and How to sell it): `columns`, [{"id", "label"}], each
        a header; `rows`, [{"id", "label", "cells", "acts"}], each its label as the row's header, a cell for each column,
        and up to three buttons. A cell is {"state", "text"}: its look is its state's place in `key`,
        [{"state", "label"}], the first dashed, the second hatched, the third filled in the page's colour; its state is
        in words for VoiceOver, so none rests on its look; its few words show beside it. `key` is drawn under the table,
        and a narrow page scrolls the table in its own box. The summary and a tap's focus get each row's label."""
        bid = block["id"]
        cols = [c for c in data.get("columns") or [] if isinstance(c, dict) and plain(c.get("id")) and plain(c.get("label"))]
        rows = [r for r in data.get("rows") or [] if isinstance(r, dict) and plain(r.get("id")) and plain(r.get("label"))]
        key = [k for k in data.get("key") or [] if isinstance(k, dict) and plain(k.get("state")) and plain(k.get("label"))]
        if len(key) > 3 or len(cols) > 8 or len(rows) > ROWS_MOST:
            raise KitError("a table has at most three states in its key, eight columns and %d rows, and %s has %d, %d and %d" % (
                ROWS_MOST, bid, len(key), len(cols), len(rows)))
        if not rows or not cols:
            return self._section(block, data, None)
        look = {k["state"]: (i, plain(k["label"])) for i, k in enumerate(key)}
        acts = any(r.get("acts") for r in rows)
        head = '<thead><tr><td></td>%s%s</tr></thead>' % ("".join('<th scope="col">%s</th>' % esc(plain(c["label"])) for c in cols), "<td></td>" if acts else "")
        body, items = "", []
        for r in rows:
            cells = r.get("cells") if isinstance(r.get("cells"), list) else []
            if len(cells) != len(cols):
                raise KitError("a table's row has a cell for each column, and %s's %s has %d of %d" % (bid, r["id"], len(cells), len(cols)))
            tds = ""
            for c in cells:
                c = c if isinstance(c, dict) else {}
                state = plain(c.get("state"))
                if state not in look:
                    raise KitError("a cell's state is one its table's key names, and %r isn't" % state)
                n, said = look[state]
                text = plain(c.get("text"))
                tds += '<td class="tc s%d"><i class="tcm" aria-hidden="true"></i><span class="vh">%s.</span>%s</td>' % (
                    n, esc(said), '<span class="tcw">%s</span>' % esc(text) if text else "")
            body += '<tr id="t-%s-%s" data-item="%s"><th scope="row">%s</th>%s%s</tr>' % (
                esc(bid), esc(r["id"]), esc(r["id"]), esc(plain(r["label"])), tds, '<td class="tact">%s</td>' % self._acts(r) if acts else "")
            items.append({"id": r["id"], "label": plain(r["label"])})
        label = plain(data.get("label"))
        shown = '<p class="tkey" aria-hidden="true">%s</p>' % "".join(
            '<span class="s%d"><i class="tcm"></i>%s</span>' % (i, esc(said)) for i, said in sorted(look.values())) if key else ""
        table = '<div class="tblw"><table class="tbl"%s>%s<tbody>%s</tbody></table></div>%s' % (
            ' aria-label="%s"' % esc(label) if label else "", head, body, shown)
        return self._section(block, data, table, items=items, lead=data.get("lead"), live=True)

    def _note(self, block, data):
        """A section that is its finding and one caption alone."""
        body = "" if self.insight(block["id"]) or data.get("caption") else None
        return self._section(block, data, body)

    def _suggestions(self, block, data):
        hints = self.suggestions()
        bid = block["id"]
        if not hints:
            if not self._review_off():
                return "", None
            title = block.get("title") or "Claude suggests"
            return (('<section class="t sec" data-block="%s" aria-labelledby="h-%s"><h2 class="h hh" id="h-%s">%s</h2><p class="nrv">%s %s</p></section>')
                    % (esc(bid), esc(bid), esc(bid), esc(title), esc(REVIEW_OFF), REVIEW_ON), {"id": bid, "title": title, "says": REVIEW_OFF, "figures": [], "items": []})
        cells = "".join('<div class="nmv"><b>%s</b><span>%s</span></div>' % (esc(s["text"]), esc(s.get("why", ""))) for s in hints)
        out = ('<section class="t sec" data-block="%s" aria-labelledby="h-%s"><h2 class="h hh" id="h-%s">%s</h2>'
               '<div class="sgs" style="--n:%d">%s</div></section>') % (esc(bid), esc(bid), esc(bid), esc(block.get("title") or "Claude suggests"), max(2, len(hints)), cells)
        return out, {"id": bid, "title": block.get("title") or "Claude suggests", "says": hints[0]["text"], "figures": [], "items": []}

    def _questions(self, block, data):
        if data.get("hidden"):  # Goals' page data hides Claude asks before any goal
            return "", None
        texts = {r["id"]: r["text"] for r in self.goals["goals"] + self.goals["record"]}
        shown = [fill_goal(q, texts) for q in (self.say or {}).get("questions") or [] if isinstance(q, dict) and q.get("id") and q.get("text")]
        shown = [q for q in shown if q]
        shown = [q for q in (fill_names(q, self.names) for q in shown) if q]  # {project}, from the app's own names (Research's)
        open_ones = [q for q in shown if not isinstance(q.get("answer"), dict)][:3]
        shown = [q for q in shown if isinstance(q.get("answer"), dict) or q in open_ones]
        items = []
        for q in shown:
            goal = next((r for r in self.goals["goals"] + self.goals["record"] if r["id"] == q.get("goal")), None)
            where = self._block_title(q.get("block"))
            if self.app == "goals":  # the page that asks, as Home names it: "Goals · Swim twice a week"
                where = self.title
            tag = " \u00b7 ".join(t for t in (where, goal["text"] if goal else "") if t)
            items.append(question(q, self.app, tag=tag, accent=self.column.get("accent"), words=self.answers.get(q["id"])))
        note = data.get("note", "") if shown else ""
        if not shown:  # before the app's first run, its own line for when Claude will ask ("before"), else the kit's
            note = (data.get("before") or "") if self.new else "Nothing to ask today."  # one (ASKS_NONE); after it, a quiet day
        out = asks(items, note=note, block=block["id"])
        return out, {"id": block["id"], "title": "Claude asks", "says": "", "figures": [],
                     "items": [{"id": q["id"], "label": q["text"]} for q in shown]}

    def _counts(self, block, data):
        """"What counts your goals" and Wellbeing's "Where this comes from": the data's `title` and one row each, with no "Internal", "External" or run line. A row's `app` is named
        and linked by its registry entry, says "Counted to <day>." from its `counted_to`, and takes its `do` as the kit's
        tinted action under its words; a row's `name` is plain, a colon after it; a row's `line` is drawn as it's written.
        Under the rows, a newer file's place from `drop` once the app has run, as Connections has it, then the `foot`."""
        bid, items = block["id"], ""
        for row in data.get("rows") or []:
            if not isinstance(row, dict):
                continue
            if row.get("app"):
                reg = self.apps.get(row["app"])
                if not reg:
                    continue  # an app that isn't installed counts nothing here
                cls, style = tint(row["app"], reg.get("accent"))
                to = day(row.get("counted_to") or "")
                said = "%s.%s" % (row.get("what", ""), " Counted to %s." % weekday_day(to) if to else "")
                do = row.get("do") if isinstance(row.get("do"), dict) and row["do"].get("words") else None
                act = ('<a class="cta" href="%s" target="_top">%s</a>' % (
                    esc(page_link(do.get("link") or "")), esc(do["words"])) if do else "")
                items += '<li%s>%s<span><a href="/%s/" target="_top">%s</a>: %s</span>%s</li>' % (
                    _attrs(cls, style), icon(app_icon(row["app"], reg.get("icon"))), esc(row["app"]),
                    esc(reg.get("title") or row["app"].capitalize()), esc(said), act)
            elif row.get("name"):
                items += "<li>%s<span><b>%s</b>: %s.</span></li>" % (
                    icon(row.get("icon") or "pencil"), esc(row["name"]), esc(row.get("what", "")))
            elif isinstance(row.get("line"), str) and row["line"].strip():
                items += "<li>%s<span>%s</span></li>" % (icon(row.get("icon") or "pencil"), esc(row["line"].strip()))
        again = data.get("drop").strip() if isinstance(data.get("drop"), str) else ""
        if again and not self.new:  # a newer file's place, as Connections has it (_draw fills the slot)
            self._again = self._drop_place(again)
        foot = data.get("foot").strip() if isinstance(data.get("foot"), str) else ""
        title = data.get("title") or "What counts your goals"
        out = ('<section class="t conn" data-block="%s" aria-labelledby="h-%s"><h2 id="h-%s">%s</h2><ul class="cn">%s</ul>%s%s'
               "</section>") % (esc(bid), esc(bid), esc(bid), esc(title), items, AGAIN_SLOT if again and not self.new else "",
                                '<p class="lim">%s</p>' % esc(foot) if foot else "")
        return out, {"id": bid, "title": title, "says": foot, "figures": [], "items": []}

    def _connections(self, block, data):
        """"Where this comes from": one list, as Wellbeing's, with no "Internal" or
        "External", whatever the page passes. A page's own `rows` are drawn as given (_counts). Otherwise the kit makes
        them: each recorded source by the name the page's column.json declares for its id, and the recorded text only for
        an id it doesn't declare, or before any, what the page waits on with its Connect; then the pages
        and things that feed this one; then the person's own answers. Under them, a newer file's place and the run line."""
        if isinstance(data.get("rows"), list):  # Goals' "What counts your goals", Wellbeing's own rows
            return self._counts(block, data)
        bid, items = block["id"], ""
        declared = {s["id"]: (s.get("name") or s.get("source") or "").strip() for s in self.column.get("sources") or []
                    if isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("name") or s.get("source") or "", str)}
        via_icons = {"connector": "world", "api": "world", "browser": "world", "mac": "apps", "file": "file", "typed": "pencil"}
        hints = {r.get("service"): r for r in data.get("external") or [] if isinstance(r, dict) and r.get("service")}
        by_id = {r["id"]: r for r in data.get("external") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)}
        if self.sources:
            merged = []
            for s in self.sources:
                name = declared.get(s.get("id")) or s.get("source", "")
                same = next((m for m in merged if m["name"] == name and m["reads"] == s.get("reads")), None)
                if same:
                    same["accounts"].append(s.get("account") or "")
                else:
                    merged.append({"name": name, "source": s.get("source", ""), "reads": s.get("reads", ""), "via": s.get("via"),
                                   "accounts": [s.get("account") or ""], "id": s.get("id")})
            for m in merged:
                accounts = [a for a in m["accounts"] if a]
                who = ", " + (" and ".join(accounts) if len(accounts) < 3 else ", ".join(accounts[:-1]) + " and " + accounts[-1]) if accounts else ""
                hint = by_id.get(m["id"]) or hints.get(m["source"]) or hints.get(m["name"]) or {}
                what = m["reads"] or hint.get("what", "")
                if m["id"] == "":
                    what = "recorded, and %s can't read it yet" % self.title
                items += "<li>%s<span><b>%s</b>%s%s</span></li>" % (icon(hint.get("icon") or via_icons.get(m["via"], "world")), esc(m["name"]), esc(who),
                                                                    esc(": " + what if what else ""))
        else:
            plain = file_only(self.column)  # its one way in is its drop place, so no line here files a request
            for row in data.get("external") or []:
                if not isinstance(row, dict) or not (row.get("service") or row.get("name")):
                    continue
                name = row.get("service") or row["name"]
                button = connect(self.app, "Connect", service=row["service"], label="Connect " + row["service"]) if row.get("service") and not plain else ""
                items += "<li>%s<span><b>%s</b>%s%s</span>%s</li>" % (icon(row.get("icon") or "world"), esc(name), esc(", " + row["how"]) if row.get("how") else "",
                                                                       esc(": " + row["what"] if row.get("what") else ""), button)
        for row in data.get("internal") or []:
            if not isinstance(row, dict):
                continue
            if row.get("app"):
                reg = self.apps.get(row["app"])
                name = (reg or {}).get("title") or row["app"].capitalize()
                cls, style = tint(row["app"], (reg or {}).get("accent"))
                link = '<a href="/%s/" target="_top">%s</a>' % (esc(row["app"]), esc(name)) if reg else "<b>%s</b>" % esc(name)
                items += "<li%s>%s<span>%s: %s</span></li>" % (_attrs(cls, style), icon(app_icon(row["app"], (reg or {}).get("icon"))), link, esc(row.get("what", "")))
            elif row.get("name"):
                items += "<li>%s<span><b>%s</b>%s%s</span></li>" % (icon(row.get("icon") or "pencil"), esc(row["name"]),
                                                                    esc(", " + row["how"]) if row.get("how") else "", esc((": " + row["what"]) if row.get("what") else ""))
        items += "<li>%s<span>Your answers to Claude asks</span></li>" % icon("pencil")
        # Once the readings are in, a newer file has its own place here: the app's `drop` line, drawn once the app has
        # run and only when no block's empty state holds the first one (_draw fills the slot when every block is in).
        again = data.get("drop").strip() if isinstance(data.get("drop"), str) else ""
        if again and not self.new:
            self._again = self._drop_place(again)
        ran = self._run_line()
        last = " ".join(t for t in (data.get("never", ""), ran) if t)
        title = data.get("title") or "Where this comes from"
        out = ('<section class="t conn" data-block="%s" aria-labelledby="h-%s"><h2 id="h-%s">%s</h2><ul class="cn%s">%s</ul>%s%s</section>') % (
            esc(bid), esc(bid), esc(bid), esc(title), " nc" if "data-connect" in items else "", items,
            AGAIN_SLOT if again and not self.new else "", '<p class="lim">%s</p>' % esc(last) if last else "")
        return out, {"id": bid, "title": title, "says": last, "figures": [], "items": []}

    def _run_line(self):
        """The last and the next run, in one quiet line."""
        at = (self.column.get("schedule") or {}).get("at") if isinstance(self.column.get("schedule"), dict) else None
        try:
            hh, mm = (int(x) for x in str(at).split(":"))
            due = _dt.time(hh, mm)
        except (TypeError, ValueError):
            due = None
        ran = moment(self.run) if self.run and self.run != "by-hand" else None
        parts = []
        if ran:
            local = ran.astimezone(self.now.tzinfo)
            when = "today" if local.date() == self.today else "yesterday" if (self.today - local.date()).days == 1 else weekday_day(local.date())
            parts.append("Ran %s at %s." % (when, clock(local)))
        if due:
            nxt = "today" if self.now.time() < due and not (ran and ran.astimezone(self.now.tzinfo).date() == self.today) else "tomorrow"
            parts.append("Next at %s %s." % (clock(due), nxt) if ran else "Runs daily at %s." % clock(due))
        return " ".join(parts)

    # The whole page

    def _draw(self):
        if self._drawn is not None:
            return self._drawn
        draw = {"header": self._header, "goals": self._goals, "today": self._today, "chart": self._chart, "note": self._note,
                "suggestions": self._suggestions, "list": self._list, "table": self._table, "questions": self._questions,
                "connections": self._connections}
        parts, entries = [], []
        for block in self.blocks:
            data = self.data.get(block.get("data") or block["id"])  # a block's dataset is the one it names, else the one with its id
            if not isinstance(data, dict):
                if block.get("data") and block["type"] not in FIXED:
                    continue  # a block whose dataset is missing isn't drawn
                data = {}
            out, entry = draw[block["type"]](block, data or {})
            if not out:
                continue
            parts.append((block, out))
            if entry is not None:
                entries.append(entry)
        head = next((out for b, out in parts if b["type"] == "header"), "")
        rest, row = [], []

        def flush():
            if len(row) == 1:
                rest.append(row[0][1])
            elif row:
                rest.append('<div class="duo" style="--n:%d">%s</div>' % (len(row), "".join(out for _, out in row)))
            del row[:]
        for block, out in parts:
            if block["type"] == "header":
                continue
            width = WIDTHS.get(block.get("width", "full"), 1)
            if width == 1 or block["type"] in FIXED or (row and (WIDTHS.get(row[0][0].get("width"), 1) != width or len(row) == width)):
                flush()
            if width == 1 or block["type"] in FIXED:
                rest.append(out)
            else:
                row.append((block, out))
        flush()
        rest = [out.replace(AGAIN_SLOT, "" if self._dropped else self._again) for out in rest]
        if self._ready_to_set_up():
            rest.insert(0, self._ready_to_set_up())
        body = "%s\n<main class=\"pg\">\n%s\n</main>\n%s" % (head, "\n".join(rest + [r for r in [self._remove_row()] if r]), footer(self.now))
        summary = {
            "contract": "summary/v1", "app": self.app, "built_at": self.now.isoformat(timespec="seconds"), "as_of": self.as_of,
            "headline": (self.say or {}).get("headline", "") if not self.new else self.home.get("line", ""),
            "blocks": entries, "suggestions": [s.get("id", "") for s in self.suggestions()],
            "open_questions": [q["id"] for q in (self.say or {}).get("questions") or [] if isinstance(q, dict) and q.get("id") and not isinstance(q.get("answer"), dict)][:3],
        }
        self._drawn = (body, summary)
        return self._drawn

    def html(self):
        body, _ = self._draw()
        tips = self.tips()
        if tips:  # its tips still to show, for the kit's script
            body += "\n" + tips_html(self.app, tips)
        if self.preview:
            body += "\n" + layout_bar(self.app, self.preview)
        return document(self.app, self.title, body, accent=self.column.get("accent"), built_at=self.now.isoformat(timespec="seconds"),
                        run=self.run or "by-hand", as_of=self.as_of, appearance=self.settings["appearance"],
                        place=place_of(self.root), rail=rail(registry_apps(self.root) if self.root else None, self.app, self.root))

    def summary(self):
        return self._draw()[1]

    def _remove_row(self):
        """The page's own Remove, a quiet row at its foot, asked in its own place, then done by Home's server with no
        Claude, and Home opens. None for Hydra-OS's own pages (the main app's, and Goals, which holds every goal), for
        a page not in the registry, and for a page built with no root."""
        entry = self.apps.get(self.app) if self.root else None
        own = {a for e in self.apps.values() if isinstance(e, dict) and e.get("kind") == "main" for a in e.get("apps") or [] if isinstance(a, str)}
        if not entry or entry.get("kind") == "main" or self.app in own or self.app == "goals":
            return ""
        return ('<p class="t rm"><button type="button" class="alt" data-do="remove" data-fields=\'{"app": "%s", "confirm": true}\' data-yes="Remove" '
                'data-then="home" data-question="%s">Remove %s\u2026</button></p>') % (esc(self.app), esc(PAGE_REMOVE_ASK % self.title), esc(self.title))

    def _ready_to_set_up(self):
        """A page from the Shop that hasn't run yet (no say.json): one quiet line at the top of its page, "Finance is
        ready to set up." with Set up Finance, which hands Claude a setup request. "" once its first run has written
        say.json, for a page with nothing to set up (needs_setup), for a page that isn't in the Shop, and for a page
        built with no root."""
        if (not self.root or not self.new or not needs_setup(self.column)
                or self.app not in {p.get("id") for p in shop_doc(self.root)["pages"] if isinstance(p, dict)}):
            return ""  # a page with nothing to set up starts by itself
        return ('<p class="t upd" data-setup><span>%s is ready to set up.</span><button type="button" class="cta" data-connect '
                'data-kind="setup" data-app="%s">Set up %s</button></p>') % (esc(self.title), esc(self.app), esc(self.title))

    def tips(self):
        """This page's tips still to show (tips_of), those due today. A page built with no root has none."""
        if not self.root:
            return []
        since = installed_on(self.root)
        here = {b.get("id") for b in self.blocks}  # a block the page draws
        return [t for t in tips_of(self.column.get("tips"), self.settings["tips"].get(self.app, []), blocks=here) if tip_due(t, self.now.date(), since)]


def render_blocks(layout, yours, say, data, column, root=None, now=None, run="by-hand", answers=None, move=""):
    """The one function that turns a layout into a page: (the page's HTML, its summary). Page does the work."""
    page = Page(column, layout, say=say, data=data, root=root, now=now, run=run, answers=answers, move=move, yours=yours)
    return page.html(), page.summary()


def build(plugin, record, root=None, now=None, run="by-hand", data=None, answers=None, move="", names=None):
    """Build an app's page into its record: page/data/<name>.json, page/index.html and page/summary.json.

    plugin  the plugin's folder, for column.json and layout.json.
    record  the app's record folder, which must exist: say.json is read from it, and page/ is made in it.
    data    the app's datasets by name. Returns {"path", "blocks", "bytes"}: a path and counts, never a name or a figure.
    names   the app's own things a question names, {"project": {id: words}} (fill_names), read from its store.
    """
    if not os.path.isdir(record):
        raise KitError("no record folder to build the page in")
    column = read_json(os.path.join(plugin, "column.json"))
    layout = read_json(os.path.join(plugin, "layout.json"))
    if not isinstance(column, dict) or not isinstance(layout, dict):
        raise KitError("the plugin needs its column.json and its layout.json")
    yours = read_json(os.path.join(root, "yours", "layouts", "%s.json" % column.get("id"))) if root else None
    page = Page(column, layout, say=read_json(os.path.join(record, "say.json")), data=data, root=root, now=now, run=run,
                answers=answers, move=move, yours=yours, names=names)
    text, summary = page.html(), page.summary()
    packed = json.dumps(summary, ensure_ascii=False, indent=1)
    if len(packed.encode("utf-8")) > SUMMARY_MAX:
        raise KitError("the page's summary is over 24 KB")
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise KitError("the page is over 1 MB")
    folder = os.path.join(record, "page")
    for path in (folder, os.path.join(folder, "data")):
        os.makedirs(path, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
    for name, value in sorted((data or {}).items()):
        if not isinstance(name, str) or not name.replace("-", "").replace("_", "").isalnum():
            raise KitError("a dataset's name is letters, digits, - and _, and %r isn't" % name)
        body = json.dumps(value, ensure_ascii=False, indent=1) + "\n"
        if len(body.encode("utf-8")) > 256 * 1024:
            raise KitError("the dataset %s is over 256 KB" % name)
        write_whole(os.path.join(folder, "data", name + ".json"), body)
    write_whole(os.path.join(folder, "summary.json"), packed + "\n")
    write_whole(os.path.join(folder, "index.html"), text)
    return {"path": os.path.join(folder, "index.html"), "blocks": len(summary["blocks"]), "bytes": len(text.encode("utf-8"))}
