"""The words lock: every line Health puts in front of a person passes here first, whether code or a model
wrote it. A line that fails is dropped, never reworded.

The lock: Health may suggest, about sleep, training load, recovery and meals, with its reason from the person's own
figures. It never names a diagnosis, a medicine, a supplement or a dose, and anything that looks like a health problem
reads "worth asking a doctor". Two more limits stand: no diet plan and no calorie target.

    care(text)        the lock: True when a line names any of those
    internal(text)    True when a line uses one of the build's own words, which nobody outside it knows
    problems(text, most)   every reason a line can't be shown: the two above, and it's one plain line within its length
    numbers_ok(text, allowed)   every number in a line is one Health worked out

Checks holds the same lock on say.json with its own checker (checks/say.py); this one runs before anything is written,
and is at least as strict. Changing these lists is changing Health's lock: it goes through Checks.

Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import re

# the lock: a diagnosis, a medicine, a supplement or a dose, by the words that name one
CARE = re.compile(
    r"\b(diagnos\w*|medicat\w*|medicine\w*|supplement\w*|dose\w*|dosage|dosing|prescri\w*|pills?|tablets?|capsules?|"
    r"vitamins?|multivitamins?|melatonin|magnesium|creatine|ashwagandha|probiotics?|electrolyte (tablets?|powders?)|"
    r"ibuprofen|aspirin|paracetamol|acetaminophen|antihistamines?|antibiotics?|antidepressants?|statins?|insulin|"
    r"beta.?blockers?|sedatives?|sleeping (pills?|aids?))\b"
    r"|\b\d+(\.\d+)?\s?(mg|mcg|µg|iu|ml)\b", re.I)
# a diagnosis by its name: Health never says what someone has
CONDITION = re.compile(
    r"\b(apn(o)?ea|insomnia|arrhythmia|tachycardia|bradycardia|fibrillation|hypertension|hypotension|diabet\w*|"
    r"an(a)?emia|depress(ion|ed)|anxiety disorder|infection|infected|virus|viral|flu|covid|overtraining syndrome|"
    r"burnout syndrome|thyroid|disorder|disease|syndrome|condition you have|you (may|might|could|probably) have)\b", re.I)
# observations only: no diet plan and no calorie target
DIET = re.compile(r"\b(diet plan|meal plan|calorie (target|goal|budget|deficit|limit)|\d[\d,]*\s?(k?cal|calories)|"
                  r"(cut|count|track)(ting|ing)? (your )?(calories|carbs|macros)|fasting (plan|window))\b", re.I)
# the build's own words, which a person who was only handed the product has never seen
BUILD_WORDS = ("seat", "tick", "fence", "record", "root", "lane", "contract", "blueprint")
INTERNAL = re.compile(r"\b(%s)\w*" % "|".join(BUILD_WORDS), re.I)
MARKUP = re.compile(r"<[A-Za-z!/?]|&#?[A-Za-z0-9]+;")
DASH = re.compile("[–—]")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
PRIVATE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|https?://|www\.|/Users/|~/|\b(sk|pk|ghp|xox[abp])[-_][A-Za-z0-9_-]{8,}"
                     r"|\b[A-Za-z0-9_\-]{32,}\b|\+?\d[\d ()-]{8,}\d")
NUMBER = re.compile(r"\d+(?:[.:]\d+)?")
# a day said as a date ("June 11", "Jun 11 and 12", "the 13th") is a day, not a figure
DATE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:(?:,|\s+and|\s+to|\s+or)\s+\d{1,2})*\b"
                  r"|\b\d{1,2}(st|nd|rd|th)\b", re.I)
ALWAYS = {"7", "14", "30"}   # the page's own spans: 7 days to a usual, 14 days shown, 30 days behind a usual
LIMITS = {"headline": 90, "text": 120, "why": 140, "moved": 40, "label": 40, "line": 60, "word": 20, "counting": 60}


def care(text: str) -> bool:
    return bool(CARE.search(text) or CONDITION.search(text) or DIET.search(text))


def internal(text: str) -> bool:
    return bool(INTERNAL.search(text))


def problems(text, most: int) -> list:
    """Why a line can't be shown, in words; [] when it can."""
    if not isinstance(text, str) or not text:
        return ["it isn't a line of text"]
    p = []
    if text.strip() != text or "\n" in text or "\r" in text or "\t" in text:
        p.append("it isn't one plain line")
    if len(text) > most:
        p.append(f"it's over {most} characters")
    if MARKUP.search(text) or DASH.search(text) or EMOJI.search(text):
        p.append("it holds markup, a long dash or an emoji")
    if care(text):
        p.append("it names a diagnosis, a medicine, a supplement, a dose or a diet plan")
    if internal(text):
        p.append("it uses one of the build's own words")
    if PRIVATE.search(text):
        p.append("it holds an address, a link, a path, a key or a phone number")
    return p


def ok(text, most: int) -> bool:
    return not problems(text, most)


def numbers(text: str) -> set:
    return set(NUMBER.findall(text or ""))


def numbers_ok(text: str, allowed: set) -> bool:
    """Every figure in a line is one Health worked out, or one of the page's own spans. A date isn't a figure."""
    return numbers(DATE.sub(" ", text or "")) <= (allowed | ALWAYS)
