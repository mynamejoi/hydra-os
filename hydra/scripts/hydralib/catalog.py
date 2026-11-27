"""The Shop, as an explainer: Home's
catalog, the main plugin's home/catalog.json, catalog/v1, which Home's build draws as the Shop page (/shop/). Network
reads it for the `about` request ("Ask Claude about it" on a card) and for Claude's line about it. Nothing is sold:
each card says what the page does, what it reads and what it needs.

  read(root)            [{"id", "title", "does", "reads", "needs", "installed"}, ...], or [] with no catalog
  title(root, page_id)  that page's title, or ""
"""
import os

from . import files, registry

TEXT_MOST = 160


def path(root):
    main = registry.app(root, registry.MAIN) or {}
    folder = os.environ.get("HYDRA_TEST_CATALOG_ROOT") or main.get("root") or ""  # a test's own copy, never the repo's
    return os.path.join(folder, "home", "catalog.json") if folder else ""


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= TEXT_MOST and "\n" not in value


def read(root):
    doc = files.read_json(path(root), None) if path(root) else None
    if not isinstance(doc, dict) or doc.get("contract") != "catalog/v1" or not isinstance(doc.get("pages"), list):
        return []
    installed = {a.get("id") for a in registry.read(root).get("apps", []) if a.get("kind") != "main"}
    return [{"id": p["id"], "title": p["title"], "does": p["does"], "reads": p["reads"], "needs": p["needs"],
             "installed": p["id"] in installed}
            for p in doc["pages"]
            if isinstance(p, dict) and all(_text(p.get(k)) for k in ("id", "title", "does", "reads", "needs"))]


def title(root, page_id):
    return next((p["title"] for p in read(root) if p["id"] == page_id), "")
