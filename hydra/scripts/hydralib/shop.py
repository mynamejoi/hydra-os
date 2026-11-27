"""The buying path: a page on sale, added by its key, from the catalog Hydra-OS's own key signed.

A page on sale arrives by its key. The key's first word is the page's id ("finance-..."), and the whole key opens the
page's sealed pack. Home's server, or `hydra add --key`, then works with no Claude turn: it fetches the pack the catalog
names, checks its sha256, opens it with the Mac's own /usr/bin/openssl, installs it into the store as setup does, adds
it to Claude Code from the store, and rebuilds the registry. All of that happens whole or not at all: a step that fails
puts back what came before it and says why in one plain line.

  catalog(root)                the catalog in force: the shop's signed one, checked again, or the bundled cards alone
  read_catalog(config, now)    the daily read: the catalog the settings name and its signature, kept once it checks out
  signed(data, sig)            whether the shop's key signed those bytes, by the Mac's own /usr/bin/openssl
  add(config, key, pack=None)  a page by its key, from the catalog's pack, or from a pack file (tests, offline)
  update(config, page=None)    each bought page the catalog has newer, with its kept key, one version kept back
  remove(config, page)         a bought page out of Claude Code and the store; its records stay
  state(root)                  each catalog page and where it stands, for Home's Shop page and `hydra shop`
  bought_entries(root)         the store's marketplace entries for bought pages, for setup's store step to keep

The shop's catalog is signed: <catalog>.sig beside it holds the base64 of
an ECDSA P-256 signature over its exact bytes, made with a key kept off GitHub, whose public half ships here
(scripts/shop_key.json). Nothing is listed, opened or installed unless /usr/bin/openssl checks that signature, so a
catalog or a pack changed by anyone without the key, a stolen GitHub login among them, reaches no one. Every pack is
trusted only through the signed catalog's sha256, a pack file given by hand too.

Python 3.9, standard library only, and /usr/bin/openssl."""
import base64
import binascii
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from . import catalog as home_catalog
from . import claude as cl
from . import config as cfg
from . import files, registry

OPENSSL = "/usr/bin/openssl"
CIPHER = ["-aes-256-cbc", "-pbkdf2", "-md", "sha256"]
KEY = re.compile(r"([a-z][a-z0-9]{0,23})-([A-Za-z0-9-]{8,128})")
ID = re.compile(r"[a-z][a-z0-9-]{0,23}")
VERSION = re.compile(r"\d{1,4}(\.\d{1,4}){0,3}")
SHA256 = re.compile(r"[0-9a-f]{64}")
PACK_MOST = 64 * 1024 * 1024
CATALOG_MOST = 256 * 1024
SIG_MOST = 4 * 1024  # a catalog's .sig: one line of base64
SIGNATURE_MOST = 512  # bytes of the signature itself
KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shop_key.json")
CATALOG_EVERY = datetime.timedelta(hours=20)
FETCH_WAIT = 30  # seconds
KEEP = 2  # versions of a bought page kept in the store: the one in use and the one before
PRICE_MOST = 40


class Refused(Exception):
    """One plain line on why nothing changed; with `repair`, a page draws Repair beside it, which hands Claude the
    request, and Claude offers it."""

    def __init__(self, said="", repair=False):
        super().__init__(said)
        self.repair = repair


def folder(root):
    return os.path.join(root, "hydra", "shop")


def _p(root, name):
    return os.path.join(folder(root), name)


def _now():
    return datetime.datetime.now().astimezone()


def _iso(now):
    return now.replace(microsecond=0).isoformat()


def vt(version):
    """A version as a tuple of numbers, for comparing; () for one that isn't a version."""
    return tuple(int(x) for x in version.split(".")) if isinstance(version, str) and VERSION.fullmatch(version) else ()


# ---- the catalog -------------------------------------------------------------------------------------------------

def _page(p, base=""):
    """One catalog page in its shape, or None. A pack named by a relative path is taken from the catalog's own
    folder, so a local test catalog works where it lies."""
    if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not ID.fullmatch(p["id"]):
        return None
    out = {k: p[k] for k in ("id", "title", "does", "reads", "needs", "for_goal", "icon", "accent") if isinstance(p.get(k), str)}
    if "title" not in out:
        return None
    out["fits"] = p["fits"] if isinstance(p.get("fits"), dict) else {}
    out["version"] = p["version"] if VERSION.fullmatch(str(p.get("version") or "")) else ""
    out["sha256"] = p["sha256"] if SHA256.fullmatch(str(p.get("sha256") or "")) else ""
    out["min_hydra"] = p["min_hydra"] if VERSION.fullmatch(str(p.get("min_hydra") or "")) else ""
    checkout = p.get("checkout") if isinstance(p.get("checkout"), str) else ""
    out["checkout"] = checkout if checkout.startswith("https://") else ""
    out["pack"] = _named(p.get("pack"), base)
    out["price"] = price(p.get("price"))
    return out


def price(value):
    """The card's price as the catalog gives it: one plain line of at most 40 characters, as "$29, paid once"; "" until
    it's set, and for anything else, so Home's card hides it."""
    text = " ".join(value.split()) if isinstance(value, str) else ""
    return text if len(text) <= PRICE_MOST and "://" not in text and "www." not in text.lower() else ""


NOTES_MOST, NOTE_MOST = 5, 120  # the core's notes, its What's new in short


def _named(value, base=""):
    """A pack's or the core zip's address: an https one as it is; a file name alone from the folder the catalog came
    from, https or, for a local test catalog, a path; else ""."""
    value = value if isinstance(value, str) else ""
    if not value or value.startswith("https://"):
        return value
    if base.startswith("https://"):
        return base + value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) and ".." not in value else ""
    value = os.path.normpath(os.path.join(base, value)) if base and not os.path.isabs(value) else value
    return value if base and os.path.isabs(value) else ""


def _folder_of(address):
    """The folder an address names its files from: an https one up to its last /, a local one's folder."""
    if address.startswith("https://"):
        return address[:address.rfind("/") + 1]
    return os.path.dirname(address) if address else ""


def core(value, base=""):
    """The signed catalog's latest core, or None: {"version", "zip", "sha256",
    "notes"}, its zip an https address and its notes at most five plain lines of at most 120 characters, as Home's
    "Hydra-OS <version> is ready." shows it and hydra update fetches it. A local test catalog's zip is named from
    its own folder, as its packs are; no other catalog's zip may be local."""
    if not isinstance(value, dict) or not VERSION.fullmatch(str(value.get("version") or "")):
        return None
    zip_url = _named(value.get("zip"), base)
    digest = value.get("sha256") if isinstance(value.get("sha256"), str) else ""
    notes = [" ".join(n.split()) for n in value.get("notes") or [] if isinstance(n, str)][:NOTES_MOST]
    return {"version": value["version"], "zip": zip_url,
            "sha256": digest if SHA256.fullmatch(digest) else "",
            "notes": [n for n in notes if n and len(n) <= NOTE_MOST and "://" not in n]}


def _doc(doc, base=""):
    if not isinstance(doc, dict) or doc.get("contract") != "catalog/v1" or not isinstance(doc.get("pages"), list):
        return None
    pages = [x for x in (_page(p, base) for p in doc["pages"]) if x]
    out = {"contract": "catalog/v1", "pages": pages, "foot": doc.get("foot") if isinstance(doc.get("foot"), str) else ""}
    latest = core(doc.get("core"), base)
    if latest:
        out["core"] = latest
    return out


def _pem(public_key):
    """A public key's PEM text from its base64 DER, or None for one that isn't plain base64."""
    if not isinstance(public_key, str) or not public_key or len(public_key) > 1024:
        return None
    try:
        der = base64.b64decode(public_key, validate=True)
    except (ValueError, binascii.Error):
        return None
    lines = [public_key[i:i + 64] for i in range(0, len(public_key), 64)]
    return der, ("-----BEGIN PUBLIC KEY-----\n%s\n-----END PUBLIC KEY-----\n" % "\n".join(lines)).encode("ascii")


def shop_key(env=None):
    """The shop's public key as PEM bytes, or None, so nothing checks out: scripts/shop_key.json (shop-key/v1, its base64
    DER and the sha256 it must have), shipped with the main plugin. HYDRA_TEST_SHOP_KEY names a made-up one for a
    test, an absolute path to a .pem, or to a shop-key/v1 .json."""
    env = os.environ if env is None else env
    path = env.get("HYDRA_TEST_SHOP_KEY") or KEY_PATH
    if not os.path.isabs(path) or not os.path.isfile(path) or os.path.getsize(path) > 8192:
        return None
    if path.endswith(".pem"):
        with open(path, "rb") as f:
            return f.read()
    doc = files.read_json(path, None)
    got = _pem(doc.get("public_key")) if isinstance(doc, dict) and doc.get("contract") == "shop-key/v1" else None
    if not got or hashlib.sha256(got[0]).hexdigest() != doc.get("fingerprint"):
        return None
    return got[1]


def signed(data, sig, env=None):
    """Whether sig, the base64 of a DER ECDSA signature, signs data's exact bytes by the shop's key, as the Mac's own
    /usr/bin/openssl checks it, and nothing else does. Never raises."""
    pem = shop_key(env)
    if not pem or not isinstance(data, bytes) or not os.access(OPENSSL, os.X_OK):
        return False
    try:
        raw = base64.b64decode(b"".join((sig.encode("ascii") if isinstance(sig, str) else sig or b"").split()),
                               validate=True)
    except (ValueError, TypeError, binascii.Error):
        return False
    if not raw or len(raw) > SIGNATURE_MOST:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="hydra-signed-") as work:
            body, mark, key = (os.path.join(work, n) for n in ("catalog", "catalog.sig", "key.pem"))
            for path, value in ((body, data), (mark, raw), (key, pem)):
                with open(path, "wb") as f:
                    f.write(value)
            r = subprocess.run([OPENSSL, "dgst", "-sha256", "-verify", key, "-signature", mark, body],
                               env={"PATH": "/usr/bin:/bin"}, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == b"Verified OK"


def _bytes(path, most):
    try:
        with open(path, "rb") as f:
            data = f.read(most + 1)
    except OSError:
        return None
    return data if len(data) <= most else None


def _signed(root, env=None):
    """The catalog the shop's key signed, read again from the exact bytes the daily read kept and checked again, or
    None. A local catalog's packs are named from its own folder, as the daily read found them."""
    data, sig = _bytes(_p(root, "catalog.signed.json"), CATALOG_MOST), _bytes(_p(root, "catalog.signed.sig"), SIG_MOST)
    if data is None or sig is None or not signed(data, sig, env):
        return None
    meta = files.read_json(_p(root, "catalog.json"), {})
    source = meta.get("source") if isinstance(meta, dict) and isinstance(meta.get("source"), str) else ""
    try:
        return _doc(json.loads(data.decode("utf-8")), _folder_of(source))
    except ValueError:
        return None


def catalog(root, env=None):
    """The catalog in force: the shop's signed catalog as the daily read kept it, checked again each time, or else the
    main plugin's bundled home/catalog.json for its cards alone: with no pack and no sha256, since a pack is
    trusted only through a catalog the shop's key signed."""
    got = _signed(root, env)
    if got:
        return got
    path = home_catalog.path(root)
    doc = _doc(files.read_json(path, None) if path else None, os.path.dirname(path) if path else "") or \
        {"contract": "catalog/v1", "pages": [], "foot": ""}
    for p in doc["pages"]:
        p.update(pack="", sha256="")
    doc.pop("core", None)  # a core, like a pack, is trusted only through a catalog the shop's key signed
    return doc


def sources(config, env=None):
    """The catalog's addresses in order: the first, then its mirror, each https or,
    in test mode, an absolute local path; HYDRA_TEST_SHOP_CATALOG and HYDRA_TEST_SHOP_MIRROR name a test's."""
    env = os.environ if env is None else env
    shop_cfg = config.get("shop") if isinstance(config.get("shop"), dict) else {}
    out = []
    for given in (env.get("HYDRA_TEST_SHOP_CATALOG") or shop_cfg.get("catalog"),
                  env.get("HYDRA_TEST_SHOP_MIRROR") or ("" if env.get("HYDRA_TEST_SHOP_CATALOG") else shop_cfg.get("mirror"))):
        if isinstance(given, str) and (given.startswith("https://") or os.path.isabs(given)) and given not in out:
            out.append(given)
    return out


def source(config, env=None):
    """The catalog the settings name: config.json's shop.catalog, an https address or, in test mode, an absolute local
    path; HYDRA_TEST_SHOP_CATALOG names one for a test. "" when none is named."""
    env = os.environ if env is None else env
    given = env.get("HYDRA_TEST_SHOP_CATALOG") or ((config.get("shop") or {}).get("catalog") if isinstance(config.get("shop"), dict) else "")
    return given if isinstance(given, str) and (given.startswith("https://") or os.path.isabs(given)) else ""


def _fetch(address, most, dest=None):
    """The bytes at an https address or a local path, at most `most`, sending nothing but the request; or to `dest`."""
    if address.startswith("https://"):
        req = urllib.request.Request(address, headers={"User-Agent": "Hydra-OS"})
        with urllib.request.urlopen(req, timeout=FETCH_WAIT) as r:
            data = r.read(most + 1)
    else:
        with open(address, "rb") as f:
            data = f.read(most + 1)
    if len(data) > most:
        raise Refused("That file is larger than a page ever is, so it wasn't taken.")
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
    return data


def read_catalog(config, now=None, force=False, env=None):
    """The daily read: the catalog the settings name and its signature, <catalog>.sig, at
    most once in 20 hours. Once the shop's key is found to have signed it, its exact bytes and signature are kept
    (catalog.signed.json, catalog.signed.sig) for every later check, and its pages, with when it was read, go to
    <root>/hydra/shop/catalog.json, which Home's Shop page draws. Returns "read", "kept" (not due yet), "none" (no
    catalog is named), "offline" (it couldn't be read) or "refused" (its signature didn't check out); with either of
    the last two, the last copy stands. Never raises."""
    root = config["root"]
    now = now or _now()
    addresses = sources(config, env)
    if not addresses:
        return "none"
    last = files.read_json(_p(root, "catalog.json"), {})
    try:
        at = datetime.datetime.fromisoformat(str((last or {}).get("read_at")))
    except ValueError:
        at = None
    if not force and at and at.tzinfo and now - at < CATALOG_EVERY and last.get("source") in addresses:
        return "kept"
    result = "offline"
    for address in addresses:  # the first, then its mirror; the shop's key checked either way
        got = _read_one(address, env)
        if isinstance(got, tuple):
            data, sig, doc = got
            break
        result = "refused" if got == "refused" else result
    else:
        return _tried(root, now, result)
    files.folder(folder(root))
    for name, value in (("catalog.signed.json", data), ("catalog.signed.sig", sig)):
        fd, tmp = tempfile.mkstemp(prefix="." + name + ".", dir=folder(root))
        with os.fdopen(fd, "wb") as f:
            f.write(value)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _p(root, name))
    doc.update({"read_at": _iso(now), "source": address})
    files.write_json(_p(root, "catalog.json"), doc)
    return _tried(root, now, "read", address)


def _read_one(address, env=None):
    """(bytes, signature, catalog) from one address, or "offline" or "refused"."""
    try:
        data = _fetch(address, CATALOG_MOST)
    except (OSError, ValueError, Refused):
        return "offline"
    try:
        sig = _fetch(address + ".sig", SIG_MOST)
    except urllib.error.HTTPError:
        sig = b""  # the shop serves none: refused below
    except urllib.error.URLError:
        return "offline"
    except (OSError, ValueError, Refused):
        sig = b""
    if not signed(data, sig, env):
        return "refused"
    try:
        doc = _doc(json.loads(data.decode("utf-8")), _folder_of(address))
    except ValueError:
        doc = None
    return (data, sig, doc) if doc else "refused"


def _tried(root, now, result, address=""):
    """The daily read's last try, <root>/hydra/shop/read.json ({"at", "result"}: read, offline or refused), for hydra
    report and the doctor, so a catalog that didn't check out is seen, not only skipped. Returns the result."""
    try:
        files.write_json(_p(root, "read.json"), dict({"at": _iso(now), "result": result},
                                                      **({"source": address} if address else {})))
    except OSError:
        pass
    return result


# ---- what's bought ------------------------------------------------------------------------------------------------

def bought(root):
    doc = files.read_json(_p(root, "bought.json"), {})
    pages = doc.get("pages") if isinstance(doc, dict) else None
    return {k: v for k, v in (pages or {}).items() if ID.fullmatch(str(k)) and isinstance(v, dict)
            and VERSION.fullmatch(str(v.get("version") or ""))} if isinstance(pages, dict) else {}


def _write_bought(root, pages):
    files.refuse_newer(_p(root, "bought.json"), "bought/v1")
    files.write_json(_p(root, "bought.json"), {"contract": "bought/v1", "pages": pages})


def _keys(root):
    doc = files.read_json(_p(root, "keys.json"), {})
    return {k: v for k, v in doc.items() if isinstance(v, str)} if isinstance(doc, dict) else {}


def _write_keys(root, keys):
    files.write_json(_p(root, "keys.json"), keys)  # 0600, as every file Hydra-OS writes


def bought_entries(root):
    """The store's marketplace entries for bought pages whose folder is in the store, for setup's store step to keep
   : a core update never drops a bought page."""
    store = os.path.join(root, "hydra", "store")
    out = []
    for page, b in sorted(bought(root).items()):
        rel = "%s/%s" % (page, b["version"])
        if os.path.isfile(os.path.join(store, rel, ".claude-plugin", "plugin.json")):
            out.append({"name": page, "source": "./" + rel, "version": b["version"]})
    return out


def hydra_version(root):
    main = registry.app(root, registry.MAIN) or {}
    return str(main.get("version") or "")


# ---- opening a pack ----------------------------------------------------------------------------------------------

def parse_key(key):
    key = " ".join(str(key or "").split())
    m = KEY.fullmatch(key)
    if not m:
        raise Refused("That isn't a key Hydra-OS knows. A key starts with its page's name, as finance-...")
    return m.group(1), key


def _unseal(pack, key, out):
    """Open a sealed pack with the Mac's own openssl, the key passed in its environment, never on a command line."""
    if not os.access(OPENSSL, os.X_OK):
        raise Refused("This Mac's own openssl isn't there, so the page couldn't be opened.")
    r = subprocess.run([OPENSSL, "enc", "-d"] + CIPHER + ["-in", pack, "-out", out, "-pass", "env:HYDRA_SHOP_KEY"],
                       env={"PATH": "/usr/bin:/bin", "HYDRA_SHOP_KEY": key}, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    if r.returncode != 0:
        raise Refused("That key doesn't open it. Check the key on your receipt.")


def _extract(tar, dest):
    """A page's files out of its tar: plain files and folders only, nothing outside `dest`, folders 0700 and files 0600
    (0700 for one that was executable), as setup's store copy has them."""
    with tarfile.open(tar, "r:gz") as t:
        for m in t.getmembers():
            name = os.path.normpath(m.name)
            if name.startswith(("/", "..")) or os.path.isabs(name) or ".." in name.split(os.sep) or not (m.isfile() or m.isdir()):
                raise Refused("That pack holds something a page never does, so it wasn't taken.")
            target = os.path.join(dest, name)
            if m.isdir():
                files.folder(target)
                continue
            files.folder(os.path.dirname(target))
            src = t.extractfile(m)
            with open(target, "wb") as f:
                shutil.copyfileobj(src, f)
            os.chmod(target, 0o700 if m.mode & 0o100 else 0o600)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _plugin(folder_):
    doc = files.read_json(os.path.join(folder_, ".claude-plugin", "plugin.json"), {})
    return doc if isinstance(doc, dict) else {}


# ---- installing ------------------------------------------------------------------------------------------------------

def _marketplace(root):
    return os.path.join(root, "hydra", "store", ".claude-plugin", "marketplace.json")


def _claude(config, args, env=None, timeout=300):
    return cl.run(config["claude"], args, config.get("claude_config", ""), env, timeout=timeout, cwd=config["root"])


def _install(config, page, version, staged, key, env=None, prune=True):
    """Put a staged page into the store and Claude Code, whole or not at all, then rebuild the registry. An update
    prunes its older versions only once it has gone through whole (prune=False, then prune_versions)."""
    root = config["root"]
    store = os.path.join(root, "hydra", "store")
    target = os.path.join(store, page, version)
    market_path = _marketplace(root)
    market_before = files.read_json(market_path, None)
    if not isinstance(market_before, dict) or not isinstance(market_before.get("plugins"), list):
        raise Refused("Hydra-OS's store isn't set up here, so nothing changed.", repair=True)
    pages_before = bought(root)
    keys_before = _keys(root)
    had = pages_before.get(page)
    page_folder_was = os.path.isdir(os.path.join(store, page))
    aside = target + ".before"
    # what a killed install leaves to be put back at the next start (recover)
    files.write_json(_p(root, JOURNAL), {"contract": "installing/v1", "page": page, "version": version,
                                         "folder_was": page_folder_was, "market": market_before, "bought": pages_before,
                                         "keys": keys_before, "pid": os.getpid(), "at": _iso(_now())})
    if os.path.exists(target):
        shutil.rmtree(aside, ignore_errors=True)
        os.replace(target, aside)
    files.folder(os.path.dirname(target))
    os.replace(staged, target)

    def back():
        shutil.rmtree(target, ignore_errors=True)
        if os.path.exists(aside):
            os.replace(aside, target)
        if not page_folder_was:  # a page that was never here leaves no folder behind
            shutil.rmtree(os.path.join(store, page), ignore_errors=True)
        files.write_json(market_path, market_before)
        _write_bought(root, pages_before)
        _write_keys(root, keys_before)

    try:
        doc = dict(market_before)
        doc["plugins"] = [e for e in market_before["plugins"] if not (isinstance(e, dict) and e.get("name") == page)]
        doc["plugins"].append({"name": page, "source": "./%s/%s" % (page, version), "version": version})
        files.write_json(market_path, doc)
        pages_now = dict(pages_before)
        pages_now[page] = {"version": version, "previous": had["version"] if had and had["version"] != version else
                           (had or {}).get("previous", ""), "at": _iso(_now())}
        _write_bought(root, pages_now)
        if key:
            keys = dict(keys_before)
            keys[page] = key
            _write_keys(root, keys)
        _claude(config, ["plugin", "marketplace", "update", cfg.STORE], env, timeout=120)  # read the store again
        verb = "update" if had else "install"
        code, _ = _claude(config, ["plugin", verb, "%s@%s" % (page, cfg.STORE), "--scope", "local"], env)
        if code != 0:
            raise Refused("Claude couldn't add it from Hydra-OS's store, so nothing changed. Try again in a moment.")
        reg = registry.build(config, env=env)
        entry = next((a for a in reg.get("apps", []) if a.get("id") == page), None)
        if not entry:
            raise Refused("It didn't show among your pages, so nothing changed. Try again in a moment.")
    except Refused:
        back()
        _claude(config, ["plugin", "marketplace", "update", cfg.STORE], env, timeout=120)  # back to what the store says
        registry.build(config, env=env)
        _unjournal(root)
        raise
    except Exception:
        back()
        registry.build(config, env=env)
        _unjournal(root)
        raise Refused("Something stopped it part way, so nothing changed. Try again in a moment.")
    _unjournal(root)
    shutil.rmtree(aside, ignore_errors=True)
    if prune:
        prune_versions(root, page, version)
    files.folder(entry["record"])
    try:
        from . import pages as page_builds
        page_builds.app(config, page, force=True)
    except Exception:
        pass  # the page is built at its first look, as every page is
    _offer(config, page, env)
    return entry


JOURNAL = "installing.json"  # in hydra/shop/: an install under way, kept until it ends either way
UPDATING = "updating.json"  # in hydra/shop/: a page's update under way, with its backup (hydralib/update.py)
QUIET = datetime.timedelta(minutes=10)  # an Adding mark or a staging folder older than this, with no one at it


def _unjournal(root, name=JOURNAL):
    try:
        os.unlink(_p(root, name))
    except OSError:
        pass


def _gone(doc):
    """Whether the process a journal names is gone, so nothing is at it."""
    pid = doc.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def _claude_back(config, page, was, env=None):
    """Claude Code's copy of a page as it was: at the version the store's list now names, or not installed."""
    mine = "%s@%s" % (page, cfg.STORE)
    _claude(config, ["plugin", "marketplace", "update", cfg.STORE], env, timeout=120)
    if was:
        _claude(config, ["plugin", "update", mine, "--scope", "local"], env)
    else:
        _claude(config, ["plugin", "uninstall", mine, "--scope", "local"], env)


def recover(config, env=None, now=None, startup=False, claude=True):
    """What a killed add or update left, put back, at Home's server's start and each tick, so the Shop never sticks on
    "Adding…". Returns the pages put back. claude: False from the tick, which never starts Claude Code, so a journal
    waits for Home's server's next start or the next step in the chat, and only the marks and staging folders go.
    - A page's update (UPDATING, kept by hydralib/update.py with its backup): the backup restored, the version folder
      it made taken away, and Claude Code's copy at the version before.
    - Else an install (JOURNAL): the version folder as it was, the store's list, bought.json and keys.json as the
      journal kept them, and Claude Code's copy at the version before, or not installed.
    - An Adding mark with no one at it: at the server's start, since its add ran in the server; else once 10 minutes
      old. Staging folders (hydra/shop/.open-*, hydra/.update) 10 minutes old go too.
    Only a journal whose process is gone is touched."""
    root = config["root"]
    now = now or _now()
    out = []
    upd = files.read_json(_p(root, UPDATING), None) if claude else None
    if isinstance(upd, dict) and _gone(upd) and isinstance(upd.get("page"), str) and ID.fullmatch(upd["page"]):
        from . import backup
        if isinstance(upd.get("backup"), str) and os.path.isdir(upd["backup"]):
            backup.restore(root, upd["backup"])
        folder_ = os.path.join(root, "hydra", "store", upd["page"], str(upd.get("version") or ""))
        if upd.get("version") and not upd.get("there") and VERSION.fullmatch(str(upd["version"])):
            shutil.rmtree(folder_, ignore_errors=True)
        _claude_back(config, upd["page"], upd.get("was"), env)
        registry.build(config, env=env)
        _unjournal(root, UPDATING)
        _unjournal(root, JOURNAL)
        out.append(upd["page"])
    j = files.read_json(_p(root, JOURNAL), None) if claude else None
    if isinstance(j, dict) and _gone(j) and isinstance(j.get("page"), str) and ID.fullmatch(j["page"]) and \
            VERSION.fullmatch(str(j.get("version") or "")):
        store = os.path.join(root, "hydra", "store")
        target = os.path.join(store, j["page"], j["version"])
        if os.path.exists(target + ".before"):
            shutil.rmtree(target, ignore_errors=True)
            os.replace(target + ".before", target)
        elif not (isinstance(j.get("bought"), dict) and (j["bought"].get(j["page"]) or {}).get("version") == j["version"]):
            shutil.rmtree(target, ignore_errors=True)
        if not j.get("folder_was"):
            shutil.rmtree(os.path.join(store, j["page"]), ignore_errors=True)
        if isinstance(j.get("market"), dict):
            files.write_json(_marketplace(root), j["market"])
        if isinstance(j.get("bought"), dict):
            _write_bought(root, j["bought"])
        if isinstance(j.get("keys"), dict):
            _write_keys(root, j["keys"])
        _claude_back(config, j["page"], (j.get("bought") or {}).get(j["page"]), env)
        registry.build(config, env=env)
        _unjournal(root)
        out.append(j["page"])
    st = files.read_json(_p(root, "state.json"), {})
    left = not claude and any(os.path.exists(_p(root, n)) for n in (JOURNAL, UPDATING))  # its mark goes with it, later
    if isinstance(st, dict) and st.get("working") and not left:
        try:
            at = datetime.datetime.fromisoformat(str(st.get("at")))
        except ValueError:
            at = None
        if startup or at is None or not at.tzinfo or now - at > QUIET:
            mark(root, "", "")
    for base, prefix in ((folder(root), ".open-"), (os.path.join(root, "hydra"), ".update")):
        for n in os.listdir(base) if os.path.isdir(base) else []:
            path = os.path.join(base, n)
            try:
                old = now.timestamp() - os.stat(path).st_mtime > QUIET.total_seconds()
            except OSError:
                continue
            if n.startswith(prefix) and os.path.isdir(path) and old:
                shutil.rmtree(path, ignore_errors=True)
    return out


def prune_versions(root, page, version):
    """A page's store folder kept to KEEP versions: the one in use and the one before it."""
    folder_ = os.path.join(root, "hydra", "store", page)
    previous = (bought(root).get(page) or {}).get("previous", "")
    for old in sorted((v for v in os.listdir(folder_) if vt(v)), key=vt)[:-KEEP] if os.path.isdir(folder_) else []:
        if old not in (version, previous):
            shutil.rmtree(os.path.join(folder_, old), ignore_errors=True)


OFFER_WAIT = 120  # seconds for Goals' arrived call


def _offer(config, page, env=None):
    """Ask Goals for its one offer: Goals' own
    `scripts/act.py arrived --app=<page> --record <root>/goals`, which counts at once each goal already measured by the
    page, and asks once of each goal kept by hand that fits it, "{Page} can count '{goal}' now.". Best effort: the page
    is in either way, and Goals' next run catches up. Nothing when Goals isn't installed."""
    goals = registry.app(config["root"], "goals")
    act = os.path.join((goals or {}).get("root") or "", "scripts", "act.py")
    if page == "goals" or not goals or not os.path.isfile(act) or not os.path.isabs(config.get("python") or ""):
        return
    try:
        subprocess.run([config["python"], "-B", "-s", act, "arrived", "--app=" + page, "--record", goals["record"]],
                       cwd=config["root"], env=cfg.run_env(config), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=OFFER_WAIT)
    except (OSError, subprocess.SubprocessError):
        pass  # Goals' next run makes the offer


def _open(config, page, key, pack_file=None, want=None, env=None):
    """Fetch (or take), check and open one page's pack, staged in <root>/hydra/shop/; returns (version, staged folder)."""
    root = config["root"]
    work = tempfile.mkdtemp(prefix=".open-", dir=files.folder(folder(root)))
    try:
        sealed = os.path.join(work, "sealed")
        if pack_file:
            if not os.path.isfile(pack_file):
                raise Refused("That file isn't there.")
            if not want or not want.get("sha256") or not want.get("version"):
                raise Refused("Hydra-OS can't check that file until the shop lists it. Check the Mac is online, then "
                              "try again.")
            _fetch(pack_file, PACK_MOST, sealed)
            digest = want["sha256"]  # trusted only through the signed catalog, as every pack is
        else:
            if not want.get("pack") or not want.get("sha256") or not want.get("version"):
                raise Refused("%s isn't ready to add yet." % want.get("title", page))
            try:
                _fetch(want["pack"], PACK_MOST, sealed)
            except (OSError, ValueError):
                raise Refused("Hydra-OS couldn't reach the shop. Check the Mac is online, then try again.")
            digest = want["sha256"]
        if digest and _sha256(sealed) != digest:
            raise Refused("That file isn't the one the shop lists, so it wasn't taken.")
        try:  # room for it opened, staged and in the store
            from . import space
            space.need(root, 3 * os.path.getsize(sealed) + space.PAGE_MORE, env)
        except space.Short as e:
            raise Refused(str(e))
        tar = os.path.join(work, "page.tar.gz")
        _unseal(sealed, key, tar)
        staged = os.path.join(work, "staged")
        files.folder(staged)
        try:
            _extract(tar, staged)
        except (tarfile.TarError, OSError):
            raise Refused("That key doesn't open it. Check the key on your receipt.")
        inner = os.path.join(staged, page)
        plugin = _plugin(inner)
        version = str(plugin.get("version") or "")
        if plugin.get("name") != page or not VERSION.fullmatch(version):
            raise Refused("That pack isn't %s's, so it wasn't taken." % (want or {}).get("title", page))
        if want and want.get("version") and version != want["version"]:
            raise Refused("That pack isn't the version the shop lists, so it wasn't taken.")
        return version, inner, work
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def _listed(root, page, env=None):
    want = next((p for p in catalog(root, env)["pages"] if p["id"] == page), None)
    if not want:
        raise Refused("That page isn't in the shop.")
    need = want.get("min_hydra")
    if need and vt(hydra_version(root)) < vt(need):
        raise Refused("%s needs a newer Hydra-OS. Update Hydra-OS first." % want["title"])
    return want


def add(config, key, pack_file=None, env=None):
    """A page by its key (`hydra add --key`, Home's Shop page), or from a pack file with its key (`hydra add <file>`,
    for tests and offline use). Returns the line to say."""
    root = config["root"]
    page, key = parse_key(key)
    want = _listed(root, page, env)
    have = bought(root).get(page)
    if not pack_file and registry.app(root, page) and (not have or have["version"] == want.get("version")):
        _keys_keep(root, page, key)  # bought at this version, or installed with the rest: never put in again
        return "%s is in your rail already." % want["title"]
    if (not want.get("sha256") or not (pack_file or want.get("pack"))) and source(config, env):
        # nothing to fetch yet: the shop is read again now, rather than at the next daily read
        read = read_catalog(config, force=True, env=env)
        if read == "offline":
            raise Refused("Hydra-OS couldn't reach the shop. Check the Mac is online, then try again.")
        if read == "refused":
            raise Refused("Hydra-OS couldn't check the shop's list, so nothing was added. Try again later.")
        want = _listed(root, page, env)
    version, inner, work = _open(config, page, key, pack_file, want, env)
    try:
        _install(config, page, version, inner, key, env)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return "%s is in your rail." % want["title"]  # its Set up, on its tile and its page, hands Claude the rest


def _keys_keep(root, page, key):
    keys = _keys(root)
    if keys.get(page) != key:
        keys[page] = key
        _write_keys(root, keys)


def update(config, page=None, env=None):
    """Each bought page the catalog has newer, with its kept key, one version kept back. Returns the lines to say."""
    root = config["root"]
    out = []
    for p, have in sorted(bought(root).items()):
        if page and p != page:
            continue
        want = next((x for x in catalog(root, env)["pages"] if x["id"] == p), None)
        if not want or not vt(want.get("version")) or vt(want["version"]) <= vt(have["version"]):
            out.append("%s is up to date." % (want or {}).get("title", p))
            continue
        key = _keys(root).get(p)
        if not key:
            raise Refused("%s's key isn't kept here. Paste it in the Shop, or give it with hydra add --key." % want["title"])
        _listed(root, p, env)
        version, inner, work = _open(config, p, key, None, want, env)
        try:  # with the backup, the page's own migrate and the rollback
            from . import update as updating
            updating.page(config, p, version, inner, want["title"], env)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        out.append("%s %s is in your rail." % (want["title"], version))
    if page and not out:
        raise Refused("That page isn't one you've added.")
    return out or ["Nothing to update."]


def remove(config, page, env=None):
    """A bought page out of Claude Code and the store, with its key; its own records stay in the Hydra-OS folder."""
    root = config["root"]
    pages_now = bought(root)
    if page not in pages_now:
        raise Refused("That page isn't one you've added.")
    title = (registry.app(root, page) or {}).get("title") or page
    _claude(config, ["plugin", "uninstall", "%s@%s" % (page, cfg.STORE), "--scope", "local"], env)
    market_path = _marketplace(root)
    doc = files.read_json(market_path, {})
    if isinstance(doc, dict) and isinstance(doc.get("plugins"), list):
        doc["plugins"] = [e for e in doc["plugins"] if not (isinstance(e, dict) and e.get("name") == page)]
        files.write_json(market_path, doc)
    shutil.rmtree(os.path.join(root, "hydra", "store", page), ignore_errors=True)
    pages_now.pop(page)
    _write_bought(root, pages_now)
    keys = _keys(root)
    keys.pop(page, None)
    _write_keys(root, keys)
    registry.build(config, env=env)
    return "%s is out of your rail. Its own records stay in your Hydra-OS folder." % title


# ---- where each page stands ----------------------------------------------------------------------------------------

def state(root):
    """Each catalog page and where it stands, for Home's Shop page (GET /api/shop) and `hydra shop`:
    {"pages": [{"id", "title", "version", "have", "state", "checkout", "price"}], "working": <the page being added or updated,
    or "">, "said": <the last add's or update's line>, and "repair": true when Repair goes beside that line}. A state is
    one of: "available", "not-ready" (no pack yet),
    "needs-hydra" (Update Hydra-OS first), "in-rail", "update" (a newer version is ready), "adding"."""
    have = bought(root)
    installed = {a["id"]: a for a in registry.read(root).get("apps", []) if a.get("kind") != "main" and a.get("id")}
    now_doc = files.read_json(_p(root, "state.json"), {})
    working = now_doc.get("working") if isinstance(now_doc, dict) and isinstance(now_doc.get("working"), str) else ""
    mine = hydra_version(root)
    out = []
    for p in catalog(root)["pages"]:
        h = have.get(p["id"], {}).get("version", "")
        if working == p["id"]:
            st = "adding"
        elif h and vt(p.get("version")) > vt(h):
            st = "update"
        elif h or p["id"] in installed:  # bought, or installed with the rest, never offered again
            st = "in-rail"
            h = h or str(installed.get(p["id"], {}).get("version") or "")
        elif p.get("min_hydra") and vt(mine) < vt(p["min_hydra"]):
            st = "needs-hydra"
        elif not p.get("pack") or not p.get("sha256"):
            st = "not-ready"
        else:
            st = "available"
        out.append({"id": p["id"], "title": p["title"], "version": p.get("version", ""), "have": h, "state": st,
                    "checkout": p.get("checkout", ""), "price": p.get("price", "")})
    said = now_doc.get("said") if isinstance(now_doc, dict) and isinstance(now_doc.get("said"), str) else ""
    doc = {"pages": out, "working": working, "said": said}
    if said and now_doc.get("repair") is True:  # the Shop draws Repair beside that line
        doc["repair"] = True
    return doc


def checkout(root, page, env=None):
    """"Get <Page>": the catalog in force's checkout address for that page, https only and never from the
    request, opened in the person's own browser with /usr/bin/open, so card details never sit in a pane Claude reads.
    HYDRA_TEST_OPENED records it for a test instead. Returns the line to say."""
    env = os.environ if env is None else env
    want = next((p for p in catalog(root, env)["pages"] if p["id"] == page), None)
    if not want:
        raise Refused("That page isn't in the shop.")
    url = want.get("checkout") or ""
    if not url.startswith("https://"):
        raise Refused("%s isn't on sale yet." % want["title"])
    if env.get("HYDRA_TEST_OPENED"):
        with open(env["HYDRA_TEST_OPENED"], "a") as f:
            f.write(url + "\n")
    else:
        subprocess.run(["/usr/bin/open", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)
    return "The checkout opens in your browser."


def mark(root, working="", said="", repair=False):
    """Home's server's note of an add or update under way, and of how the last one went: with `repair`, its line is
    one the Shop draws Repair beside."""
    doc = {"working": working, "said": said, "at": _iso(_now())}
    if repair:
        doc["repair"] = True
    files.write_json(_p(root, "state.json"), doc)
