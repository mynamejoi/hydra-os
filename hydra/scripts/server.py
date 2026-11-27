#!/usr/bin/env python3
"""Home's server: Home, each installed app's page and the kit, on this Mac only,
and the few writes Home's own pages make.

  /                 Home, <root>/hydra/home/page/frame.html, Home's own page, after Home's own fresh(root)
  /shop/            the Shop, as an explainer: <root>/hydra/home/page/shop.html, after Home's fresh(root)
  /home/            Home's page and the files beside it, after fresh(root)
  /<app>/           an installed app's record's page/, built first when it's older than what it's drawn from
                    (<root>/hydra/<id>/page/ for the main app's own apps)
  /kit/             any file under the main plugin's kit/, from the registry's hydra root

  POST /api/act/<app>/<action>     a page's save (hydralib/act.py)
  POST /api/focus, /api/request, /api/notes, /api/notes/remove; GET /api/panel
  GET and PUT /api/layout          Home's layout, <root>/yours/layouts/home.json
  POST /api/walkthrough            a page's first-visit walkthrough, seen: {} for Home's, {"page": <id>} for an app's
  GET /api/shop                    each catalog page and where it stands, for Home's Shop page
  POST /api/shop/key               {"key"}: a page by its key, added in the background
  POST /api/shop/update            {"id"}: a bought page's newer version, in the background
  POST /api/shop/checkout          {"id"}: the catalog's checkout, opened in their own browser
  POST /api/open                   {"link"}: a link that leaves a page, https only, in their own browser
  /help/, /privacy/                Home's Help and Privacy pages, as /shop/ is
  POST /api/name                   {"name"}: the welcome sheet's name, with no Claude turn
  POST /api/tips/seen              {"app", "tip"}: a tip or connect ask shown, kept once
  POST /api/whats-new              {}: What's new closed for the installed version
  POST /api/widget/remove          {"id": "<app>.<offer>"}: a widget taken off Home from its own menu

What keeps it to the person:
- It listens on config.json's home.listen, a loopback address, and never on every interface; with phone access on,
  also on each home.names entry's one private-network address.
- It answers only a request addressed to it by its own address or one of its names (421 otherwise), so a page on
  another site can't reach it by pointing a name at this Mac.
- A write comes only from its own pages: Origin (or, without one, Referer) is its own address, and the browser says
  Sec-Fetch-Site: same-origin. Each is JSON of a small, fixed size, with each key once.
- It serves only files inside the folders above, never a dot file, never a folder listing. Nothing about a request or
  a device is logged, and a slow client is dropped after 10 seconds.

Run (Python 3.9 standard library only):  python3 server.py [--root DIR] [--port N]
"""
import argparse
import ast
import base64
import datetime
import email.utils
import hashlib
import html
import http.server
import ipaddress
import json
import os
import re
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from hydralib import act, applog, browser, files, pages, panel, registry, settings, shop, upload, widgets, you  # noqa: E402
from hydralib import config as cfg  # noqa: E402
from hydralib import health  # noqa: E402

TIMEOUT = 10
MAX_ACT = 2 * 1024
MAX_SMALL = 1024
MAX_LAYOUT = 16 * 1024
MAX_TILES = 40
WALKTHROUGH_SAID = "The walkthrough won't show again."
SIZES = ("large", "medium", "line")
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
ACT = re.compile(r"/api/act/([a-z][a-z0-9-]{0,39})/([a-z][a-z0-9-]{0,31})")
UPLOAD = re.compile(r"/api/upload/([a-z][a-z0-9-]{0,39})")
RUN_WAIT_FOR_ANOTHER = 1800  # a dropped file's run waits this long for a run that's out
APP = re.compile(r"[a-z][a-z0-9-]{0,39}")
TILE = re.compile(r"[a-z][a-z0-9.-]{0,39}")
PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".mjs": "text/javascript; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
         ".ico": "image/x-icon", ".woff2": "font/woff2", ".woff": "font/woff", ".txt": "text/plain; charset=utf-8"}
# A page that isn't built yet says so, with a Repair button that hands Claude the request: its one script, allowed by
# its sha256 alone, files {"kind": "repair", "app": <its data-app>} as Home's pages do, and shows the answer's line
REPAIR_JS = ("document.getElementById('r').onclick=function(){var b=this,s=document.getElementById('s');b.disabled=true;"
             "fetch('/api/request',{method:'POST',headers:{'Content-Type':'application/json'},"
             "body:JSON.stringify({kind:'repair',app:b.dataset.app})}).then(function(r){return r.json()})"
             ".then(function(j){s.textContent=j.said||''},function(){s.textContent='Not sent.';b.disabled=false})}")
NOT_BUILT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; connect-src 'self'; script-src 'sha256-%s'"
                 % base64.b64encode(hashlib.sha256(REPAIR_JS.encode("utf-8")).digest()).decode("ascii"))


def not_built(app):
    """The page for one that isn't built yet: what's wrong, and Repair for `app` ("" for Hydra-OS itself)."""
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            "<title>Not built yet</title><body style='font:16px/1.5 system-ui;margin:2rem'>"
            "<p>This page isn't built yet.</p><p><button type=button id=r data-app=\"%s\">Repair</button> "
            "<span id=s role=status aria-live=polite></span></p><script>%s</script>"
            % (html.escape(app), REPAIR_JS)).encode("utf-8")
NOT_OURS = "Only Hydra-OS's own pages can save."
SENT_WRONG = "That can't be saved as it was sent."


def listen_address(value, tailnet=False):
    """The one address `value` names when it's loopback (or, with tailnet, a private-network one), or None."""
    try:
        infos = socket.getaddrinfo(value, None, type=socket.SOCK_STREAM)
        ips = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos}
    except (OSError, ValueError, UnicodeError):
        return None
    if len(ips) != 1:
        return None
    ip = ips.pop()
    if ip.is_unspecified or not (ip.is_loopback or (tailnet and any(ip in net for net in TAILNET))):
        return None
    return ip


def phone_on(root):
    s = files.read_json(os.path.join(root, "yours", "settings.json"), {})
    return isinstance(s, dict) and s.get("phone") is True


def _once(pairs):
    """A JSON object whose keys each come once: a key sent twice is refused, never read as its last copy."""
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("a key twice")
        out[k] = v
    return out


def _no_constant(name):
    raise ValueError("no %s" % name)


def check_layout(value, known):
    """Home's layout from PUT /api/layout, in yours/v1's keys for Home: order, hidden and
    widths naming tile ids, each once. Returns (order, hidden, widths) or raises ValueError with a short reason."""
    if not isinstance(value, dict) or set(value) - {"contract", "version", "order", "hidden", "widths"}:
        raise ValueError("A layout has only order, hidden and widths.")
    if value.get("contract", "yours/v1") != "yours/v1":
        raise ValueError("A layout is yours/v1.")
    order, hidden, widths = value.get("order"), value.get("hidden", []), value.get("widths", {})
    if not isinstance(order, list) or not isinstance(hidden, list) or not isinstance(widths, dict):
        raise ValueError("order and hidden are lists, and widths names each tile's size.")
    if len(order) + len(hidden) > MAX_TILES:
        raise ValueError("That's more tiles than Home has.")
    seen = set()
    for t in order + hidden:
        if not isinstance(t, str) or not TILE.fullmatch(t) or t in seen or t not in known:
            raise ValueError("A tile in the layout isn't one of Home's, or comes twice.")
        seen.add(t)
    for t, size in widths.items():
        if t not in order or size not in SIZES:
            raise ValueError("A tile's size is large, medium or line.")
    return list(order), list(hidden), dict(widths)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        """socketserver's bind alone: http.server's also asks for the host's name (socket.getfqdn), a lookup Home never
        needs and one that can wait on the network."""
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), port

    def handle_error(self, request, client_address):  # never log a device's address
        pass


class Server6(Server):
    address_family = socket.AF_INET6


def make_server(ip, port, handler):
    return (Server6 if ip.version == 6 else Server)((str(ip), port), handler)


def make_handler(config, timeout=TIMEOUT, budget=act.BUDGET, clock=None):
    """The request handler for one <root>. clock() gives the time (tests pass a fixed one)."""
    root = config["root"]
    names = [str(n).lower().rstrip(".") for n in (config.get("home") or {}).get("names") or [] if n]
    clock = clock or (lambda: datetime.datetime.now().astimezone())
    focus_at = {"t": None}
    focus_lock = threading.Lock()
    layout_lock = threading.Lock()
    shop_lock = threading.Lock()  # one add or update at a time
    freshener = pages.Freshener(config)

    def main_app():
        return registry.app(root, registry.MAIN) or {}

    def base_of(app):
        """The page folder an app's URL serves, or None for one that isn't installed."""
        main = main_app()
        if app in (main.get("apps") or []):
            return os.path.join(root, "hydra", app, "page")
        entry = registry.app(root, app)
        if entry and entry.get("kind") != "main" and entry.get("record"):
            return os.path.join(entry["record"], "page")
        return None

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "Hydra-OS"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # quiet: no paths or addresses in any log
            pass

        # ---- answering --------------------------------------------------------------------------------------------

        def reply(self, code, body=b"", kind="text/plain; charset=utf-8", store=True, extra=()):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store" if store else "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def said(self, code, said, **more):
            body = json.dumps(dict({"ok": code < 400, "said": said}, **more), ensure_ascii=False).encode("utf-8")
            return self.reply(code, body, "application/json")

        def answer(self, value):
            return self.reply(200, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json")

        # ---- who's asking -----------------------------------------------------------------------------------------

        def hosts(self):
            ip, port = self.server.server_address[:2]
            own = "[%s]" % ip if ":" in ip else ip
            out = {"%s:%d" % (own, port)}
            if ipaddress.ip_address(ip).is_loopback:
                out.add("localhost:%d" % port)
            if phone_on(root):
                for n in names:
                    out |= {"%s:%d" % (n, port), "%s.:%d" % (n, port)}
            return out

        def parse_request(self):
            if not super().parse_request():
                return False
            if (self.headers.get("Host") or "").strip().lower() not in self.hosts():
                self.close_connection = True
                self.reply(421, b"not this server\n")
                return False
            return True

        def own_page(self):
            """True for a write from one of this server's own pages, which needs all three:
            - its Host is one of Home's own names, which keeps out DNS rebinding (parse_request answers any other 421);
            - its Origin is there and is Home's own: a write with no Origin, or "null", is refused;
            - its Sec-Fetch-Site, when the browser sends one, says same-origin. WebKit sends it only from Safari 16.4, so
              on a Mac at macOS 13.0 to 13.2 whose Safari was never updated there's none, and the Origin and Host decide."""
            host = (self.headers.get("Host") or "").strip().lower()
            if host not in self.hosts():
                return False
            origin = (self.headers.get("Origin") or "").strip().lower()
            if not origin or origin != "http://" + host:
                return False
            site = self.headers.get("Sec-Fetch-Site")
            return site is None or site.strip().lower() == "same-origin"

        def body(self, most):
            """The request's JSON, each key once, or None after answering why not."""
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                self.said(415, "Send it as JSON.")
                return None
            if self.headers.get("Transfer-Encoding") is not None:
                self.said(411, "Send it with its length.")
                return None
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self.said(411, "Send it with its length.")
                return None
            if length < 0 or length > most:
                self.close_connection = True
                self.said(413, "That's too big.")
                return None
            try:
                data = self.rfile.read(length)
            except OSError:  # the client stopped sending: drop it
                self.close_connection = True
                return None
            if len(data) != length:
                self.said(400, SENT_WRONG)
                return None
            try:
                return json.loads(data.decode("utf-8"), object_pairs_hook=_once, parse_constant=_no_constant)
            except (ValueError, RecursionError):
                self.said(400, SENT_WRONG)
                return None

        # ---- files ------------------------------------------------------------------------------------------------

        def route(self, path):
            """(folder, file inside it, which page to build first) for a GET path, or None."""
            if path == "/":
                return os.path.join(root, "hydra", "home", "page"), "frame.html", "home"
            if path in ("/shop", "/shop/"):  # Home's build draws it from its catalog
                return os.path.join(root, "hydra", "home", "page"), "shop.html", "home"
            for name in ("help", "privacy"):  # Home's Help and Privacy, built by Home's page.py
                if path in ("/%s" % name, "/%s/" % name):
                    return os.path.join(root, "hydra", "home", "page"), name + ".html", "home"
            parts = path.split("/")[1:]
            if not parts or not parts[0]:
                return None
            if any(p in ("", ".", "..") or not PART.fullmatch(p) for p in parts[1:-1]) or (
                    parts[-1] and not PART.fullmatch(parts[-1])):
                return None
            head, rest = parts[0], "/".join(parts[1:])
            if head == "kit":
                kit = main_app().get("root")
                return (os.path.join(kit, "kit"), rest, None) if kit and rest else None
            if not APP.fullmatch(head):
                return None
            base = base_of(head)
            if not base:
                return None
            name = rest or "index.html"
            build = head if name == "index.html" else None
            return base, name, build

        def serve_file(self):
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if "\x00" in path or "\\" in path:
                return self.reply(404, b"not found\n")
            if APP.fullmatch(path.strip("/")) and not path.endswith("/") and base_of(path.strip("/")):
                return self.reply(301, b"", extra=(("Location", path + "/"),))
            found = self.route(path)
            if not found:
                return self.reply(404, b"not found\n")
            base, name, build = found
            if build == "home":
                pages.home(config)
            elif build:
                pages.app(config, build)
            real_base = os.path.realpath(base)
            real = os.path.realpath(os.path.join(base, name))
            if not real.startswith(real_base + os.sep) or not os.path.isfile(real):
                if build and name in ("index.html", "frame.html"):
                    entry = registry.app(root, build) if build != "home" else None
                    page = build if entry and entry.get("kind") != "main" else ""  # Home's own pages: Hydra-OS itself
                    return self.reply(404, not_built(page), "text/html; charset=utf-8",
                                      extra=(("Content-Security-Policy", NOT_BUILT_CSP),))
                return self.reply(404, b"not found\n")
            try:
                st = os.stat(real)
                since = self.headers.get("If-Modified-Since")
                if since:
                    try:
                        when = email.utils.parsedate_to_datetime(since)
                        if when is not None and int(st.st_mtime) <= when.timestamp():
                            return self.reply(304, b"", store=False)
                    except (TypeError, ValueError, OverflowError):
                        pass
                with open(real, "rb") as f:
                    data = f.read()
            except OSError:
                return self.reply(404, b"not found\n")
            kind = TYPES.get(os.path.splitext(real)[1].lower(), "application/octet-stream")
            return self.reply(200, data, kind, store=False,
                              extra=(("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True)),))

        # ---- the verbs --------------------------------------------------------------------------------------------

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/panel":
                page = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("page", [""])[0]
                if page:  # the page in front names itself as it polls
                    panel.front(root, page, clock())
                freshener.kick()  # an open page learns of a new build only from this answer's `built`
                return self.answer(panel.answer(root, clock()))
            if path == "/favicon.ico":  # a browser asks on every page; nothing to show, and no console error
                return self.reply(204, b"", store=False)
            if path == "/api/shop":  # Home's Shop page asks each second while it's adding
                return self.answer(shop.state(root))
            if path == "/api/report":  # Help's Copy a report: hydra report's exact text
                try:
                    from hydralib import report
                    return self.answer({"ok": True, "report": report.build(cfg.load(root))})
                except Exception:
                    return self.said(500, "Home couldn't make the report just now.")
            if path == "/api/layout":
                doc = files.read_json(os.path.join(root, "yours", "layouts", "home.json"))
                if not isinstance(doc, dict) or doc.get("contract") != "yours/v1":
                    return self.reply(404, b"no layout saved yet\n")
                return self.answer(doc)
            if path.startswith("/api/"):
                takes = path in POSTS or ACT.fullmatch(path) or path.startswith("/api/yours/")
                return self.said(405 if takes else 404, "That isn't something Home answers.")
            return self.serve_file()

        def do_HEAD(self):
            if self.path.startswith("/api/"):
                return self.reply(405, b"")
            if urllib.parse.urlsplit(self.path).path == "/favicon.ico":
                return self.reply(204, b"", store=False)
            return self.serve_file()

        def do_POST(self):
            self.close_connection = True  # one write a connection, so a body left unread is never read as a request
            path = self.path
            u = UPLOAD.fullmatch(path)
            if u:
                if not self.own_page():
                    return self.said(403, NOT_OURS)
                return self.upload(u.group(1))
            y = YOURS.fullmatch(path)
            if y:  # Keep and Undo on the layout-changed bar
                if not self.own_page():
                    return self.said(403, NOT_OURS)
                from hydralib import yours
                try:
                    said = yours.keep(config, y.group(1)) if y.group(2) == "keep" else yours.drop(config, y.group(1))
                except yours.Refused as e:
                    return self.said(400, str(e))
                except Exception:
                    return self.said(500, "Home couldn't do that just now.")
                return self.said(200, said)
            m = ACT.fullmatch(path)
            if not m and path not in POSTS:
                return self.said(404, "That isn't something Home saves.")
            if not self.own_page():
                return self.said(403, NOT_OURS)
            if m:
                value = self.body(MAX_ACT)
                if value is None:
                    return None
                try:
                    code, out = act.handle(config, m.group(1), m.group(2), value, budget=budget)
                except Exception:  # never a traceback, never a half answer
                    return self.said(502, "Home couldn't run that save.")
                return self.reply(code, out, "application/json")
            value = {} if path in ("/api/notes/remove", "/api/walkthrough", "/api/widget/remove",
                                   "/api/whats-new") \
                and self.headers.get("Content-Length") in (None, "0") \
                else self.body(MAX_SMALL)
            if value is None:
                return None
            if not isinstance(value, dict):
                return self.said(400, SENT_WRONG)
            try:
                return POSTS[path](self, value)
            except panel.Refused as e:
                return self.said(400, str(e))
            except files.Newer as e:  # a file a newer Hydra-OS saved, never written over
                return self.said(409, str(e))
            except Exception:
                return self.said(500, "Home couldn't do that just now.")

        def upload(self, app):
            """POST /api/upload/<app>: a file dropped on the app's own page, its name in X-Hydra-File-Name, streamed
            into the app's folder (hydralib/upload.py), then the app's run once, in a process of its own."""
            length = self.headers.get("Content-Length")
            try:
                n = int(length) if length is not None and not self.headers.get("Transfer-Encoding") else -1
            except ValueError:
                n = -1
            name = urllib.parse.unquote(self.headers.get("X-Hydra-File-Name") or "")
            try:
                code, said, path = upload.take(config, app, name, n, self.rfile.read)
            except OSError:
                return self.said(500, "Home couldn't file that just now.")
            if code == 200:
                try:  # waits for a run that's out, so the file is read now and not at tomorrow's run
                    run = subprocess.Popen([config["python"], "-B", "-s", os.path.join(HERE, "tick.py"), "--root",
                                            config["root"], "--run", app, "--wait", str(RUN_WAIT_FOR_ANOTHER)],
                                           cwd=config["root"], env=cfg.run_env(config), stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                           start_new_session=True)
                    threading.Thread(target=run.wait, daemon=True).start()  # reaped when it ends: no zombie stays
                except OSError:
                    pass  # filed all the same: its next run reads it
            return self.said(code, said)

        def do_PUT(self):
            self.close_connection = True
            if self.path != "/api/layout":
                return self.said(405 if ACT.fullmatch(self.path) or self.path in POSTS else 404, "That isn't something Home saves.")
            if not self.own_page():
                return self.said(403, NOT_OURS)
            value = self.body(MAX_LAYOUT)
            if value is None:
                return None
            known = {a["id"] for a in registry.read(root).get("apps", []) if a.get("kind") != "main"}
            known |= set(main_app().get("apps") or [])
            known |= set(widgets.added(root))  # an added widget is a tile too
            try:
                order, hidden, widths = check_layout(value, known)
            except ValueError as e:
                return self.said(400, str(e))
            path = os.path.join(root, "yours", "layouts", "home.json")
            with layout_lock:
                was = files.read_json(path, {})
                version = was.get("version", 0) if isinstance(was, dict) and isinstance(was.get("version"), int) else 0
                doc = {"contract": "yours/v1",
                       "stock": {"app": "home", "layout": "layout/v1", "release": str(main_app().get("version") or "")},
                       "version": version + 1, "order": order, "hidden": hidden, "widths": widths}
                if isinstance(was, dict) and isinstance(was.get("added"), list):
                    doc["added"] = was["added"]  # Claude's widgets stay: only `hydra widget` and their menu change them
                files.write_json(path, doc)
            return self.answer({"ok": True, "said": "Saved.", "version": doc["version"]})

        def do_other(self):
            return self.reply(405, b"")

        do_DELETE = do_PATCH = do_OPTIONS = do_other

        # ---- the small writes -------------------------------------------------------------------------------------

        def focus(self, value):
            if set(value) - {"app", "block", "item"}:
                return self.said(400, SENT_WRONG)
            now = clock()
            with focus_lock:
                last = focus_at["t"]
                if last is not None and abs((now - last).total_seconds()) < 1:
                    return self.said(429, "That was a moment ago.")
                f = panel.focus(root, value.get("app"), value.get("block"), value.get("item", ""), now)
                focus_at["t"] = now
            return self.answer({"ok": True, "label": f["label"]})

        def request(self, value):
            if set(value) - {"kind", "app", "service"}:
                return self.said(400, SENT_WRONG)
            panel.request(root, value.get("kind"), value.get("app"), clock(), service=value.get("service", ""))
            return self.answer({"ok": True, "said": "Now say go to Claude."})

        def note(self, value):
            if set(value) != {"text"}:
                return self.said(400, SENT_WRONG)
            panel.note(root, value["text"], clock())
            return self.answer({"ok": True, "said": "Claude sees it with your next message."})

        def remove_note(self, value):
            if value:
                return self.said(400, SENT_WRONG)
            return self.answer({"ok": True, "removed": panel.remove_note(root)})

        def walkthrough(self, value):
            page = value.get("page", "home") if isinstance(value, dict) else None
            if set(value) - {"page"} or not isinstance(page, str) or \
                    (page != "home" and not (TILE.fullmatch(page) and registry.app(root, page))):
                return self.said(400, SENT_WRONG)
            settings.mark_walkthrough(root, page)
            return self.said(200, WALKTHROUGH_SAID)

        def shop_key(self, value):
            key = value.get("key") if isinstance(value, dict) else None
            if set(value) != {"key"} or not isinstance(key, str):
                return self.said(400, SENT_WRONG)
            try:
                page, key = shop.parse_key(key)
                title = shop._listed(root, page)["title"]
            except shop.Refused as e:
                return self.answer(dict({"ok": False, "said": str(e)}, **({"repair": True} if e.repair else {})))
            return self.shop_work(page, "Adding %s\u2026" % title, lambda: shop.add(config, key))

        def shop_checkout(self, value):
            page = value.get("id") if isinstance(value, dict) else None
            if set(value) != {"id"} or not isinstance(page, str):
                return self.said(400, SENT_WRONG)
            try:
                return self.answer({"ok": True, "said": shop.checkout(root, page)})
            except (shop.Refused, OSError, subprocess.SubprocessError) as e:
                return self.answer({"ok": False, "said": str(e) if isinstance(e, shop.Refused) else "The checkout didn't open. Try again."})

        def home_tips(self):
            """Home's own tips' ids, as Home's page.py declares them, in its TIPS literal: read, never run."""
            main = registry.app(root, registry.MAIN) or {}
            path = os.path.join(main.get("root") or "", "home", "page.py")
            try:
                with open(path, encoding="utf-8") as f:
                    tree = ast.parse(f.read(), path)
                found = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                             and any(isinstance(t, ast.Name) and t.id == "TIPS" for t in n.targets))
                return {t["id"] for t in ast.literal_eval(found) if isinstance(t, dict) and isinstance(t.get("id"), str)}
            except (OSError, SyntaxError, ValueError, StopIteration, TypeError):
                return set()

        def name_save(self, value):
            """The welcome sheet's name, saved on the page with no Claude turn, by hydra name set's rule.
            Empty saves nothing; either way the sheet is seen."""
            if set(value) != {"name"} or not isinstance(value.get("name"), str) or len(value["name"]) > 200:
                return self.said(400, SENT_WRONG)
            text = " ".join(value["name"].split())
            if text:
                kept = you.clean(text)
                if kept is None:
                    return self.answer({"ok": False, "said": "That name can't be saved. Try letters only."})
                you.save(root, kept)
            settings.mark_welcome(root)
            return self.answer({"ok": True})

        def tip_seen(self, value):
            """A tip or connect ask shown, kept once so it's never drawn again: only one the app's
            column.json declares, or one of Home's own, as Home's page.py declares them."""
            app, tip = value.get("app"), value.get("tip")
            if set(value) != {"app", "tip"} or not isinstance(app, str) or not isinstance(tip, str) or \
                    not settings.TIP.fullmatch(tip) or not settings.APP.fullmatch(app):
                return self.said(400, SENT_WRONG)
            if app == "home":
                if tip not in self.home_tips():
                    return self.said(400, SENT_WRONG)
            else:
                entry = registry.app(root, app)
                col = files.read_json(os.path.join((entry or {}).get("root") or "", "column.json"), {}) if entry else {}
                col = col if isinstance(col, dict) else {}
                ids = {t.get("id") for t in col.get("tips") or [] if isinstance(t, dict)}
                ask = col.get("ask") if isinstance(col.get("ask"), dict) else {}
                if tip not in ids and tip != ask.get("id"):
                    return self.said(400, SENT_WRONG)
            settings.mark_tip(root, app, tip)
            return self.answer({"ok": True})

        def whats_new(self, value):
            """What's new closed: the installed main version, seen."""
            if value:
                return self.said(400, SENT_WRONG)
            main = registry.app(root, registry.MAIN) or {}
            try:
                settings.mark_whats_new(root, str(main.get("version") or ""))
            except ValueError:
                return self.said(400, SENT_WRONG)
            return self.answer({"ok": True})

        def open_link(self, value):
            """A link that leaves a page, opened in the person's own browser, never inside the pane."""
            if set(value) != {"link"} or not isinstance(value.get("link"), str):
                return self.said(400, SENT_WRONG)
            if browser.link(value["link"]) is None:
                return self.answer({"ok": False, "said": "That link can't be opened from here."})
            try:
                browser.open_link(value["link"])
            except (OSError, subprocess.SubprocessError, ValueError):
                return self.answer({"ok": False, "said": "It didn't open. Try again."})
            return self.answer({"ok": True, "said": "It opens in your browser."})

        def shop_update(self, value):
            page = value.get("id") if isinstance(value, dict) else None
            if set(value) != {"id"} or not isinstance(page, str) or page not in shop.bought(root):
                return self.said(400, SENT_WRONG)
            return self.shop_work(page, "Updating\u2026", lambda: " ".join(shop.update(config, page)))

        def shop_work(self, page, said, work):
            """An add or an update in the background, one at a time, its line kept for the page's next ask."""
            with shop_lock:
                if shop.state(root)["working"]:
                    return self.answer({"ok": False, "said": "Another page is being added. Try again once it's done."})
                shop.mark(root, page, said)

            def run():
                repair = False
                try:
                    line = work()
                except shop.Refused as e:
                    line, repair = str(e), e.repair
                except Exception:
                    line = "Something stopped it part way, so nothing changed. Try again in a moment."
                shop.mark(root, "", line, repair)

            threading.Thread(target=run, daemon=True).start()
            return self.answer({"ok": True, "said": said})

        def widget_remove(self, value):
            wid = value.get("id") if isinstance(value, dict) else None
            if set(value) != {"id"} or not isinstance(wid, str) or wid.count(".") != 1:
                return self.said(400, SENT_WRONG)
            with layout_lock:
                try:
                    said = widgets.remove(root, *wid.split("."))
                except ValueError as e:
                    return self.said(400, str(e))
            return self.answer({"ok": True, "said": said})

    POSTS = {"/api/focus": Handler.focus, "/api/request": Handler.request, "/api/notes": Handler.note,
             "/api/notes/remove": Handler.remove_note,
             "/api/walkthrough": Handler.walkthrough, "/api/widget/remove": Handler.widget_remove,
             "/api/shop/key": Handler.shop_key, "/api/shop/update": Handler.shop_update,
             "/api/shop/checkout": Handler.shop_checkout, "/api/open": Handler.open_link, "/api/name": Handler.name_save,
             "/api/tips/seen": Handler.tip_seen, "/api/whats-new": Handler.whats_new}
    Handler.timeout = timeout
    return Handler


def servers(config, port=None, v6=False, **kw):
    """The listening servers for this <root>: home.listen, and with phone access each name's private-network address.
    v6, as Home's own start asks: on 127.0.0.1, ::1 too, on the same port, so localhost reaches Home whichever address a
    client tries first, as the Claude app's Browser pane opens Home by launch.json's http://localhost:<port>. Raises
    ValueError for an address that isn't one."""
    home = config.get("home") or {}
    ip = listen_address(str(home.get("listen") or ""))
    if ip is None:
        raise ValueError("home.listen isn't a loopback address, so Home's server won't start.")
    port = home.get("port") if port is None else port
    handler = make_handler(config, **kw)
    out = [make_server(ip, port, handler)]
    if v6 and ip == ipaddress.ip_address("127.0.0.1"):  # localhost may be ::1 first
        try:
            out.append(make_server(ipaddress.ip_address("::1"), out[0].server_address[1], handler))
        except OSError:
            pass  # no IPv6 loopback on this Mac, or its port is taken there: 127.0.0.1 answers localhost alone
    if phone_on(config["root"]):
        for n in home.get("names") or []:
            other = listen_address(str(n), tailnet=True)
            if other is not None and other != ip:
                out.append(make_server(other, out[0].server_address[1], handler))
    return out


YOURS = re.compile(r"/api/yours/([a-z][a-z0-9-]{0,23})/(keep|drop)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Home's server for one Hydra-OS folder")
    ap.add_argument("--root", help="the root (default: HYDRA_ROOT, the nearest hydra/config.json, then ~/Hydra-OS)")
    ap.add_argument("--port", type=int, help="a port in place of config.json's (tests)")
    args = ap.parse_args(argv)
    try:
        config = cfg.load(os.path.abspath(os.path.expanduser(args.root))) if args.root else cfg.load()
    except cfg.NotInstalled as e:
        print(str(e), file=sys.stderr)
        return 1
    applog.use(config["root"])  # its notes go to the folder's own log
    try:  # a part-done add or update put back first, so the Shop never sticks on Adding
        shop.recover(config, startup=True)
    except Exception:
        pass
    try:
        running = servers(config, port=args.port, v6=True)
    except (ValueError, OSError) as e:
        print(str(e) if isinstance(e, ValueError) else "Home's port is in use.", file=sys.stderr)
        return 2
    for s in running[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print("Home answers on port %d." % running[0].server_address[1], flush=True)
    try:
        running[0].serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
