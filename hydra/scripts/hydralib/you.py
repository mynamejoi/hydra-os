"""The name Home's greeting shows: <root>/hydra/home/you.json {"name"}, one of Home's own files,
which Home's page.py reads and `hydra name set` writes once the person has told Claude their name. Their answer to
Claude's question is their yes for that one save.

  path(root)          <root>/hydra/home/you.json
  name(root)          the name kept, or ""
  clean(text)         the name as it's kept, or None when it isn't one
  save(root, name)    keeps it, with every other key of you.json as it was

And their city, asked once, last and optional,
so the sky follows their real sun and Home's date line shows sunset. Claude gives its latitude and longitude from what it
knows, so no lookup service is called, and their answer is their yes for that one save:
  place(root)         {"city", "lat", "lon"} once set; None once they passed (place is null); {} when not asked yet
  clean_city(text)    the city as it's kept, or None when it isn't one
  check_place(lat, lon, offset)   (lat, lon) to one decimal, or ValueError with why, offset being the Mac's in seconds
  save_place(root, city, lat, lon) / clear_place(root)

And the first session's steps they skipped in the chat, so each is never asked again (`hydra first skip <step>`):
  skipped(root) / skip(root, step)     "name", "goal" or "connect", in you.json's "skipped"
"""
import os
import unicodedata

from . import files

MOST = 60
BETWEEN = " -'’."  # what may stand between a name's letters: spaces, hyphens, apostrophes and periods


def path(root):
    return os.path.join(root, "hydra", "home", "you.json")


def name(root):
    doc = files.read_json(path(root), {})
    value = doc.get("name") if isinstance(doc, dict) else None
    return value.strip() if isinstance(value, str) else ""


def clean(text):
    """Letters in any script, with spaces, hyphens, apostrophes and periods between, on one line, at most 60 characters,
    its spaces made single: so never a figure, a key, markup or a second line."""
    text = str(text)
    if any(unicodedata.category(c) == "Cc" for c in text):
        return None
    text = unicodedata.normalize("NFC", " ".join(text.split()))
    if not 1 <= len(text) <= MOST or unicodedata.category(text[0])[0] != "L":
        return None
    if not all(unicodedata.category(c)[0] in "LM" or c in BETWEEN for c in text):
        return None
    return text


def save(root, value):
    doc = files.read_json(path(root), {})
    doc = dict(doc) if isinstance(doc, dict) else {}
    doc["name"] = value
    files.write_json(path(root), doc)


CITY_MOST = 60
CITY_BETWEEN = " -'\u2019.,"  # and commas and periods, as "St. John's, Newfoundland" has
ZONE_HOURS = 3  # a longitude further than this from the Mac's own time zone is refused


def place(root):
    doc = files.read_json(path(root), {})
    if not isinstance(doc, dict) or "place" not in doc:
        return {}
    value = doc["place"]
    if isinstance(value, dict) and isinstance(value.get("city"), str):
        return {"city": value["city"], "lat": value.get("lat"), "lon": value.get("lon")}
    return None


def clean_city(text):
    """Letters in any script, with spaces, hyphens, apostrophes, periods and commas between, on one line, at most 60
    characters, its spaces made single."""
    text = str(text)
    if any(unicodedata.category(c) == "Cc" for c in text):
        return None
    text = unicodedata.normalize("NFC", " ".join(text.split()))
    if not 1 <= len(text) <= CITY_MOST or unicodedata.category(text[0])[0] != "L":
        return None
    if not all(unicodedata.category(c)[0] in "LM" or c in CITY_BETWEEN for c in text):
        return None
    return text


def check_place(lat, lon, offset):
    """Latitude -90 to 90 and longitude -180 to 180, kept to one decimal. A longitude more than three hours from the
    Mac's own time zone (15 degrees an hour, around the globe either way) is refused, so a city Claude placed wrongly
    never moves the sky by half a day."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError("The latitude and longitude are numbers, such as --lat=40.7 --lon=-74.0.")
    if lat != lat or lon != lon or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("The latitude runs from -90 to 90, and the longitude from -180 to 180.")
    off = abs((lon - offset / 240.0 + 180) % 360 - 180)  # degrees from the Mac's zone, offset/3600 hours at 15 an hour
    if off > ZONE_HOURS * 15:
        raise ValueError("That's more than three hours from this Mac's time zone, so it wasn't kept.")
    return round(lat, 1) + 0.0, round(lon, 1) + 0.0


def save_place(root, city, lat, lon):
    doc = files.read_json(path(root), {})
    doc = dict(doc) if isinstance(doc, dict) else {}
    doc["place"] = {"city": city, "lat": lat, "lon": lon}
    files.write_json(path(root), doc)


def clear_place(root):
    """No place, kept as asked: the city is never asked again."""
    doc = files.read_json(path(root), {})
    doc = dict(doc) if isinstance(doc, dict) else {}
    doc["place"] = None
    files.write_json(path(root), doc)


SKIPS = ("name", "goal", "connect")


def skipped(root):
    doc = files.read_json(path(root), {})
    value = doc.get("skipped") if isinstance(doc, dict) else None
    return {v for v in value if v in SKIPS} if isinstance(value, list) else set()


def skip(root, step):
    doc = files.read_json(path(root), {})
    doc = dict(doc) if isinstance(doc, dict) else {}
    doc["skipped"] = sorted(skipped(root) | {step})
    files.write_json(path(root), doc)


def city_asked(root):
    """The session that asked their city, or "" before it's asked (asked once, across sessions)."""
    doc = files.read_json(path(root), {})
    value = doc.get("city_asked") if isinstance(doc, dict) else None
    return value if isinstance(value, str) else ""


def mark_city_asked(root, session):
    doc = files.read_json(path(root), {})
    doc = dict(doc) if isinstance(doc, dict) else {}
    doc["city_asked"] = session or "-"
    files.write_json(path(root), doc)
