"""Research's public release notes, read in code on the tick, with no sign-in and no Claude:
Claude Code's, the Claude API's and the Claude app's release notes, and the official plugin marketplace. They fill
"What changed in Claude's tools".

- **The lock:** allow.json lists the only addresses read, each a plain GET with no cookie and nothing of the person's.
  The client reads it before every request, refuses any address it doesn't list or whose site isn't in its own ceiling
  (SITES), and refuses a redirect off the page's own site.
- **What's kept** (store/releases.json): each page's lines as a reader sees them, one line a block, each with the day it
  was first seen, the newest LINES of them, and a fingerprint of every line seen, never the page itself. A first look
  keeps what's there as seen, and shows only a changelog's newest version, so a first day isn't a flood.
- **A page that can't be read** keeps its last read, and the block says so with the day of that read.

    python3 scripts/release.py [--record DIR] [--now ISO] [--offline]

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.parse
import urllib.request

import common
import store

ALLOW = common.ROOT / "allow.json"
SITES = ("https://raw.githubusercontent.com", "https://platform.claude.com", "https://support.claude.com")  # the ceiling
KINDS = ("text", "html", "marketplace")
LINES = 20        # lines kept a page, newest first
NEW = 40          # new lines taken from one read, at most
LINE = 300        # a line's characters, at most
SHORT = 24        # a line shorter than this is a page's furniture (menus, buttons), not news
TIMEOUT = 20
MOST = 8_000_000
AGENT = "hydra-os-research/1.0"


class Refused(Exception):
    """An address the lock doesn't allow."""


def site(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    return f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else ""


def allowed() -> list:
    """allow.json's sources, each checked against the ceiling; [] when it can't be read, so nothing is fetched."""
    doc = common.load_json(ALLOW, {}) or {}
    out = []
    for s in doc.get("sources") or [] if isinstance(doc, dict) else []:
        if not isinstance(s, dict) or s.get("kind") not in KINDS:
            continue
        url, link = str(s.get("url") or ""), str(s.get("link") or "")
        if site(url) in SITES and url.startswith("https://") and link.startswith("https://") and s.get("id") and s.get("name"):
            out.append({k: str(s[k]) for k in ("id", "name", "kind", "url", "link")})
    return out


class SameSite(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if site(newurl) != site(req.full_url):
            raise Refused("a redirect off the page's own site")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str) -> str:
    if url not in {s["url"] for s in allowed()}:
        raise Refused("an address allow.json doesn't list")
    opener = urllib.request.build_opener(SameSite)
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with opener.open(req, timeout=TIMEOUT) as r:
        return r.read(MOST).decode("utf-8", errors="replace")


def lines_of(text: str, kind: str) -> list:
    """A page's text, one line a block, as a reader would see it. A marketplace is its plugins, a line each."""
    if kind == "marketplace":
        try:
            doc = json.loads(text)
        except ValueError:
            return []
        out = []
        for p in doc.get("plugins", []) if isinstance(doc, dict) else []:
            if isinstance(p, dict) and p.get("name"):
                desc = " ".join(str(p.get("description") or "").split())
                out.append(f"{p['name']}: {desc}"[:LINE] if desc else str(p["name"])[:LINE])
        return out
    if kind == "html":
        text = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<(br|/p|/li|/h[1-6]|/div|/tr|/section|/article)\b[^>]*>", "\n", text, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    out = []
    for line in text.splitlines():
        line = " ".join(line.lstrip("-*# ").split())
        if len(line) >= SHORT:
            out.append(line[:LINE])
    return out


def newest_version(text: str) -> list:
    """A changelog's newest version's lines: the bullets under its first "## " heading."""
    out, inside = [], False
    for raw in text.splitlines():
        if raw.startswith("## "):
            if inside:
                break
            inside = True
            continue
        if inside and raw.lstrip().startswith(("- ", "* ")):
            line = " ".join(raw.strip().lstrip("-* ").split())
            if len(line) >= SHORT:
                out.append(line[:LINE])
    return out


def fingerprint(line: str) -> str:
    return hashlib.sha256(line.lower().encode("utf-8")).hexdigest()[:16]


def read(rec, now, getter=fetch, offline: bool = False) -> dict:
    """Every allowed page, read once and kept: {"read": n, "failed": n, "new": n}. Offline, nothing is fetched and every
    page keeps its last read."""
    kept = store.releases(rec)
    today = now.astimezone().date().isoformat()
    counts = {"read": 0, "failed": 0, "new": 0}
    for s in allowed():
        last = kept.get(s["id"]) if isinstance(kept.get(s["id"]), dict) else {}
        entry = {"name": s["name"], "link": s["link"], "checked_at": last.get("checked_at", ""),
                 "read_at": last.get("read_at", ""), "ok": False, "lines": last.get("lines") or [],
                 "seen": last.get("seen") or []}
        entry["checked_at"] = common.iso(now)
        if offline:
            counts["failed"] += 1
            kept[s["id"]] = entry
            continue
        try:
            text = getter(s["url"])
        except Exception:  # noqa: BLE001  (a page that can't be read keeps its last read; the block says so)
            counts["failed"] += 1
            kept[s["id"]] = entry
            continue
        lines = lines_of(text, s["kind"])
        seen = set(entry["seen"])
        first = not seen
        fresh, taken = [], set()
        if first:
            fresh = newest_version(text) if s["kind"] == "text" else []
        else:
            for line in lines:
                f = fingerprint(line)
                if f not in seen and f not in taken:
                    fresh.append(line)
                taken.add(f)
        fresh = fresh[:NEW]
        entry["lines"] = ([{"text": t, "seen": today} for t in fresh] + list(entry["lines"]))[:LINES]
        entry["seen"] = sorted(seen | {fingerprint(line) for line in lines} | {fingerprint(t) for t in fresh})
        entry.update(ok=True, read_at=common.iso(now))
        counts["read"] += 1
        counts["new"] += len(fresh)
        kept[s["id"]] = entry
    store.save_releases(rec, kept)
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{common.TITLE}'s public release notes, read once, in code.")
    ap.add_argument("--record")
    ap.add_argument("--now")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    rec = common.record_dir(a.record)
    if not rec.is_dir():
        print(f"release: {common.TITLE}'s folder isn't there yet.", file=sys.stderr)
        return 1
    c = read(rec, common.now(a.now), offline=a.offline)
    print(f"release: {c['read']} pages read, {c['failed']} not, {c['new']} new lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
