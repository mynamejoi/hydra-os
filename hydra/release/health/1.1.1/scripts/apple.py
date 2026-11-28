"""Apple Health's own export, read for Health: the export.zip
the Health app makes on an iPhone (your picture, then Export All Health Data), or the export.xml inside it.

It's read streamed, one element at a time and each cleared after use, so an export of gigabytes reads in little
memory. It reads only three kinds and turns them into the shape's rows (days.py):
  sleep           HKCategoryTypeIdentifierSleepAnalysis, its asleep stages, with overlaps between sources merged:
                  the night is the longest stretch of sleep with no break of over two hours, from lights out to waking.
                  A night with no asleep stage, as an iPhone with no watch records it, keeps its time in bed instead,
                  as bed_hours, with its own lights out and waking
  resting heart rate   HKQuantityTypeIdentifierRestingHeartRate
  workouts        Workout, its kind, its times and its minutes
Everything else is passed over unread, heart rate variability included. It never opens the zip's workout-routes/,
clinical-records/ or
electrocardiograms/ folders or export_cda.xml, and never keeps a route, a location or a clinical record. Every time is
shown in this Mac's own zone. Written in code, with no model. Nothing here prints a value.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib

import days as D

SOURCE = "upload"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
RHR = "HKQuantityTypeIdentifierRestingHeartRate"
HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"   # heart rate variability: passed over, never read
IN_BED = "HKCategoryValueSleepAnalysisInBed"
ASLEEP = {"HKCategoryValueSleepAnalysisAsleep", "HKCategoryValueSleepAnalysisAsleepUnspecified",
          "HKCategoryValueSleepAnalysisAsleepCore", "HKCategoryValueSleepAnalysisAsleepDeep",
          "HKCategoryValueSleepAnalysisAsleepREM"}
SPORTS = {"Swimming": "swim", "Running": "run", "Cycling": "ride", "Walking": "walk", "Hiking": "walk",
          "TraditionalStrengthTraining": "lift", "FunctionalStrengthTraining": "lift", "Yoga": "yoga", "Pilates": "yoga",
          "Rowing": "row"}
DAYTIME = (10, 18)   # a sleep that starts between these hours is a nap, not a night
BREAK = dt.timedelta(hours=2)   # a longer time awake ends one stretch of sleep; the night is the longest stretch
_WHEN = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d) ([+-]\d\d)(\d\d)$")


class NotAnExport(Exception):
    """The file isn't an Apple Health export Health can read."""


def when(text):
    """Apple's "2025-06-15 22:10:00 -0400" in this Mac's own zone, or None."""
    m = _WHEN.match(str(text or "").strip())
    if not m:
        return None
    try:
        return dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{m.group(3)}:{m.group(4)}").astimezone()
    except ValueError:
        return None


def member(zf: zipfile.ZipFile) -> str:
    """The name of the export.xml inside an export.zip, and never any other file in it."""
    names = [n for n in zf.namelist() if n.lower().rsplit("/", 1)[-1] == "export.xml"]
    if not names:
        raise NotAnExport("there's no export.xml in it")
    return min(names, key=len)


def _elements(stream):
    """(tag, attributes) for each Record and Workout, streamed. Once each of HealthData's own children is whole, it and
    everything before it is dropped, so memory stays flat however long the export."""
    depth, root = 0, None
    for event, el in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
            depth += 1
            if root is None:
                root = el
            continue
        depth -= 1
        if depth == 1:   # a child of HealthData, now whole; a Record's own children end deeper
            if el.tag in ("Record", "Workout", "ExportDate"):
                yield el.tag, dict(el.attrib)
            root.clear()


def _sport(kind: str) -> str:
    name = re.sub(r"^HKWorkoutActivityType", "", str(kind or ""))
    if name in SPORTS:
        return SPORTS[name]
    return D.kind_of(re.sub(r"(?<!^)(?=[A-Z])", " ", name)) if name else ""


def _night(spans: list) -> list:
    """The night's asleep spans: overlaps between sources counted once, then the longest stretch with no break over
    BREAK, so an evening doze or a few minutes asleep before getting up isn't its lights out or its waking."""
    spans = sorted(spans)
    merged = [list(spans[0])]
    for s, e in spans[1:]:   # two sources often record the same night: count each minute once
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    stretches = [[merged[0]]]
    for span in merged[1:]:
        if span[0] - stretches[-1][-1][1] > BREAK:
            stretches.append([span])
        else:
            stretches[-1].append(span)
    return max(stretches, key=lambda st: sum((e - s).total_seconds() for s, e in st))


def read_stream(stream, info=None) -> list:
    """The shape's rows, oldest first, from export.xml's bytes. info, a dict, gets "made": the day Apple made the
    export (its ExportDate), the snapshot's own end."""
    made = None
    asleep, bed, rhr, sports, minutes = {}, {}, {}, {}, {}
    try:
        for tag, a in _elements(stream):
            if tag == "ExportDate":
                made = when(a.get("value"))
                continue
            start, end = when(a.get("startDate")), when(a.get("endDate"))
            if start is None:
                continue
            if tag == "Workout":
                kind = _sport(a.get("workoutActivityType"))
                if kind:
                    sports.setdefault(start.date().isoformat(), []).append(kind)
                    if end is not None and end > start:
                        day = start.date().isoformat()
                        minutes[day] = minutes.get(day, 0) + (end - start).total_seconds() / 60
                continue
            kind = a.get("type")
            if kind == SLEEP and (a.get("value") in ASLEEP or a.get("value") == IN_BED) and end is not None and end > start:
                if DAYTIME[0] <= start.hour < DAYTIME[1]:
                    continue   # a nap
                night = (start + dt.timedelta(hours=12)).date().isoformat()   # the morning it ends in
                (asleep if a.get("value") in ASLEEP else bed).setdefault(night, []).append((start, end))
            elif kind == RHR:
                try:
                    v = float(a.get("value"))
                except (TypeError, ValueError):
                    continue
                rhr.setdefault(start.date().isoformat(), []).append(v)
    except ET.ParseError:
        raise NotAnExport("it isn't whole XML") from None
    out = {}
    for day, spans in asleep.items():
        night = _night(spans)
        hours = sum((e - s).total_seconds() for s, e in night) / 3600
        out[day] = {"day": day, "sleep_hours": round(hours, 2), "lights_out": night[0][0].strftime("%H:%M"),
                    "woke": night[-1][1].strftime("%H:%M")}
    for day, spans in bed.items():   # time in bed, only for a night with no asleep stage
        if day in out:
            continue
        night = _night(spans)
        hours = sum((e - s).total_seconds() for s, e in night) / 3600
        out[day] = {"day": day, "bed_hours": round(hours, 2), "lights_out": night[0][0].strftime("%H:%M"),
                    "woke": night[-1][1].strftime("%H:%M")}
    for day, vs in rhr.items():
        out.setdefault(day, {"day": day})["resting_heart"] = vs[-1]
    for day, m in minutes.items():
        out.setdefault(day, {"day": day})["workout_minutes"] = round(m)
    for day, ks in sports.items():
        out.setdefault(day, {"day": day})["sports"] = ", ".join(ks)
    rows = [D.clean(out[d], SOURCE) for d in sorted(out)]
    if info is not None and made is not None:
        info["made"] = made.date().isoformat()
    return [r for r in rows if r]


def read(path, info=None) -> list:
    """The shape's rows from an export.zip or an export.xml on disk, and in info the day it was made. Raises NotAnExport."""
    path = str(path)
    if path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                with zf.open(member(zf)) as f:   # only export.xml is ever opened
                    return read_stream(f, info)
        except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError):
            raise NotAnExport("it isn't a whole zip Health can open") from None   # cut short, locked or packed otherwise
    with open(path, "rb") as f:
        return read_stream(f, info)
