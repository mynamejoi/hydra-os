#!/usr/bin/env python3
"""Home, Hydra-OS's hub: the greeting, Toward your goals, a tile for each installed app with Add a
widget after them, and Claude asks, with the frame that holds every page, drawn with the main plugin's kit.

What Home says is its own; what each app found is the app's. It reads, and nothing else:
  <root>/hydra/registry.json            which apps are installed, and how each looks before it has run
  <root>/yours/goals.json, sources.json, settings.json and layouts/home.json
  each app's home.json (home/v3), and its say.json for the goals it measures
  Health's day/1 offer, found through the registry, for tonight's lights out in the greeting
  its own files in <root>/hydra/home/: you.json {"name"} and quote.json {"text", "by"}, either of them optional
  lines.json beside it: the lines of the day, one a day by the date

It writes only <root>/hydra/home/page/: index.html and frame.html (both Home; the server shows frame.html at /), the scripts and the
stylesheet they load, summary.json and stamp. Each whole or not at all, mode 0600.

  fresh(root)                     what Home's server calls before it serves Home: it rebuilds
                                  only when something Home reads has changed, and it never raises
  python3 page.py --root DIR [--now ISO]     build it by hand, or for a test

Python 3.9, standard library only. No model call and no request.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _kit():
    folder = os.environ.get("HYDRA_KIT") or os.path.join(os.path.dirname(HERE), "kit")
    spec = importlib.util.spec_from_file_location("hydra_kit", os.path.join(folder, "kit.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kit = _kit()
esc = kit.esc

OWN = ("home.js", "shop.js", "help.js")  # Home's own file, copied beside the page so /home/<file> serves it
BAND = ("goals",)                 # Goals is the band across the top, never a tile
ENGINES = ("research", "dreams")  # they read across every app: a row each under the apps, never a tile
ADD = ("Add a widget", "Tell Claude what you'd like here.")  # the grid's last tile; this build has no store
# While Wellbeing offers a widget that isn't on Home, the tile names its findings.
ADD_OFFERS = "Sleep, heart rate, lights out or meals. Tell Claude which, in the chat beside this page."
OFFER = re.compile(r"[a-z0-9-]{1,24}")  # an offer's id
QUOTE = {"text": "First say to yourself what you would be; and then do what you have to do.", "by": "Epictetus"}  # lines.json unread
LINES = os.path.join(HERE, "lines.json")  # about ninety short public-domain lines, one a day by the date
# Home's own tips, in their order, each pointing at
# its part by a selector of its own: the goals band once the first goal lands, Claude asks at its first question, the
# morning review's first morning, the sky on day two while no city is set, and Add a widget on day three.
TIPS = (
    {"id": "home-goals", "block": "goals", "sel": ".gband li", "text": "Your goal lives here. Open it to see how it's going.", "when": "data"},
    {"id": "home-asks", "block": "questions", "sel": "[data-block=questions] .qs > *", "text": "Answer here. It saves on the page, no chat needed.", "when": "data"},
    {"id": "home-review", "block": "", "sel": ".web .sg", "text": "This came from this morning's review.", "when": "after-review"},
    {"id": "home-sky", "block": "", "sel": ".head .orb.sun, .head .orb.moon", "text": "Your sky can follow your sun. Tell Claude your city.", "when": "day-2"},
    {"id": "home-widget", "block": "", "sel": ".web .add", "text": "Want something else here? Tell Claude.", "when": "day-3"},
)

# The first run's sheets, one at a time: the welcome sheet while it
# isn't seen and no name is kept, else What's new once after an update. The name saves on the page (POST /api/name).
WELCOME = ("Welcome to Hydra-OS", (
    ("home", "Your day on one page", "Home shows your goals and what matters today.", None),
    ("message", "Set up by talking", "Tell Claude what you want, in the chat beside this page.", None),
    ("file", "Kept on this Mac", "Your records are files in your Hydra-OS folder.", ("/privacy/", "How privacy works")),
))
NAME_FIELD = {"label": "What should we call you?", "placeholder": "First name", "under": "Optional"}
TITLED = re.compile(r"\*\*(.+?)\*\*\s*(.*)$")  # a CHANGELOG line's "**Title.**"

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


# ---------------------------------------------------------------------------------------------------------------
# What Home reads

def page_dir(root):
    return os.path.join(root, "hydra", "home", "page")


def offer(root, apps, name):
    """The file an installed app offers under this name ("day/1"), or None. Found through the registry, never by a path of Home's own."""
    for entry in apps.values():
        if name in (entry.get("offers") or []) and entry.get("root"):
            column = kit.read_json(os.path.join(entry["root"], "column.json"), {})
            for o in (column.get("offers") if isinstance(column, dict) else None) or []:
                if isinstance(o, dict) and "%s/%s" % (o.get("name"), o.get("version")) == name and isinstance(o.get("file"), str):
                    path = os.path.normpath(os.path.join(kit.record_of(root, entry["id"], apps), o["file"]))
                    if path.startswith(os.path.normpath(kit.record_of(root, entry["id"], apps)) + os.sep):
                        return path
    return None


def drop_only(entry):
    """True when every way in the app's column.json declares is a file dropped on its own page,
    as Health's export is. Its tile then opens that page at the drop place, since Claude has nothing to connect."""
    return kit.file_only(kit.read_json(os.path.join(entry["root"], "column.json"), {}) if isinstance(entry.get("root"), str) else {})


# While a dropped file waits to be read, on every page's tile and Wellbeing's page alike:
# one state, one phrase, whatever the file.
READING = "Reading your file…"


def inbox(root, entry, apps):
    """The folder an app's upload source files into, or None."""
    column = kit.read_json(os.path.join(entry["root"], "column.json"), {}) if isinstance(entry.get("root"), str) else {}
    source = kit.upload_source(column)
    if not source:
        return None
    return os.path.join(kit.record_of(root, entry["id"], apps), str(source.get("folder") or "inbox/").strip("/"))


def unread(root, entry, apps, home):
    """True while a file dropped on the app's page waits to be read: one in its upload folder that's newer than its last
    home.json, or any before its first. home.json's `updated_at` is the start of the run
    that wrote it, to the second, and Home's server starts that run only once the file is filed, so
    a file from that same second is one the run has read: an app that keeps its file, as Finance keeps the bank's, would
    otherwise read as "Reading…" for good. A stamp with fractions is held to the instant."""
    box = inbox(root, entry, apps)
    try:
        names = [n for n in os.listdir(box) if not n.startswith(".") and os.path.isfile(os.path.join(box, n))] if box else []
        newest = max((os.stat(os.path.join(box, n)).st_mtime for n in names), default=None)
    except OSError:
        return False
    if newest is None:
        return False
    ran = kit.moment((home or {}).get("updated_at") or (home or {}).get("as_of"))
    if not ran:
        return True
    started = ran.timestamp()
    return int(newest) > started if started == int(started) else newest > started


def tiles_order(apps, layout):
    """The installed apps that get a tile, in the person's order when they have one, else the rail's (kit.rail_apps: the
    free pages first, then the kit's order), never the order they were installed in. Goals is
    the band, so it has none, and an app that isn't installed has none."""
    ids = [i for i in kit.rail_apps(apps) if i not in BAND and i not in ENGINES]
    if isinstance(layout, dict):
        hidden = set(layout.get("hidden") or [])
        want = [i for i in layout.get("order") or [] if i in ids]
        ids = [i for i in want + [i for i in ids if i not in want] if i not in hidden]
    return ids


def ran_today(root, now):
    """Whether the morning review ran today: hydra think's <root>/hydra/think/ran.json, {"at"}."""
    doc = kit.read_json(os.path.join(root, "hydra", "think", "ran.json"), {})
    at = kit.moment(doc.get("at")) if isinstance(doc, dict) else None
    return bool(at and at.tzinfo) and at.astimezone(now.tzinfo).date() == now.date()


def tips(model):
    """Home's tips still to show today: not seen (yours/settings.json's "tips"), and due (kit.tip_due). The sky's waits
    while their city is set, and the morning review's until hydra think has run today (ran_today)."""
    root = model.get("root")
    if not root:
        return []
    seen, since = kit.settings_of(root)["tips"].get("home", []), kit.installed_on(root)
    reviewed = ran_today(root, model["now"])
    return [t for t in TIPS if t["id"] not in seen and kit.tip_due(t, model["now"].date(), since, reviewed=reviewed)
            and not (t["id"] == "home-sky" and model["place"])]


def lights_out(root, apps, today):
    """Tonight's lights out in minutes after midnight, from Health's day/1 offer for today, or None."""
    path = offer(root, apps, "day/1")
    got = kit.read_json(path, {}) if path else {}
    if not isinstance(got, dict) or got.get("day") != today.isoformat() or not isinstance(got.get("lights_out"), str):
        return None
    try:
        hh, mm = (int(x) for x in got["lights_out"].split(":"))
    except ValueError:
        return None
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    minutes = hh * 60 + mm
    return minutes + 1440 if minutes < 300 else minutes  # a lights out after midnight belongs to the evening before it


def day_lines():
    """The bundled lines of the day, in their order: [{"text", "by", "from"}]."""
    got = kit.read_json(LINES, {})
    lines = got.get("lines") if isinstance(got, dict) else None
    return [q for q in lines if isinstance(q, dict) and isinstance(q.get("text"), str) and q["text"].strip()] if isinstance(lines, list) else []


def own_why(goals, today):
    """On a Monday, their own why: one goal a Monday, from the
    active goals with a why, in goals.json's order, turn by turn by the week. None on any other day, or with no why."""
    whys = [r for r in goals["goals"] if r.get("status") == "active" and isinstance(r.get("why"), str) and r["why"].strip()]
    if today.weekday() != 0 or not whys:
        return None
    r = whys[today.toordinal() // 7 % len(whys)]
    return {"text": r["why"].strip(), "by": "You, on %s" % r["text"].strip()}


def day_quote(root, today, goals):
    """The quote under the greeting: their own why on a Monday; else quote.json's, when they've set one; else the day's
    bundled line, by the date."""
    own = own_why(goals, today)
    if own:
        return own
    quote = kit.read_json(os.path.join(root, "hydra", "home", "quote.json"), {})
    if isinstance(quote, dict) and isinstance(quote.get("text"), str) and quote["text"].strip():
        return quote
    lines = day_lines()
    return lines[today.toordinal() % len(lines)] if lines else QUOTE


def past_due(root, app_id, apps, now):
    """True once an app's say.json is past its stale_after: its tile then says how old it
    is, as its goals do."""
    say = kit.read_json(os.path.join(kit.record_of(root, app_id, apps), "say.json"))
    after = kit.moment(say.get("stale_after")) if isinstance(say, dict) else None
    return bool(after and now > after)


def read(root, now=None):
    """Everything Home says, as plain data, from the files alone."""
    now = now or clock()
    today = now.date()
    apps = kit.registry_apps(root)
    settings = kit.settings_of(root)
    layout = kit.read_json(os.path.join(root, "yours", "layouts", "home.json"))
    goals = kit.read_goals(root, today, now=now)
    tiles, asked, offers = [], [], {}
    texts = {r["id"]: r["text"] for r in goals["goals"] + goals["record"]}
    hand = {r["id"] for r in goals["goals"]}
    # Goals has no tile, but its questions, like a new goal's why, are Claude asks' as every app's are.
    shown = tiles_order(apps, layout)
    every = tiles_order(apps, dict(layout, hidden=[])) if isinstance(layout, dict) else shown  # a hidden tile's added widgets still show
    for app_id in every + [i for i in ENGINES if i in apps] + [i for i in BAND if i in apps]:
        entry = apps[app_id]
        about = entry.get("home") if isinstance(entry.get("home"), dict) else {}
        home = kit.read_json(os.path.join(kit.record_of(root, app_id, apps), "home.json"))
        if not isinstance(home, dict) or home.get("contract") != "home/v3" or home.get("state") == "new":
            home = None
        stale = past_due(root, app_id, apps, now)  # its say.json past its stale_after
        if app_id not in BAND:
            tiles.append({"id": app_id, "title": entry.get("title") or app_id.capitalize(), "accent": entry.get("accent"), "icon": entry.get("icon"),
                          "about": about, "home": home, "engine": app_id in ENGINES, "schedule": entry.get("schedule") if isinstance(entry.get("schedule"), dict) else {},
                          "feeds": [r["id"] for r in goals["goals"] if r["app"] == app_id], "drop": drop_only(entry),
                          # a stale or failed tile shows how old it is, never "Reading your file…": its run has
                          # stopped, so a file can look unread for good
                          "reading": unread(root, entry, apps, home) and not stale and (home or {}).get("state") not in ("stale", "failed"),
                          "hidden": app_id in every and app_id not in shown, "offers": offers_of(home), "stale": stale})
        if app_id in every and app_id not in shown:
            continue  # a hidden tile's questions stay off Claude asks
        for q in (home or {}).get("questions") or []:
            if isinstance(q, dict) and q.get("id") and q.get("text"):
                q = kit.fill_goal(q, texts)  # "Why does '{goal}' matter to you?", in the goal's own words from goals.json
                if q and app_id in BAND and kit.offer_app(q):  # Goals' one offer goes under its goal in the band
                    if q["goal"] in hand:
                        offers.setdefault(q["goal"], q)
                elif q:
                    asked.append((app_id, entry.get("title") or app_id.capitalize(), entry.get("accent"), q))
    asked = [a for a in asked if not isinstance(a[3].get("answer"), dict)] + [a for a in asked if isinstance(a[3].get("answer"), dict)]
    you = kit.read_json(os.path.join(root, "hydra", "home", "you.json"), {})
    name = you.get("name") if isinstance(you, dict) and isinstance(you.get("name"), str) else ""
    measured = [r for r in goals["goals"] if r["state"] != "new"]
    # They said no to the morning review: while no tile ends in a suggestion, the first that would says how to turn it
    # on, once.
    live = [t for t in tiles if t["home"] and not t["engine"] and not t["hidden"] and not t["stale"] and not t["reading"]
            and t["home"].get("state") not in ("stale", "failed")] if kit.review_off(settings) else []
    quiet = [] if any(isinstance(t["home"].get("suggest"), dict) and str(t["home"]["suggest"].get("text") or "").strip() for t in live) \
        else [t["id"] for t in live]
    sourced = {s["app"] for s in kit.sources_of(root)}
    return {
        "now": now, "today": today, "apps": apps, "settings": settings, "goals": goals, "measured": bool(measured),
        "review_tile": quiet[0] if quiet else None, "offers": offers,
        "tiles": [t for t in tiles if not t["engine"] and not t["hidden"]], "engines": [t for t in tiles if t["engine"]], "asked": asked[:3],
        "grid": grid(tiles, layout), "offers_left": offers_left(tiles, layout),
        "name": name.strip().split(" ")[0][:24], "out": lights_out(root, apps, today),
        "welcome": not settings["welcome"] and not name.strip(),  # the welcome sheet's due
        "helpers": helpers_of(root),
        "quote": day_quote(root, today, goals),
        "new": not any(t["home"] for t in tiles if not t["hidden"]),  # nothing has run yet: the day-zero hub. Goals has no tile, so its run doesn't end it
        "has_goals_app": "goals" in apps,
        "place": kit.place_of(root), "root": root,
        "ready": core_ready(root, apps), "whats_new": whats_new(root, apps),  # a newer Hydra-OS, and what's new after an update
        "sourced": sourced,
    }


# ---------------------------------------------------------------------------------------------------------------
# Drawing it

def greeting(model):
    """The greeting for the build's own minute, by one hour rule in every state. The page's script keeps it to the
    clock from then on. With tonight's lights out it's "Still up?" after it; with none known, after midnight."""
    now, name, out = model["now"], model["name"], model["out"]
    t = now.hour * 60 + now.minute
    m = t + 1440 if t < 300 else t
    tail = ", " + name if name else ""
    if m >= (out or 1440):
        return "Still up%s?" % tail
    if out and m >= out - 90:
        return "Winding down%s." % tail
    return ("Good morning" if m < 720 else "Good afternoon" if m < 1020 else "Good evening") + tail + "."


def first_step(model):
    """While nothing has run, the one thing to do first, in plain words. With no goal,
    nothing here: the band's line points to Claude, in the chat. Then whatever the app that will measure a goal needs,
    with Claude for its way in unless that's a file dropped on its page; then nothing, since the app's own tile says
    when it fills in."""
    if not model["new"] or not model["goals"]["goals"]:
        return ""
    for t in model["tiles"]:
        needs = (t["about"].get("needs") or "").strip()
        if needs and t["feeds"] and t["id"] not in model["sourced"] and not t["reading"]:
            return "Next: %s%s below%s" % (needs[:1].lower(), needs[1:], "." if t["drop"] else ", or tell Claude what you use.")
    return ""


def minutes_said(m):
    """Minutes after midnight, as the page says a time: 1260 -> "9:00 pm"."""
    m %= 1440
    return "%d:%02d %s" % (m // 60 % 12 or 12, m % 60, "am" if m < 720 else "pm")


def date_more(model):
    """What follows the date: tonight's lights out when Health has it, which home.js joins to
    the sunset once a place is set. One dot at most."""
    out, place = model["out"], model["place"]
    if not out and not place:
        return ""
    attrs = (' data-lo="%s"' % esc(minutes_said(out)) if out else "") + (" data-sunset" if place else "")
    return '<span data-more%s>%s</span>' % (attrs, esc(" \u00b7 Lights out %s" % minutes_said(out)) if out else "")


def head(model):
    today, quote = model["today"], model["quote"]
    cite = "<cite>%s</cite>" % esc(quote["by"]) if isinstance(quote.get("by"), str) and quote["by"].strip() else ""
    return ('<header class="head"><i class="orb sun" aria-hidden="true"></i><i class="orb moon" aria-hidden="true"></i><div class="top"><div>'
            '<h1 data-greet data-name="%s" data-out="%s">%s</h1><p class="date">%s, %s %d%s</p>%s</div>'
            '<blockquote class="quote"><p>“%s”</p>%s</blockquote></div></header>') % (
        esc(model["name"]), model["out"] or "", esc(greeting(model)), DAYS[today.weekday()], MONTHS[today.month - 1], today.day,
        date_more(model),  # lights out, and sunset once their place is set: home.js, from the kit's sun
        '<p class="first">%s</p>' % esc(first_step(model)) if first_step(model) else "", esc(quote["text"].strip()), cite)


def shown_goals(model):
    """The band's goals as it draws them, and the tally it shows, which the summary says too: with one or two goals, a
    goal that's behind says why from its measuring app, and there's no tally."""
    readings = model["goals"]["goals"]
    if len(readings) <= 2:
        return [dict(r, caption=r["why_pace"]) if r["state"] == "behind" and r["why_pace"] else r for r in readings], ""
    return readings, model["goals"]["tally"]


MORE_GOALS = kit.SOMETHING_ELSE


def band_offer(model, reading):
    """Goals' one offer for this goal, under it in the band: "Finance
    can count 'Save $5,000 for a trip' now.", with Count it and Not this one, in the arriving page's colour. A pick saves
    through Goals' answer, "Saved." with Undo, as every question does."""
    q = model.get("offers", {}).get(reading["id"])
    if not q:
        return ""
    page_id = kit.offer_app(q)
    return kit.question(q, "goals", accent=(model["apps"].get(page_id) or {}).get("accent"), tint_app=page_id, saved="Saved.")


def band(model):
    """Toward your goals: every goal in hand, read as Goals reads them. Until one is measured, each row says who will
    measure it, over the line that points a new goal to Claude, in the chat. With no goal at all, it's that line, with
    a few goals in plain words."""
    readings = model["goals"]["goals"]
    title = '<a href="/goals/" target="_top">Goals</a>' if model["has_goals_app"] else "Goals"
    rows, tally = shown_goals(model)  # the tally shows only from three goals
    top = '<div class="gt"><h2 class="h" id="h-goals">%s</h2>%s</div>' % (title, kit._tally(tally))
    if model["measured"]:
        n, few = len(readings), len(readings) <= 2
        if few:  # one or two: each row spans the tile, and a goal that's behind says why, from its measuring app
            body = '<ul class="gl5 few" style="--n:1;--n3:1;--n2:1">%s</ul><p class="gq">%s</p>' % (
                "".join(kit.goal_item(r, home=True, under=band_offer(model, r)) for r in rows), esc(MORE_GOALS))
        else:
            cols = "--n:%d;--n3:%d;--n2:%d" % (max(2, min(5, n)), max(2, min(3, n)), 2)
            body = '<ul class="gl5" style="%s">%s</ul>' % (cols, "".join(kit.goal_item(r, home=True, under=band_offer(model, r)) for r in readings))
    else:
        rows = "".join('<li%s><span class="gn">%s</span>%s%s%s</li>' % (kit._attrs(*kit._goal_style(r)), esc(r["text"]), kit.goal_bar(r), kit.goal_status(r),
                                                                       band_offer(model, r)) for r in readings)
        body = '<div class="g0"><ul class="g0l">%s</ul>%s</div>' % (rows, kit.goal_field(first=not readings, examples=not readings))
    return '<article class="t gband" data-block="goals" aria-labelledby="h-goals">%s%s</article>' % (top, body)


def offers_of(home):
    """An app's offers Home may draw as widgets: up to six from its home.json, each with an id
    and a name."""
    got = (home or {}).get("offers")
    return [o for o in got[:6] if isinstance(o, dict) and isinstance(o.get("id"), str) and OFFER.fullmatch(o["id"])
            and isinstance(o.get("title"), str) and 1 <= len(o["title"].strip()) <= 20] if isinstance(got, list) else []


def added_ids(layout):
    """The widgets added from apps' offers, each once, in the order added: yours/layouts/home.json's `added`."""
    got = layout.get("added") if isinstance(layout, dict) else None
    out = []
    for a in got if isinstance(got, list) else []:
        wid = a.get("id") if isinstance(a, dict) else None
        if isinstance(wid, str) and wid.count(".") == 1 and wid not in out:
            out.append(wid)
    return out


def grid(tiles, layout):
    """The grid in order: each app's tile, then the widgets added from its offers, in the order
    added, each drawn from the app's current offer. A hidden tile or widget isn't drawn, a hidden tile's widgets still
    are, and an offer the app no longer makes draws nothing."""
    hidden = set(layout.get("hidden") or []) if isinstance(layout, dict) else set()
    added, out = added_ids(layout), []
    for t in tiles:
        if t["engine"]:
            continue
        if not t["hidden"]:
            out.append(("tile", t))
        offers = {o["id"]: o for o in t["offers"]}
        for wid in added:
            app_id, _, oid = wid.partition(".")
            if app_id == t["id"] and oid in offers and wid not in hidden:
                out.append(("widget", {"id": wid, "tile": t, "offer": offers[oid]}))
    return out


def offers_left(tiles, layout):
    """True while Wellbeing offers a widget that isn't on Home yet, so Add a widget names its findings."""
    added = set(added_ids(layout))
    return any("%s.%s" % (t["id"], o["id"]) not in added for t in tiles if t["id"] == "health" for o in t["offers"])


def widget(w, model):
    """An added widget: one of an app's other findings in the one tile shape, from its current
    offer: the app's symbol with the finding's name, how it stands, its line and its 14 days, then the button that takes
    it off Home (POST /api/widget/remove, in home.js)."""
    t, o = w["tile"], w["offer"]
    cls, style = kit.tint(t["id"], t["accent"])
    title = o["title"].strip()
    name = '%s<a href="/%s/" target="_top">%s</a>' % (kit.icon(kit.app_icon(t["id"], t["icon"])), esc(t["id"]), esc(title))
    word = o["word"].strip() if isinstance(o.get("word"), str) else ""
    as_of = kit.moment(t["home"].get("as_of"))
    if (t["home"].get("state") in ("stale", "failed") or t["stale"]) and as_of:
        word = "As of " + kit.short_day(as_of.date())
    status = '<span class="st%s">%s</span>' % (" off" if word.lower().endswith(("behind", "missed")) else "", esc(word)) if word else ""
    body = '<header class="ch"><h2>%s</h2>%s</header><p class="say">%s</p>' % (name, status, esc(kit.capital(o["line"].strip()) if isinstance(o.get("line"), str) else ""))
    days = o.get("days") if isinstance(o.get("days"), dict) else None
    if days and len(days.get("values") or []) == 14:
        body += kit.chart(days, to=model["today"], label_on_line=True, group=True, says=days.get("says"))
    if isinstance((days or {}).get("caption"), str) and days["caption"].strip():
        body += '<p class="gl"><span class="cap">%s</span></p>' % esc(days["caption"].strip())
    body += '<p class="act0"><button type="button" class="tb" data-remove="%s">Take off Home</button></p>' % esc(w["id"])
    return "<article%s>%s</article>" % (kit._attrs(" ".join(c for c in ("t", "card", "wd", cls) if c), style, tabindex="0",
                                                  data_widget=w["id"], data_name=title), body)


def tile(t, model):
    """One app's tile, in the one shape: its symbol and name, how it stands, the finding, the 14 days, and the goal it moves."""
    cls, style = kit.tint(t["id"], t["accent"])
    home, about = t["home"], t["about"]
    name = '%s<a href="/%s/" target="_top">%s</a>' % (kit.icon(kit.app_icon(t["id"], t["icon"])), esc(t["id"]), esc(t["title"]))
    attrs = kit._attrs(" ".join(c for c in ("t", "card", cls) if c), style, tabindex="0" if home and not model["new"] else None, data_app=t["id"],
                       data_item=t["id"], data_name=t["title"], data_feeds=" ".join(t["feeds"]))
    if not home:  # just installed: its name, its line, the 14 days as empty marks, and the one thing it needs, if any
        needs, via = (about.get("needs") or "").strip(), (about.get("via") or "").strip()
        body = '<header class="ch"><h2>%s</h2></header><p class="say0">%s</p>%s' % (name, esc(READING if t["reading"] else kit.capital(about.get("line") or "")), kit.empty_marks())
        if t["reading"]:  # the file is in: nothing to do but wait for its read
            pass
        elif needs and t["drop"]:  # its one way in is a file: the tap opens its page at the drop place, and files nothing
            body += '<p class="act0"><a class="cta" href="/%s/#drop" target="_top">%s</a><span class="via">%s</span></p>' % (
                esc(t["id"]), esc(needs), esc("The %s page shows you how." % t["title"]))
        elif needs:
            body += '<p class="act0">%s%s</p>' % (kit.connect(t["id"], needs), '<span class="via">%s</span>' % esc(via) if via else "")
        return "<article%s>%s</article>" % (attrs, body)
    word = (home.get("word") or "").strip()
    stale = home.get("state") in ("stale", "failed") or t["stale"]  # or its say.json is past its stale_after
    as_of = kit.moment(home.get("as_of"))
    if stale and as_of:
        word = "As of " + kit.short_day(as_of.date())
    status = '<span class="st%s">%s</span>' % (" off" if word.lower().endswith(("behind", "missed")) else "", esc(word)) if word else ""  # Goals' "2 behind" too
    move = home.get("move") if isinstance(home.get("move"), dict) and home["move"].get("text") else None
    said = READING if t["reading"] else kit.capital(move["text"] if move else home.get("line") or "")  # every tile line starts with a capital
    body = '<header class="ch"><h2>%s</h2>%s</header><p class="say">%s</p>' % (name, status, esc(said))
    days = home.get("days") if isinstance(home.get("days"), dict) else None
    if days and len(days.get("values") or []) == 14:
        body += kit.chart(days, to=model["today"], label_on_line=True, group=True, says=days.get("says"))
    href = kit.page_link(move.get("link")) if move else None
    words = kit.MOVE_DO.get(href.rpartition("#")[2]) if href and "#" in href else None
    if words and not t["reading"]:  # the move's one button, under the chart: an old export's "Add a fresh export"
        body += '<p class="act0"><a class="cta" href="%s" target="_top">%s</a></p>' % (esc(href), esc(words))
    goal = next((r for r in model["goals"]["goals"] if r["app"] == t["id"]), None)
    caption = (days or {}).get("caption") or ""
    if goal or caption:
        body += '<p class="gl">%s%s</p>' % (kit.icon("target") + esc(goal["text"]) if goal else "", '<span class="cap">%s</span>' % esc(caption) if caption else "")
    suggest = home.get("suggest") if isinstance(home.get("suggest"), dict) and isinstance(home["suggest"].get("text"), str) else None
    if suggest and suggest["text"].strip() and not stale:  # the tile ends in its suggestion, none once it's stale
        body += '<p class="sg">%s<a href="%s" target="_top">See why on %s</a></p>' % (
            esc(kit.capital(suggest["text"].strip())), esc(kit.page_link(suggest.get("link")) or "/%s/" % t["id"]), esc(t["title"]))
    elif t["id"] == model.get("review_tile"):  # where its suggestion would be, while they said no to the morning review
        body += '<p class="sg nrv">%s</p>' % esc(kit.REVIEW_OFF)
    return "<article%s>%s</article>" % (attrs, body)


def add_tile(model):
    """Add a widget, the grid's last tile, in the target's shape. This build has no
    store. While Wellbeing offers a widget that isn't on Home, the tile names its findings, and Claude adds the one they
    pick by `hydra widget add` after their yes. A tap hands Claude a
    request that names no app yet, Claude asks what they'd like there, and the kit's
    note says to go to Claude."""
    return ('<button type="button" class="t add" data-connect data-kind="add-app" data-app="">'
            '<span class="plus" aria-hidden="true">%s</span><b>%s</b><span class="how">%s</span></button>') % (kit.icon("plus"), esc(ADD[0]), esc(ADD_OFFERS if model["offers_left"] else ADD[1]))


def engine(t, model):
    """Research or Dreams: one row under the apps, stating its top item, or when it starts."""
    cls, style = kit.tint(t["id"], t["accent"])
    link = '<a class="go" href="/%s/" target="_top"><b>%s</b></a>' % (esc(t["id"]), esc(t["title"]))
    if t["home"] and t["home"].get("line"):
        words = "%s: <span>%s</span>" % (link, esc(t["home"]["line"]))
    elif t["id"] == "research":
        words = "%s %s" % (link, "starts on your goals tonight" if model["goals"]["goals"] else "starts once you set a goal or name a project")
    else:
        at = None
        try:
            hh, mm = (int(x) for x in str(t["schedule"].get("at")).split(":"))
            at = datetime.time(hh, mm)
        except (TypeError, ValueError):
            pass
        words = "%s %s" % (link, "runs tonight at %s, after your first day" % kit.clock(at) if at else "runs overnight, after your first day")
    return '<div%s>%s<span>%s</span></div>' % (kit._attrs(" ".join(c for c in ("sp", cls) if c), style, role="group", tabindex="0" if t["home"] else None,
                                                         aria_label=t["title"], data_eng=t["id"]), kit.icon(kit.app_icon(t["id"], t["icon"])), words)


def web(model):
    """The goals band, the apps that feed it with Add a widget after them, and the engines under them, when they're
    installed. What belongs together lights together."""
    cards = "".join(tile(x, model) if kind == "tile" else widget(x, model) for kind, x in model["grid"])
    dock = '<div class="gdock" aria-hidden="true"><div class="gbar" style="--n:%d"></div></div>' % max(2, min(5, len(model["goals"]["goals"]))) if model["measured"] else ""
    strip = '<div class="strip">%s</div>' % "".join(engine(t, model) for t in model["engines"]) if model["engines"] else ""
    return ('<section class="web%s" data-to="%s" data-today="%s" aria-label="Your goals, and the pages that feed them.">%s%s'
            '<div class="lane"><h2 class="h plate" id="h-apps">Your pages</h2><div class="dayw"><p class="plate day" aria-live="polite"></p></div></div>'
            '<div class="grid" data-block="apps" role="group" aria-labelledby="h-apps">%s%s</div>%s</section>') % (
        " new" if model["new"] else "", window_end(model).isoformat(), model["today"].isoformat(), dock, band(model), cards, add_tile(model), strip)


ASKS_NOTE = "Written from your goals and your last two weeks. Your answers shape tomorrow's page."
ASKS_EMPTY = "Nothing to ask yet. Questions show here after your first goal."  # before any goal


def window_end(model):
    """The last day of the tiles' 14 days, for home.js's day read-out: the charts' own when they all end on one day, like
    an old export's last day, else today."""
    ends = {kit.day((t["home"].get("days") or {}).get("to")) for t in model["tiles"] if t["home"] and isinstance(t["home"].get("days"), dict)}
    ends.discard(None)
    return ends.pop() if len(ends) == 1 else model["today"]


def asks(model):
    """Claude asks: before any goal its empty state says when
    questions come; then the questions under one note, or a quiet day's line."""
    if not model["goals"]["goals"]:
        return kit.asks([], note=ASKS_EMPTY, own=False)
    texts = {r["id"]: r["text"] for r in model["goals"]["goals"]}
    items = [kit.question(q, app_id, tag=" \u00b7 ".join(t for t in (title, texts.get(q.get("goal"), "")) if t), accent=accent)
             for app_id, title, accent, q in model["asked"]]
    return kit.asks(items, note=ASKS_NOTE if items else "Nothing to ask today.", own=False)


def summary(model, built_at):
    """What Home says, for Claude to read when the person asks about it, and for the focus taps (summary/v1)."""
    goals = model["goals"]
    rows, tally = shown_goals(model)  # as the band says them
    blocks = [{"id": "goals", "title": "Goals", "says": tally,
               "figures": [{"label": r["text"], "value": " ".join(x for x in (r["word"], "· " + r["caption"] if r["word"] and r["caption"] else r["caption"]) if x)} for r in rows],
               "items": [{"id": r["id"], "label": r["text"]} for r in goals["goals"]] if model["measured"] else []},
              {"id": "apps", "title": "Your pages", "says": "",
               "figures": [{"label": t["title"], "value": ((t["home"].get("move") or {}).get("text") or t["home"].get("line") or "") if t["home"] else t["about"].get("line") or ""} for t in model["tiles"]]
                          + [{"label": w["offer"]["title"].strip(), "value": w["offer"].get("line") or ""} for kind, w in model["grid"] if kind == "widget"],
               "items": [{"id": t["id"], "label": t["title"]} for t in model["tiles"]]}]
    if model["goals"]["goals"]:  # Claude asks, as the page draws it: not before any goal
        blocks.append({"id": "questions", "title": "Claude asks", "says": "", "figures": [], "items": [{"id": q["id"], "label": q["text"]} for _, _, _, q in model["asked"]]})
    return {"contract": "summary/v1", "app": "home", "built_at": built_at, "as_of": built_at, "headline": tally, "blocks": blocks,
            "suggestions": [], "open_questions": [q["id"] for _, _, _, q in model["asked"] if not isinstance(q.get("answer"), dict)]}


def said_list(words):
    """["Home", "Goals", "Wellbeing"] -> "Home, Goals and Wellbeing"."""
    return words[0] if len(words) == 1 else "%s and %s" % (", ".join(words[:-1]), words[-1])




# Help: plain answers, a report, and the two lines about Claude and Anthropic.
DESCRIPTION = ("Hydra-OS is a set of plugins for Claude Code. It requires your own Claude plan (Pro or higher); you sign in "
               "with Anthropic directly. Hydra-OS never sees your login and doesn't include or resell Claude usage.")
HELP = (
    ("about", "What is Hydra-OS?", DESCRIPTION),
    ("devtools", "My Mac asked to install developer tools. What do I do?",  # Claude Code runs git at every start
     "Choose Install. It's a free Apple download that Claude Code uses, and it takes a few minutes. Hydra-OS needs nothing else."),
    ("goal", "How do I set a goal?",
     "Tell Claude what you're working toward, in the chat beside this page. Goals keeps it, and the page that can count it does."),
    ("current", "How do my pages stay up to date?",
     "Each page updates every morning by itself. Pages that read your accounts do it in the morning review, which runs in your "
     "Claude app once you've turned it on. The more pages you have, the more of your plan it uses. Others read a file you drop on them."),
    ("repair", "A page says it hasn't updated. What do I do?",
     'Tell Claude "repair Hydra-OS" in the chat beside this page. It finds what\'s wrong and says what it changed.'),
    ("shop", "How do I add a page from the Shop?",
     "Open the Shop at the foot of the rail. Choose Get, or paste the key you were given at the Shop's foot, and the page joins "
     "your rail. Then say 'set up' and the page's name in the chat, such as 'set up People'."),
    ("update", "How do I update Hydra-OS?",
     'When Home says a new version is ready, tell Claude "update Hydra-OS". Your goals, your pages\' records and your own changes stay.'),
    ("remove", "How do I remove Hydra-OS?", 'Tell Claude "remove Hydra-OS". It asks before anything goes.'),
    ("records", "Where are my records?", "As files on your Mac, in the Hydra-OS folder in your home folder. There's no server of ours."),
    ("leaves", "What leaves my Mac?",
     "What Claude reads for each page, under your own account; the Shop's daily list, which sends nothing about you; and Research's "
     "searches, in general words only. The Privacy page says it all."),
)
REPORT = ("Something's wrong. Who do I tell?", "Copy a report", "It shows how Hydra-OS is running, never your records, and you see all of it before you copy it.")
HELP_FILE = os.path.join(HERE, "help.json")  # the contact address, once one is set
# Help's first line and its rows.
HELP_LINE = "Ask Claude anything in the chat beside this page."
# Hydra-OS's two background helpers, Home's server and the tick, as config.json's "helpers" says: the line under Help's row
HELPERS = {"on": "Home and the daily reads start when you log in.", "off": "Home and the daily reads start with a Hydra-OS chat."}
HELP_ROWS = {"review": "Each morning Claude reads your pages and puts the day's moves on Home. It uses some of your Claude plan each morning.",  # its plan use
             "repair": "For a page that hasn't updated. Claude finds what's wrong and says what it changed.",
             "privacy": "What stays on your Mac, and what leaves it."}
CONTACT = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


# A newer Hydra-OS, and what's new after an update. An update goes through Claude.
CHANGELOG = os.environ.get("HYDRA_TEST_CHANGELOG") or os.path.join(os.path.dirname(HERE), "CHANGELOG.md")  # the main plugin's: "## <version>", then its "- " lines; a test names a made-up one
READY = 'Hydra-OS %s is ready. Tell Claude "update Hydra-OS".'


def installed(apps):
    """The installed main plugin's version: the registry's main entry, else this plugin's own."""
    main = next((a for a in apps.values() if isinstance(a, dict) and a.get("kind") == "main" and kit._vt(a.get("version"))), None)
    return main["version"] if main else kit.MAIN_VERSION


def core_ready(root, apps):
    """The catalog in force's core version while it's newer than the installed one, else ""."""
    core = kit.shop_doc(root).get("core")
    if not isinstance(core, dict) or not kit._vt(core.get("version")):
        return ""
    return core["version"] if kit._vt(core["version"]) > kit._vt(installed(apps)) else ""


def notes_for(version):
    """The CHANGELOG's lines for a version: under its own "## <version>", each "- " line, plain, at most five of 120."""
    try:
        with open(CHANGELOG, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == version
        elif inside and line.startswith("- "):
            said = " ".join(line[2:].split())
            if 0 < len(said) <= 120:
                out.append(said)
    return out[:5]


def whats_new(root, apps):
    """(version, lines) once after an update: setup keeps the installed version as seen (yours/settings.json's whats_new),
    so a first install shows nothing, and an update shows its own lines until Close. None otherwise."""
    have = installed(apps)
    seen = (kit.read_json(os.path.join(root, "yours", "settings.json"), {}) or {}).get("whats_new")
    if not isinstance(seen, str) or not seen or seen == have:
        return None
    lines = notes_for(have)
    return (have, lines) if lines else None


def updates(model):
    """The quiet line that says a newer Hydra-OS is ready, at the top of Home's grid. What's new is a sheet (sheet())."""
    out = ""
    if model.get("ready"):
        out += '<p class="t upd" data-block="update">%s</p>\n' % esc(READY % kit.shown_version(model["ready"]))
    return out


def sheet(model):
    """Home's one sheet, if any: the welcome sheet while it's due, else What's new once after an update,
    its rows the version's first three lines, each "**Title.**" its row's title."""
    if model.get("welcome"):
        return kit.sheet_html("welcome", WELCOME[0], WELCOME[1], field=NAME_FIELD)
    if model.get("whats_new"):
        version, lines = model["whats_new"]
        rows = []
        for line in lines[:3]:
            m = TITLED.match(line)
            rows.append(("check", m.group(1).strip().rstrip(".").strip(), m.group(2).strip(), None) if m else ("check", "", line, None))
        return kit.sheet_html("whats-new", "What's new in Hydra-OS %s" % kit.shown_version(version), rows, esc_go=True)
    return ""


def helpers_of(root):
    """Whether Hydra-OS's background helpers are on: <root>/hydra/config.json's "helpers", "on" or "off", as setup and
    `hydra helpers` write it. None when it can't be read or says anything else, so Help draws no row rather than guess."""
    doc = kit.read_json(os.path.join(root, "hydra", "config.json"), {})
    state = doc.get("helpers") if isinstance(doc, dict) else None
    return state if state in ("on", "off") else None


def help_page(model):
    """Help at /help/: its first line, then its rows:
    the morning review, with Turn on while it's off; the background helpers, On with Turn off or Off with Turn on,
    whose button hands Claude the request (Claude asks before it changes anything), and no row when config.json can't
    say which; Copy a report, whose button shows the report's exact text before its
    Copy (help.js); Repair; Privacy; and the contact address once help.json holds one. Then the plain answers under a
    quiet "Questions", each opening on a tap, so the first view stays clean; the two lines about Claude and Anthropic;
    the footer."""
    contact = (kit.read_json(HELP_FILE, {}) or {}).get("contact")
    contact = contact if isinstance(contact, str) and CONTACT.fullmatch(contact) else ""
    _, button, line = REPORT
    on = model["settings"].get("review") is True
    helpers = model.get("helpers")
    turn = {"on": "off", "off": "on"}.get(helpers)  # the button turns the helpers the other way
    row = lambda name, said, end="", more="", ident="": '<li class="hr"%s><div><b>%s</b><p>%s</p></div>%s%s</li>' % (
        ' id="%s"' % ident if ident else "", esc(name), esc(said), end, more)
    rows = [row("Morning review: %s" % ("On." if on else "Off."), HELP_ROWS["review"],
                "" if on else '<button type="button" class="cta" data-connect data-kind="review" data-app="">Turn on</button>')]
    if turn:
        rows.append(row("Background helpers: %s." % helpers.capitalize(), HELPERS[helpers],
                        '<button type="button" class="cta" data-connect data-kind="helpers-%s" data-app="">Turn %s</button>' % (turn, turn)))
    rows += [row(button, line, '<button type="button" class="cta" id="rep-show">%s</button>' % esc(button),
                '<div class="rep" id="rep" hidden><pre class="rept" id="rep-text" tabindex="0" aria-label="The report"></pre>'
                '<p class="act0"><button type="button" class="cta" id="rep-copy">Copy</button></p></div>'
                '<p class="said" id="rep-said" role="status" aria-live="polite"></p>', ident="report"),
            row("Repair", HELP_ROWS["repair"], '<button type="button" class="cta" data-connect data-kind="repair" data-app="">Repair</button>'),
            row("Privacy", HELP_ROWS["privacy"], '<a class="cta" href="/privacy/" target="_top">Read it</a>')]
    if contact:  # no address drawn until one is set
        rows.append('<li class="hr"><div><b>Write to us</b><p>%s</p></div></li>' % esc(contact))
    items = "".join('<details class="qa" id="q-%s"><summary>%s</summary><p class="ha">%s</p></details>' % (i, esc(t), esc(a)) for i, t, a in HELP)
    body = ('<section data-block="header"><h1 class="crumb"><a href="/" target="_top">Home</a><i aria-hidden="true">/</i><span>Help</span></h1>'
            '<p class="sub">%s</p></section>\n<main class="pg hp">\n'
            '<section class="t sec" data-block="help" aria-label="Help"><ul class="hrows">%s</ul></section>\n'
            '<section class="t sec" data-block="answers" aria-labelledby="h-questions"><h2 class="hq0" id="h-questions">Questions</h2>%s</section>\n'
            '<div class="t foot ai">%s</div>\n</main>\n%s') % (
        esc(HELP_LINE), "".join(rows), items, "".join("<p>%s</p>" % esc(t) for t in kit.SHOP_AI), kit.footer(model["now"]))
    return kit.document("help", "Help", body, accent=205, built_at=model["now"].isoformat(timespec="seconds"), run="by-hand",
                        as_of=model["now"].isoformat(timespec="seconds"), appearance=model["settings"]["appearance"], place=model["place"],
                        scripts=("/home/help.js",), rail=kit.rail(model["apps"], "help", None if model.get("root") is None else model["root"]))


# Privacy. Its two facts, where the logs are and what removing Hydra-OS does, are the install's; until both are in,
# no Privacy page is written.
PRIVACY_FACTS = {"log": "~/Hydra-OS/hydra/logs",
                 "remove": "It asks first, then moves your Hydra-OS folder to the Trash whole, so you can take it back. Your Claude chats stay in Claude."}
ANTHROPIC_PRIVACY = "https://www.anthropic.com/legal/privacy"
PRIVACY_PAGES = (
    ("Wellbeing", "the Apple Health export you drop in, read on your Mac. It never gives a diagnosis, medical advice or a diet plan."),
    ("Goals", "what you tell Claude, and what your pages count."),
    ("Finance", "Monarch and Robinhood through your own connectors, read only, or a file from your bank. It never trades, moves money or "
                "says what to buy or sell."),
    ("People", "Gmail and Google Calendar through your own connectors, read only. It reads who and when, never a message's words or its "
               "subject. It never sends, drafts or changes anything."),
    ("Inbox", "Gmail and Google Calendar through your own connectors, read only. It reads who, when and the subject, never a message's "
              "words. It never sends, drafts or changes anything.",
     ("Claude Code, which runs your chats, keeps its own record of each chat on your Mac. That record can hold what your mail and calendar "
      "sent back, even the parts Claude was never shown. Hydra-OS's pages never keep a message's words. You can delete a chat in the "
      "Claude app at any time.",)),  # a line under it
    ("Research", "it searches the web for topics like yours, in general words, never your name, your city or anything you've typed. "
                 "Your notes stay on your Mac."),
    ("Content", "the YouTube Studio export you drop in, read on your Mac."),
)
PRIVACY_LEAVES = (
    "What Claude reads goes to Anthropic under your account.",
    "Once a day, Hydra-OS checks our public list of pages for updates. That request sends nothing about you. Like any web request, "
    "it shows the site your Mac's internet address.",
    "Research's searches, in general words.",
    "Research also reads public release notes, with no sign-in.",
)


def privacy_page(model):
    """Privacy at /privacy/, its facts filled from the build; None until both are in."""
    log, remove = (" ".join(str(PRIVACY_FACTS.get(k) or "").split()) for k in ("log", "remove"))
    if not log or not remove:
        return None
    sec = lambda title, inner: '<h2 class="hq">%s</h2>%s' % (esc(title), inner)
    para = lambda text: '<p class="ha">%s</p>' % esc(text)
    body = ('<section data-block="header"><h1 class="crumb"><a href="/" target="_top">Home</a><i aria-hidden="true">/</i><span>Privacy</span></h1>'
            '<p class="sub">Your records stay as files on your Mac. There\'s no server of ours.</p></section>\n<main class="pg hp">\n'
            '<section class="t sec" data-block="privacy" aria-label="Privacy">%s</section>\n<div class="t foot ai">%s</div>\n</main>\n%s') % (
        sec("What stays on your Mac", para("Your goals, notes, answers and every page's records stay in Hydra-OS, in your home folder "
                                            "(~/Hydra-OS). We never receive them."))
        + sec("What Claude reads", '<p class="ha">%s <a href="%s" data-open rel="noopener noreferrer">%s</a></p>' % (
            esc("When Claude helps you, in your chat or in the morning review, it reads what each page uses, under your own Claude account, "
                "as in any Claude chat. Anthropic's privacy policy covers that:"), esc(ANTHROPIC_PRIVACY), esc(ANTHROPIC_PRIVACY))
            + para("The morning review uses some of your Claude plan each morning, and more as you add pages."))
        + sec("Page by page", '<ul class="hl">%s</ul>' % "".join("<li><b>%s:</b> %s%s</li>" % (esc(p[0]), esc(p[1]), '<ul class="hl">%s</ul>' % "".join(
            "<li>%s</li>" % esc(t) for t in p[2]) if len(p) > 2 else "") for p in PRIVACY_PAGES))
        + sec("What leaves your Mac", '<ul class="hl">%s</ul>' % "".join("<li>%s</li>" % esc(t) for t in PRIVACY_LEAVES))
        + sec("Your log", para("Hydra-OS keeps a log of what ran, in %s, with keys, passwords and email addresses taken out. It stays on "
                               "your Mac. \"Copy a report\" on the Help page shares only how Hydra-OS is running, never your records, and shows "
                               "you all of it before you copy it." % log))
        + sec("Removing Hydra-OS", para("Tell Claude \"remove Hydra-OS\". %s" % remove)),
        "".join("<p>%s</p>" % esc(t) for t in kit.SHOP_AI), kit.footer(model["now"]))
    return kit.document("privacy", "Privacy", body, accent=205, built_at=model["now"].isoformat(timespec="seconds"), run="by-hand",
                        as_of=model["now"].isoformat(timespec="seconds"), appearance=model["settings"]["appearance"], place=model["place"],
                        rail=kit.rail(model["apps"], "privacy", model.get("root")))


def home_page(model):
    built = model["now"].isoformat(timespec="seconds")
    body = "%s\n<main>\n%s%s\n%s\n</main>\n%s\n%s" % (head(model), updates(model), web(model), asks(model), kit.footer(model["now"]),
                                              kit.tips_html("home", tips(model)) + sheet(model))
    return kit.document("home", "Home", body, accent=205, built_at=built, run="by-hand", as_of=built, appearance=model["settings"]["appearance"],
                        contract="home/v3", scripts=("/home/home.js",), place=model["place"], rail=kit.rail(model["apps"], "home", model.get("root")))


# ---------------------------------------------------------------------------------------------------------------
# Building it, and keeping it fresh

def inputs(root):
    """Every file Home's page is drawn from: what it reads, and its own code and the kit's."""
    apps = kit.registry_apps(root)
    paths = [os.path.join(root, "hydra", n) for n in ("registry.json", "config.json")]  # config.json: the helpers' state, for Help
    paths += [os.path.join(root, "yours", n) for n in ("goals.json", "sources.json", "settings.json", os.path.join("layouts", "home.json"))]
    paths += [os.path.join(root, "hydra", "home", n) for n in ("you.json", "quote.json")]
    for app_id in apps:
        record = kit.record_of(root, app_id, apps)
        paths += [os.path.join(record, "home.json"), os.path.join(record, "say.json")]
        box = inbox(root, apps[app_id], apps)  # a file dropped on its page changes the folder, so Home says it's being read
        if box:
            paths.append(box)
    day = offer(root, apps, "day/1")
    if day:
        paths.append(day)
    paths += [os.path.join(HERE, n) for n in ("page.py", "lines.json") + OWN] + [CHANGELOG]
    paths += [os.path.join(kit.KIT, n) for n in ("kit.py", "icons.json")] + [kit.CATALOG] + [os.path.join(root, "hydra", "shop", n) for n in ("catalog.json", "bought.json")]
    paths.append(os.path.join(root, "hydra", "think", "ran.json"))  # the morning review's run, for its tip
    if os.path.isdir(kit.SHOP_PICTURES):
        paths += [os.path.join(kit.SHOP_PICTURES, n) for n in sorted(os.listdir(kit.SHOP_PICTURES)) if n.endswith(".webp")]
    return paths


def stamp(root, today, now=None):
    """One line that changes when anything Home reads does, or the day does, or (with `now`) an app's say.json passes
    its stale_after, which changes no file."""
    h = hashlib.sha256(today.isoformat().encode("utf-8"))
    if now is not None:
        apps = kit.registry_apps(root)
        h.update(("past due: %s\n" % " ".join(sorted(a for a in apps if past_due(root, a, apps, now)))).encode("utf-8"))
    for path in inputs(root):
        try:
            st = os.stat(path)
            h.update(("%s\0%d\0%d\n" % (path, st.st_mtime_ns, st.st_size)).encode("utf-8"))
        except OSError:
            h.update(("%s\0none\n" % path).encode("utf-8"))
    return h.hexdigest()


def build(root, now=None):
    """Build Home into <root>/hydra/home/page/, whole or not at all. Returns its built_at."""
    now = now or clock()
    # The stamp of what's read is taken before the read, so a file that changes mid-build (Goals' save, say) leaves the
    # stamp behind, and the next fresh() builds again.
    mark = stamp(root, now.date(), now)
    model = read(root, now)
    built = now.isoformat(timespec="seconds")
    home = home_page(model)  # / shows Home itself, in the Claude app's Browser pane
    # the Shop, served at /shop/, from the catalog in force, with what was added from it
    head, cards = kit.shop_body(kit.catalog(model["apps"], root, every=True), model["goals"]["goals"], installed=model["apps"],
                                have=kit.bought(root), foot=kit.shop_doc(root).get("foot"))
    shop = kit.document("shop", "Shop", "%s\n<main class=\"pg\">\n%s\n</main>\n%s" % (head, cards, kit.footer(model["now"])), accent=205,
                        built_at=built, run="by-hand", as_of=built, appearance=model["settings"]["appearance"], place=model["place"],
                        scripts=("/home/shop.js",), rail=kit.rail(model["apps"], "shop", root))
    privacy = privacy_page(dict(model, root=root))  # written once its two facts are in
    pages = {"index.html": home, "frame.html": home, "shop.html": shop, "help.html": help_page(dict(model, root=root)),
             **({"privacy.html": privacy} if privacy else {}),
             "summary.json": json.dumps(summary(model, built), ensure_ascii=False, indent=1) + "\n"}
    for name in OWN:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            pages[name] = f.read()
    pictures = {}  # the Shop's pictures of each catalog page, light and dark, served beside it
    for name in sorted(os.listdir(kit.SHOP_PICTURES)) if os.path.isdir(kit.SHOP_PICTURES) else []:
        if name.endswith(".webp") and not name.startswith("."):
            with open(os.path.join(kit.SHOP_PICTURES, name), "rb") as f:
                pictures["shop-" + name] = f.read()
    folder = page_dir(root)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    for path in (os.path.join(root, "hydra", "home"), folder):
        os.chmod(path, 0o700)
    for name, text in pages.items():
        kit.write_whole(os.path.join(folder, name), text)
    for name, data in pictures.items():
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".kit-")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(folder, name))
    kit.write_whole(os.path.join(folder, "stamp"), mark + "\n")
    return built


def built_at(root):
    """When the page that stands was built, or None when there's none."""
    got = kit.read_json(os.path.join(page_dir(root), "summary.json"), {})
    return got.get("built_at") if isinstance(got, dict) and isinstance(got.get("built_at"), str) else None


def clock():
    """The moment a build is for: the Mac's clock. A test pins it with HYDRA_NOW, an ISO 8601 moment with its offset."""
    return kit.moment(os.environ.get("HYDRA_NOW")) or datetime.datetime.now().astimezone()


def fresh(root):
    """Make sure Home is as new as what it's drawn from, and say when it was built. It never raises: a failure leaves the last page standing."""
    try:
        root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(os.path.join(root, "hydra")):
            return None
        now = clock()
        try:
            with open(os.path.join(page_dir(root), "stamp"), encoding="utf-8") as f:
                last = f.read().strip()
        except OSError:
            last = ""
        if last and last == stamp(root, now.date(), now) and all(os.path.isfile(os.path.join(page_dir(root), n)) for n in ("index.html", "frame.html", "shop.html", "help.html", "summary.json") + OWN):
            return built_at(root)
        # An open page reloads only for a build that's newer than its own, so a rebuild in the same second still moves on.
        before = kit.moment(built_at(root))
        if before and now <= before:
            now = before + datetime.timedelta(seconds=1)
        return build(root, now)
    except Exception:
        try:
            return built_at(root)
        except Exception:
            return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build Hydra-OS's Home into <root>/hydra/home/page/")
    ap.add_argument("--root", default=os.environ.get("HYDRA_ROOT"))
    ap.add_argument("--now", help="the build's moment, ISO 8601 with its offset (default: the clock)")
    args = ap.parse_args(argv)
    if not args.root or not os.path.isdir(os.path.join(os.path.expanduser(args.root), "hydra")):
        print("no Hydra-OS folder at --root", file=sys.stderr)
        return 1
    now = None
    if args.now:
        now = kit.moment(args.now)
        if now is None:
            print("--now is a moment with its offset, like 2025-06-16T10:30:00-04:00", file=sys.stderr)
            return 1
    root = os.path.abspath(os.path.expanduser(args.root))
    try:
        build(root, now)
    except (OSError, ValueError) as e:
        print("Home wasn't built: %s" % type(e).__name__, file=sys.stderr)
        return 1
    print("%s: built" % os.path.join(page_dir(root), "index.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
