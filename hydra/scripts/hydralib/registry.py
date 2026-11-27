"""`<root>/hydra/registry.json`, registry/v1, written whole on install, remove and each tick, from every installed app's
column.json and `yours/sources.json`.

The installed plugins are `$HYDRA_PLUGINS/<app>` when HYDRA_PLUGINS is set (tests), else what `claude plugin list
--json` shows from the store's list, asked only in a step the person takes in the chat; the tick builds from the pages
already listed (listed_pages), so it never starts Claude Code. The main app is listed too, as `hydra`, with its `root`, so
a page finds the kit in the same release Home's server serves it from."""
import datetime
import os
import re

from . import claude as cl
from . import files, sources

CONTRACT = "registry/v1"
MAIN = "hydra"


def path(root):
    return os.path.join(root, "hydra", "registry.json")


def read(root):
    doc = files.read_json(path(root), {})
    return doc if isinstance(doc, dict) and doc.get("contract") == CONTRACT else {"contract": CONTRACT, "apps": []}


def app(root, app_id):
    """The registry's entry for an app, or None."""
    return next((a for a in read(root).get("apps", []) if a.get("id") == app_id), None)


def listed_pages(config):
    """[(id, plugin root)] without asking Claude Code: each page the registry already lists, from the last build that
    asked it, or, with none, each page in Hydra-OS's own store list, from its folder there. The tick builds from these,
    so it never starts Claude Code; pages come and go only through a step the person takes in the chat."""
    root = config["root"]
    found = [(a["id"], a["root"]) for a in read(root).get("apps", []) if isinstance(a.get("id"), str)
             and isinstance(a.get("root"), str) and os.path.isfile(os.path.join(a["root"], "column.json"))]
    if found:
        return found
    store = (config.get("store") or {}).get("folder") or os.path.join(root, "hydra", "store")
    market = files.read_json(os.path.join(store, ".claude-plugin", "marketplace.json"), {})
    for e in (market.get("plugins") or []) if isinstance(market, dict) else []:
        if isinstance(e, dict) and isinstance(e.get("name"), str) and isinstance(e.get("source"), str):
            where = os.path.realpath(os.path.join(store, e["source"]))
            if where.startswith(os.path.realpath(store) + os.sep) and os.path.isfile(os.path.join(where, "column.json")):
                found.append((e["name"], where))
    return found


def installed(config, env=None):
    """[(id, plugin root)] for each installed plugin with a column.json."""
    env = os.environ if env is None else env
    found = []
    given = env.get("HYDRA_PLUGINS")
    if given:
        base = os.path.expanduser(given)
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            plugin = os.path.join(base, name)
            if os.path.isfile(os.path.join(plugin, "column.json")):
                found.append((name, os.path.realpath(plugin)))
        return found
    # the folder Claude Code loads a plugin in place from comes first: it's Hydra-OS's own store, which each setup copies
    # fresh, while Claude Code's own copy isn't refreshed as long as the version is the same
    for p in cl.plugins(config["claude"], config.get("claude_config", ""), config["store"]["name"], cwd=config["root"],
                        env=env):
        for where in (p.get("folder"), p["path"]):
            if where and os.path.isfile(os.path.join(where, "column.json")):
                found.append((p["name"], os.path.realpath(where)))
                break
    return found


def _version(plugin_root):
    doc = files.read_json(os.path.join(plugin_root, ".claude-plugin", "plugin.json"), {})
    return str(doc.get("version") or "") if isinstance(doc, dict) else ""


FITS_SCRIPT = re.compile(r"scripts/[a-z0-9_]{1,40}\.py")


def fits(value):
    """A page's `fits` from its column.json, as Building's shape has it: `units`,
    up to 16 goal units of 1 to 16 characters each, may be []; `script`, its own goals script, scripts/<name>.py; and
    `what`, up to 120 characters for Goals' "What counts your goals". Anything else is left out, and a page with no
    valid `units` has {}."""
    if not isinstance(value, dict) or not isinstance(value.get("units"), list):
        return {}
    units = value["units"]
    if len(units) > 16 or not all(isinstance(u, str) and 1 <= len(u) <= 16 and u.strip() == u and u.isprintable()
                                  for u in units):
        return {}
    out = {"units": list(units)}
    if isinstance(value.get("script"), str) and FITS_SCRIPT.fullmatch(value["script"]):
        out["script"] = value["script"]
    if isinstance(value.get("what"), str) and 0 < len(value["what"]) <= 120 and value["what"].isprintable():
        out["what"] = value["what"]
    return out


def build(config, now=None, env=None, listed=False):
    """Build registry.json from what's installed and what the person chose, write it whole, and return it. listed: the
    pages as listed_pages has them, with no Claude Code call, as the tick builds it."""
    root = config["root"]
    now = now or datetime.datetime.now().astimezone()
    chosen = {}
    for r in sources.read(root):
        if r.get("id") and r.get("app") not in chosen:
            chosen[r["app"]] = r["id"]
    cols = []
    env_ = os.environ if env is None else env
    plugins = installed(config, env) if not listed or env_.get("HYDRA_PLUGINS") else listed_pages(config)
    for app_id, plugin in plugins:
        col = files.read_json(os.path.join(plugin, "column.json"), {})
        if isinstance(col, dict) and col.get("id") == app_id:
            cols.append((app_id, plugin, col))
    offered = {}
    for app_id, _, col in cols:
        for o in col.get("offers") or []:
            if isinstance(o, dict) and o.get("name") and o.get("version"):
                offered.setdefault(f"{o['name']}/{o['version']}", app_id)
    apps = []
    for app_id, plugin, col in cols:
        main = col.get("kind") == "main"
        entry = {"id": app_id, "title": str(col.get("title") or app_id), "accent": col.get("accent"),
                 "icon": col.get("icon"), "home": col.get("home") if isinstance(col.get("home"), dict) else None,
                 "version": _version(plugin), "root": plugin,
                 # the goals it can count: an explicit null counts no goal by matching
                 "fits": None if "fits" in col and col["fits"] is None else fits(col.get("fits")),
                 "record": os.path.join(root, MAIN) if main else os.path.join(root, app_id)}
        if main:
            entry["kind"] = "main"
            entry["apps"] = [a for a in col.get("apps") or [] if isinstance(a, str)]
        entry["offers"] = [f"{o['name']}/{o['version']}" for o in col.get("offers") or [] if isinstance(o, dict) and o.get("name")]
        uses = []
        for u in col.get("uses") or []:
            if isinstance(u, dict) and u.get("name"):
                key = f"{u['name']}/{u.get('version', 1)}"
                by = offered.get(key, "")
                ok = by and (u.get("from") in (None, "any", by))
                uses.append({"name": key, "filled_by": by if ok else "", "missing": not ok})
        entry["uses"] = uses
        entry["source"] = chosen.get(app_id)
        sched = col.get("schedule")
        entry["schedule"] = ({"at": sched.get("at", ""), "days": sched.get("days", "daily")}
                             if isinstance(sched, dict) and sched.get("run") else None)
        if isinstance(sched, dict) and sched.get("after") == "each":
            entry["schedule"]["after"] = "each"
        apps.append(entry)
    order = {"hydra": 0, "dreams": 2}
    apps.sort(key=lambda a: (order.get(a["id"], 1), (a.get("schedule") or {}).get("at") or "99:99", a["id"]))
    doc = {"contract": CONTRACT, "built_at": now.replace(microsecond=0).isoformat(), "apps": apps}
    files.write_json(path(root), doc)
    return doc


def where(root, name_version):
    """(app id, the offer's file path) for an offer such as "days/1", or None (`hydra where`)."""
    name, _, version = name_version.partition("/")
    for a in read(root).get("apps", []):
        if name_version in a.get("offers", []):
            col = files.read_json(os.path.join(a["root"], "column.json"), {})
            for o in col.get("offers") or []:
                if isinstance(o, dict) and o.get("name") == name and str(o.get("version")) == version:
                    return a["id"], os.path.join(a["record"], o.get("file", ""))
    return None
