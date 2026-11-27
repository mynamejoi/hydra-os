#!/usr/bin/env python3
"""The `hydra` command: everything Claude changes in Hydra-OS goes through it, after the person's yes, and
`<root>/.claude/settings.json` allows it by name. Each prints one plain line, or a few,
and exits 0 when it did what it said, 2 when it refused (with why), and 1 when Hydra-OS isn't installed.

  hydra sources add <page> <source> --via <via> --reads "<what>" [--server "<name>"] [--account <word>]
  hydra sources remove <page> <source> [--account <word>]
  hydra sources list
  hydra act <page> <action> [--<field>=<value> ...] [--yes [--token=<t>]]
  hydra goals <verb> [--<field>=<value> ...] [--yes [--token=<t>]]          (hydra act goals <verb>)
  hydra panel point <page> <block> [<item> ...] [--say "<words>"]
  hydra panel clear
  hydra panel done <request-id>
  hydra where <page> | <name>/<version>
  hydra run <page>
  hydra settings set <key> <value>
  hydra notes add "<line>"
  hydra name set "<their name>"
  hydra place set "<city>" --lat=<number> --lon=<number>
  hydra place clear
  hydra first skip name|goal|connect
  hydra widget add|remove <page> <offer>
  hydra add --key <key> | hydra add <pack file> --key <key>
  hydra update [hydra | <page>]
  hydra remove <page>
  hydra shop
  hydra setup <page>
  hydra report
  hydra helpers [on | off]
  hydra yours <page> move <part> before|after <part> | hide <part> | show <part> | widen <part> full|half|third |
    rename <part> "<title>" | add <kind> <data> ["<title>"] | keep | undo | back <version> | stock
  hydra think | hydra think save <page> [--part <id>] (its answer written to the path hydra think names, or
    --answer '<JSON>', or the JSON on stdin) | hydra think done <page>"""
import datetime
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from hydralib import act, applog, files, panel, registry, runs, settings, shop, sources, think, widgets, you  # noqa: E402
from hydralib import claude as cl  # noqa: E402
from hydralib import config as cfg  # noqa: E402

USAGE = __doc__.split("\n\n")[1]
SETTINGS = {"appearance": ("sun", "light", "dark", "system"), "suggestions": ("on", "off"), "phone": ("on", "off"),
            "review": ("on", "off")}
NOTES_MOST = 8 * 1024
NOTE_MOST = 280
SECRET = re.compile(r"[A-Za-z0-9_\-.=+/]{24,}")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
FIELD = re.compile(r"--([a-z][a-z0-9_]{0,31})=(.*)", re.S)
SETUP_MOST = 16 * 1024
RUN_WAIT = 5.0  # seconds `hydra run` waits to say how the run started


class Refused(Exception):
    """A plain-words reason nothing changed."""


def now_local():
    return datetime.datetime.now().astimezone()


def title_of(root, app):
    entry = registry.app(root, app)
    return str((entry or {}).get("title") or app)


# ---- sources ---------------------------------------------------------------------------------------------------------

def sources_cmd(config, args):
    root = config["root"]
    if not args:
        raise Refused(USAGE)
    verb, rest = args[0], args[1:]
    if verb == "list":
        rows = sources.read(root)
        if not rows:
            return ["No source is connected yet."]
        known = sources.names(root)  # each by its page's name for its id
        return ["%s feeds %s (%s)%s" % (sources.label(r, known), title_of(root, r.get("app")), r.get("via"),
                                        ", account %s" % r["account"] if r.get("account") else "") for r in rows]
    opts, pos = _options(rest, ("via", "reads", "server", "account"))
    if verb == "add":
        if len(pos) != 2 or not opts.get("via") or not opts.get("reads"):
            raise Refused('Say it as: hydra sources add <page> <source> --via <via> --reads "<what it reads>"')
        app, source = pos
        reg = registry.read(root)
        installed = {a["id"] for a in reg.get("apps", []) if a.get("kind") != "main"}
        entry = registry.app(root, app) or {}
        col = files.read_json(os.path.join(entry.get("root") or "", "column.json"), {})
        declared = [s for s in (col.get("sources") or []) if isinstance(s, dict) and isinstance(s.get("id"), str)] \
            if isinstance(col, dict) else []
        listed = cl.mcp_servers(config["claude"], config.get("claude_config", "")) if opts["via"] == "connector" else []
        try:
            got = sources.add(root, app, source, opts["via"], opts["reads"], installed, declared, opts.get("server", ""),
                              listed, opts.get("account", ""))
        except sources.Refused as e:
            raise Refused(str(e))
        panel.done_for(root, "connect", app, now_local())
        title = title_of(root, app)
        upload = next((s for s in declared if s.get("id") == got["id"] and s.get("kind") in ("upload", "file")), None)
        if opts["via"] == "file" and upload and entry.get("record"):
            where = _inbox(entry["record"], upload)
            if where:
                kinds = [str(k).upper() for k in upload.get("accepts") or [] if isinstance(k, str)]
                return ["%s now feeds %s. Put the file in %s%s; %s reads it from its next run." % (
                    sources.label(got, sources.names(root)), title, files.tilde(where), (", as " + " or ".join(kinds)) if kinds else "", title)]
        return ["%s now feeds %s. %s reads it from its next run." % (sources.label(got, sources.names(root)), title, title)]
    if verb == "remove":
        if len(pos) != 2:
            raise Refused("Say it as: hydra sources remove <page> <source>")
        if sources.remove(root, pos[0], pos[1], opts.get("account", "")):
            return ["%s no longer feeds %s." % (pos[1], title_of(root, pos[0]))]
        raise Refused("%s has no source by that name." % title_of(root, pos[0]))
    raise Refused(USAGE)


def _inbox(record, upload):
    """The folder, inside the app's record, that its upload source reads files from (`folder`, inbox/ by default),
    made empty when it isn't there yet; None for one that would leave the record."""
    folder = str(upload.get("folder") or "inbox/").strip("/")
    if not folder or any(part in ("", ".", "..") for part in folder.split("/")) or folder.startswith("~"):
        return None
    path = os.path.join(record, folder)
    if not os.path.realpath(path).startswith(os.path.realpath(record) + os.sep):
        return None
    if not os.path.isdir(path):
        files.folder(path)
    return path


def _options(args, names):
    """({name: value}, positional) from --name value and --name=value."""
    opts, pos, i = {}, [], 0
    while i < len(args):
        a = args[i]
        m = re.fullmatch(r"--([a-z]+)(?:=(.*))?", a, re.S)
        if m and m.group(1) in names:
            if m.group(2) is not None:
                opts[m.group(1)] = m.group(2)
            elif i + 1 < len(args):
                opts[m.group(1)] = args[i + 1]
                i += 1
            else:
                raise Refused("--%s needs a value." % m.group(1))
        elif a.startswith("--"):
            raise Refused("%s isn't something this takes." % a.split("=")[0])
        else:
            pos.append(a)
        i += 1
    return opts, pos


# ---- act and goals ---------------------------------------------------------------------------------------------------

def act_cmd(config, app, args):
    if not args:
        raise Refused("Say which action, as the page's column.json names it.")
    action, rest = args[0], args[1:]
    fields, yes, token = {}, False, None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--yes":
            yes = True
        elif a == "--token" and i + 1 < len(rest):
            token = rest[i + 1]
            i += 1
        elif a.startswith("--token="):
            token = a[len("--token="):]
        else:
            m = FIELD.fullmatch(a)
            if not m or m.group(1) in fields:
                raise Refused("Each field comes once, as --<field>=<value>.")
            fields[m.group(1)] = m.group(2)
        i += 1
    status, answer = act.chat(config, app, action, fields, yes=yes, token=token)
    out = [str(answer.get("said") or "")]
    if answer.get("token"):
        out.append("token: %s" % answer["token"])
    if isinstance(answer.get("undo"), dict) and answer.get("ok"):
        out.append("undo fields: " + " ".join("--%s=%s" % (k, v) for k, v in answer["undo"].items()))
    if status != 200 or not answer.get("ok"):
        raise Refused("\n".join(out))
    return out


# ---- the panel -------------------------------------------------------------------------------------------------------

def panel_cmd(config, args):
    root = config["root"]
    if not args:
        raise Refused(USAGE)
    verb, rest = args[0], args[1:]
    try:
        if verb == "go":  # gone: nothing opened a page by it; Claude opens one by its address
            raise Refused("Open the page in the Browser pane by its own address instead.")
        if verb == "point":
            opts, pos = _options(rest, ("say",))
            if len(pos) < 2:
                raise Refused("Say it as: hydra panel point <page> <block> [<item> ...]")
            app, block, items = pos[0], pos[1], pos[2:]
            panel.point(root, app, block, items, opts.get("say", ""), now=now_local())
            label = panel._label(panel.summary(root, app) or {}, block, "")
            return ["Outlined %s on %s's page for two minutes." % (label, title_of(root, app))]
        if verb == "clear" and not rest:
            panel.clear(root)
            return ["The outline is gone."]
        if verb == "done" and len(rest) == 1:
            if panel.done(root, rest[0], now_local()):
                return ["Marked done."]
            raise Refused("That request isn't open.")
    except panel.Refused as e:
        raise Refused(str(e))
    raise Refused(USAGE)


# ---- where -----------------------------------------------------------------------------------------------------------

def where_cmd(config, args):
    root = config["root"]
    if len(args) != 1:
        raise Refused("Say it as: hydra where <page>, or hydra where <name>/<version>")
    name = args[0]
    if "/" in name:
        found = registry.where(root, name)
        if not found:
            raise Refused("No installed page offers %s." % name)
        return ["%s is %s's, at %s." % (name, title_of(root, found[0]), files.tilde(found[1]))]
    entry = registry.app(root, name)
    if not entry or entry.get("kind") == "main":
        raise Refused("That page isn't installed.")
    return ["%s's installed release is %s, and its record is %s." % (title_of(root, name), files.tilde(entry.get("root") or ""),
                                                                    files.tilde(entry.get("record") or ""))]


# ---- run -------------------------------------------------------------------------------------------------------------

def run_cmd(config, args):
    """Start the app's run in a process of its own, so a long run never outlasts the chat's wait, and say how it went
    within a few seconds."""
    root = config["root"]
    if len(args) != 1:
        raise Refused("Say it as: hydra run <page>")
    app = args[0]
    out = runs.running(root)
    if out:
        raise Refused("Another page is running now. Try again once it's done.")
    p = subprocess.Popen([config["python"], "-B", "-s", os.path.join(HERE, "tick.py"), "--root", root, "--run", app],
                         cwd=root, env=cfg.run_env(config), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    try:  # a run that ends within the wait says how it went; a longer one keeps going in its own process
        said = (p.communicate(timeout=RUN_WAIT)[0] or b"").decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        p.stdout.close()
        panel.done_for(root, "repair", app, now_local())  # the run is what a Repair tap asked for (seams, Tier 3)
        return ["%s's run started. Its page fills in when it's done." % title_of(root, app)]
    if p.returncode != 0:
        raise Refused(said or "The run couldn't start.")
    panel.done_for(root, "repair", app, now_local())
    return [said]


# ---- settings and notes ----------------------------------------------------------------------------------------------

def settings_cmd(config, args):
    root = config["root"]
    if len(args) != 3 or args[0] != "set":
        raise Refused("Say it as: hydra settings set <key> <value>, with appearance, suggestions, phone or review.")
    key, value = args[1], args[2]
    if key not in SETTINGS or value not in SETTINGS[key]:
        raise Refused("appearance is sun, light, dark or system; suggestions is on or off.")
    if key == "phone":
        raise Refused("Phone access comes in a later version of Hydra-OS.")
    new = settings.read(root)  # every other key kept as it is, the walkthrough's "seen" with them
    if key == "appearance":
        new["appearance"] = value
    elif key == "review":
        new["review"] = value == "on"
    else:
        new["suggestions"] = value == "on"
    settings.write(root, new)
    if key == "appearance":
        return ["Appearance is now %s." % {"sun": "following the sun"}.get(value, value)]
    if key == "review":
        return ["The morning review is on." if value == "on" else "The morning review is off, and it won't be asked again."]
    return ["Suggestions are %s." % ("shown" if value == "on" else "hidden, on every page and on Home")]


def notes_cmd(config, args):
    root = config["root"]
    if len(args) != 2 or args[0] != "add":
        raise Refused('Say it as: hydra notes add "<line>"')
    line = " ".join(args[1].split())
    if not 1 <= len(line) <= NOTE_MOST or CONTROL.search(line):
        raise Refused("A note is one line of at most %d characters." % NOTE_MOST)
    if SECRET.search(line):
        raise Refused("That looks like a key or a token, so it wasn't kept. Notes are words only.")
    path = os.path.join(root, "yours", "claude.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(NOTES_MOST + 1)
    except OSError:
        text = ""
    text = (text.rstrip("\n") + "\n" if text.strip() else "") + "- " + line + "\n"
    if len(text.encode("utf-8")) > NOTES_MOST:
        raise Refused("Your notes are full (8 KB). Take something out of %s first." % files.tilde(path))
    files.write_text(path, text)
    return ["Kept. Claude reads it at the start of each session."]


def name_cmd(config, args):
    """The name Home's greeting shows, saved once the person tells Claude their name: their answer to
    Claude's question is their yes for this one save."""
    if len(args) != 2 or args[0] != "set":
        raise Refused('Say it as: hydra name set "<their name>"')
    name = you.clean(args[1])
    if name is None:
        raise Refused("A name is letters, at most %d, with spaces, hyphens or apostrophes between. Nothing was saved."
                      % you.MOST)
    you.save(config["root"], name)
    return ["Saved. Home's greeting now has their name."]


def place_cmd(config, args):
    """Their city, asked once, last and optional: set with the
    latitude and longitude Claude gives from what it knows, so no lookup service is called, or cleared when they pass,
    so it's never asked again. Their answer is their yes for that one save."""
    root = config["root"]
    if args == ["clear"]:
        you.clear_place(root)
        return ["No city is kept, and it won't be asked again."]
    if not args or args[0] != "set":
        raise Refused('Say it as: hydra place set "<city>" --lat=<number> --lon=<number>, or hydra place clear')
    opts, pos = _options(args[1:], ("lat", "lon"))
    if len(pos) != 1 or "lat" not in opts or "lon" not in opts:
        raise Refused('Say it as: hydra place set "<city>" --lat=<number> --lon=<number>')
    city = you.clean_city(pos[0])
    if city is None:
        raise Refused("A city is letters, at most %d, with spaces, hyphens, apostrophes, periods or commas between. "
                      "Nothing was saved." % you.CITY_MOST)
    try:
        lat, lon = you.check_place(opts["lat"], opts["lon"], time.localtime().tm_gmtoff)
    except ValueError as e:
        raise Refused(str(e))
    you.save_place(root, city, lat, lon)
    return ["Saved. The sky follows %s now." % city]


def widget_cmd(config, args):
    """Add a widget: one of an installed app's offers onto Home, after the person's yes, kept in their
    own layer, yours/layouts/home.json's added, which updates never touch; or taken away again (hydralib/widgets.py)."""
    if len(args) != 3 or args[0] not in ("add", "remove"):
        raise Refused("Say it as: hydra widget add <page> <offer>, or hydra widget remove <page> <offer>")
    try:
        said = (widgets.add if args[0] == "add" else widgets.remove)(config["root"], args[1], args[2])
    except ValueError as e:
        raise Refused(str(e))
    if args[0] == "add":  # Add a widget's request, named or not, is closed by the add that answers it (seams, Tier 3)
        for named in (args[1], ""):
            panel.done_for(config["root"], "add-app", named, now_local())
    return [said]


# ---- the shop -------------------------------------------------------------------------------

def add_cmd(config, args):
    """A page by the key on their receipt, or from a pack file with its key, for tests and offline use."""
    opts, pos = _options(args, ("key",))
    if not opts.get("key") or len(pos) > 1:
        raise Refused("Say it as: hydra add --key <the key on their receipt>, or hydra add <pack file> --key <key>")
    try:
        return [shop.add(config, opts["key"], pos[0] if pos else None)]
    except shop.Refused as e:
        raise Refused(str(e))


def update_cmd(config, args):
    """hydra update: Hydra-OS itself first, then each page added from the shop once Hydra-OS went through; hydra
    update hydra, Hydra-OS alone; hydra update <page>, that page alone."""
    if len(args) > 1:
        raise Refused("Say it as: hydra update, or hydra update <page>")
    page = args[0] if args else None
    out = []
    if page in (None, registry.MAIN):
        from hydralib import update
        out = update.core(config)
        if page == registry.MAIN or not update.went_through(out):
            return out
    try:
        return out + shop.update(config, page)
    except shop.Refused as e:
        raise Refused(str(e))


def remove_cmd(config, args):
    if args[:1] == [registry.MAIN] and args[1:] in ([], ["--yes"]):  # Hydra-OS itself
        from hydralib import remove
        try:
            return remove.remove(config, yes=args[1:] == ["--yes"])
        except remove.Stop as e:
            raise Refused(str(e))
    if len(args) != 1:
        raise Refused("Say it as: hydra remove <page>, or hydra remove hydra for Hydra-OS itself")
    try:
        return [shop.remove(config, args[0])]
    except shop.Refused as e:
        raise Refused(str(e))


def shop_cmd(config, args):
    if args:
        raise Refused("Say it as: hydra shop")
    words = {"available": "on sale, not added", "not-ready": "not ready to add yet", "needs-hydra": "needs a newer Hydra-OS",
             "in-rail": "in your rail", "update": "a newer version is ready", "adding": "being added now"}
    pages_ = shop.state(config["root"])["pages"]
    if not pages_:
        return ["The shop lists no page yet."]
    return ["%s%s: %s%s." % (p["title"], " " + p["have"] if p["have"] else "", words[p["state"]],
                             " (%s)" % p["version"] if p["state"] == "update" else "") for p in pages_]


def setup_cmd(config, args):
    """A page's set-up steps from its own SETUP.md: a page bought in this chat has
    its own skills only from the next chat, so the main app carries "set up <page>" for it."""
    if len(args) != 1:
        raise Refused("Say it as: hydra setup <page>")
    entry = registry.app(config["root"], args[0])
    if not entry or entry.get("kind") == "main":
        raise Refused("That page isn't one of theirs.")
    path = os.path.join(entry.get("root") or "", "SETUP.md")
    try:
        with open(path, encoding="utf-8") as f:
            steps = f.read(SETUP_MOST + 1)
    except OSError:
        raise Refused("%s has no set-up steps of its own. Its page says what it needs." % title_of(config["root"], args[0]))
    if len(steps) > SETUP_MOST:
        steps = steps[:SETUP_MOST] + "\n(cut here; the rest is in %s)" % files.tilde(path)
    return ["%s's set-up steps, from its own SETUP.md:" % title_of(config["root"], args[0]), steps.rstrip()]


def think_cmd(config, args):
    """The morning review: its guidance and each page's input, or one page's answer saved."""
    if args[:1] == ["done"] and len(args) == 2:
        try:
            return [think.save(config, args[1], "", done=True)]
        except think.Refused as e:
            raise Refused(str(e))
    if args[:1] == ["save"]:
        opts, pos = _options(args[1:], ("answer", "part"))
        if len(pos) != 1:
            raise Refused("Say it as: hydra think save <page> [--part <id>] --answer '<the JSON>', or the JSON on stdin")
        if "answer" in opts:
            answer, most = opts["answer"], think.ANSWER_MOST
        else:  # the answer the Write tool put at its path (think.answer_path), else on stdin
            try:
                answer, most = think.take_answer(config["root"], pos[0], opts.get("part")), think.STDIN_MOST
            except think.Refused as e:
                raise Refused(str(e))
            if answer is None:
                answer = sys.stdin.read(think.STDIN_MOST + 1)
        try:
            return [think.save(config, pos[0], answer, part=opts.get("part"), most=most)]
        except think.Refused as e:
            raise Refused(str(e))
    if args:
        raise Refused("Say it as: hydra think")
    return think.prompt(config)


def helpers_cmd(config, args):
    """Hydra-OS's two helpers, Home's server and the tick, at login or not, after the person's yes: `hydra helpers` says
    which, `on` starts them at login, `off` stops that (hydralib/helpers.py)."""
    from hydralib import helpers, jobs
    if args == []:
        return [helpers.ON if helpers.is_on(config) else helpers.OFF]
    if args == ["on"]:
        load = jobs.load
        if os.environ.get("HYDRA_TEST_LAUNCHCTL"):  # tests only: launchctl's stand-in
            load = jobs.test_load(os.environ["HYDRA_TEST_LAUNCHCTL"], os.path.expanduser("~"))
        return helpers.on(config, load)
    if args == ["off"]:
        return helpers.off(config)
    raise Refused("Say it as: hydra helpers, hydra helpers on, or hydra helpers off")


def first_cmd(config, args):
    """A first-session step they skipped or declined in the chat, kept so it's never asked again: their
    name, their first goal, or their Health data for now. Their no is the yes for it."""
    if len(args) != 2 or args[0] != "skip" or args[1] not in you.SKIPS:
        raise Refused("Say it as: hydra first skip name, goal or connect")
    you.skip(config["root"], args[1])
    return ["Kept: it won't be asked again."]


# ---- main ------------------------------------------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    try:
        config = cfg.load()
    except cfg.NotInstalled as e:
        print(str(e))
        return 1
    applog.use(config["root"])  # its notes go to the folder's own log (applog)
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "sources":
            out = sources_cmd(config, rest)
        elif cmd == "act":
            if not rest:
                raise Refused("Say it as: hydra act <page> <action> [--<field>=<value> ...]")
            out = act_cmd(config, rest[0], rest[1:])
        elif cmd == "goals":
            out = act_cmd(config, "goals", rest)
        elif cmd == "panel":
            out = panel_cmd(config, rest)
        elif cmd == "where":
            out = where_cmd(config, rest)
        elif cmd == "run":
            out = run_cmd(config, rest)
        elif cmd == "settings":
            out = settings_cmd(config, rest)
        elif cmd == "notes":
            out = notes_cmd(config, rest)
        elif cmd == "name":
            out = name_cmd(config, rest)
        elif cmd == "place":
            out = place_cmd(config, rest)
        elif cmd == "first":
            out = first_cmd(config, rest)
        elif cmd == "widget":
            out = widget_cmd(config, rest)
        elif cmd == "add":
            out = add_cmd(config, rest)
        elif cmd == "yours":  # a page's layout in the person's own layer
            from hydralib import yours
            if len(rest) < 2:
                raise Refused("Say it as: hydra yours <page> move|hide|show|widen|rename|add|keep|undo|back|stock ...")
            app, verb, more = rest[0], rest[1], rest[2:]
            try:
                if verb == "keep" and not more:
                    out = [yours.keep(config, app)]
                elif verb in ("undo", "drop") and not more:
                    out = [yours.drop(config, app)]
                elif verb == "back" and len(more) == 1:
                    out = [yours.back(config, app, more[0])]
                elif verb == "stock" and not more:
                    out = [yours.stock(config, app)]
                else:
                    out = [yours.preview(config, app, verb, more)]
            except yours.Refused as e:
                raise Refused(str(e))
        elif cmd == "report":  # how Hydra-OS is running, states and counts only
            if rest:
                raise Refused("Say it as: hydra report")
            from hydralib import report
            out = [report.build(config)]
        elif cmd == "update":
            out = update_cmd(config, rest)
        elif cmd == "remove":
            out = remove_cmd(config, rest)
        elif cmd == "shop":
            out = shop_cmd(config, rest)
        elif cmd == "setup":
            out = setup_cmd(config, rest)
        elif cmd == "think":
            out = think_cmd(config, rest)
        elif cmd == "helpers":
            out = helpers_cmd(config, rest)
        else:
            raise Refused(USAGE)
    except (Refused, files.Newer) as e:  # a file a newer Hydra-OS saved is never written over
        print(str(e))
        return 2
    for line in out:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
