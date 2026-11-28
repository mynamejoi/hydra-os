"""Research's privacy check, for anything it writes outside the page: STATUS.md, the run's line, home.json, say.json
and the shared file. What it writes there holds states and counts only, so the check finds, line by line:

- an amount of money: a currency sign next to a number, or a number next to a currency code or word;
- an email address, a phone number, or a card or account number (13 to 19 digits that pass the Luhn check, or any run
  of 9 or more digits);
- a key or a token: the shapes of Anthropic, OpenAI-style, GitHub, AWS, Google and Slack keys, a private key block, a
  Bearer token, a JWT, or a key, token, secret or password given a value;
- a home folder's path;
- any of the person's own words Research holds: their name and city, each project's name and each note's title.

It says which kinds it found, never the text itself. Standard library only, Python 3.9 or newer.
"""
from __future__ import annotations

import re

import common
import search
import store

CODES = r"USD|EUR|GBP|CAD|AUD|JPY|CHF|BTC|ETH"
CURRENCY_WORDS = r"dollars?|cents?|bucks"
KINDS = [
    ("an amount of money", re.compile(r"[$€£¥₹₩₿]\s?\d")),
    ("an amount of money", re.compile(rf"\d[\d,.]*\s?(?:{CODES}|{CURRENCY_WORDS})\b", re.I)),
    ("an amount of money", re.compile(rf"\b(?:{CODES})\s?\d", re.I)),
    ("an email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("a phone number", re.compile(r"(?<![\d.])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\d.])")),
    ("a phone number", re.compile(r"(?<!\w)\+\d{10,15}(?!\d)")),
    ("a card or account number", re.compile(r"(?<!\d)\d{9,}(?!\d)")),
    ("a key or a token", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("a key or a token", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("a key or a token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}")),
    ("a key or a token", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a key or a token", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("a key or a token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a key or a token", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a key or a token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*")),
    ("a key or a token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("a key or a token", re.compile(r"\b(?:api[_-]?key|key|token|secret|password|passwd)\b\s*[:=]\s*[\"']?[^\s\"']{8,}", re.I)),
    ("a key or a token", re.compile(r"[A-Za-z0-9_\-]{32,}")),
    ("a home folder", re.compile(r"/Users/[^/\s]+|/home/[^/\s]+")),
]
GROUPED_DIGITS = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")


def luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def markers(rec, root=None) -> list:
    """The person's own phrases Research can see, lowercased: name and city words, project names and note titles."""
    root = root or common.root_of(rec)
    strong, _ = search.own_words(root, rec)
    out = sorted(strong)
    out += [" ".join(search.words_of(p.get("name", ""))) for p in store.all_projects(rec, root)]
    out += [" ".join(search.words_of(n.get("title", ""))) for n in store.notes(rec)]
    return [m for m in dict.fromkeys(out) if m]


def check_text(text: str, terms: list) -> list:
    """What in a text isn't states and counts: each kind found once, never the text itself."""
    found = []
    for line in text.splitlines() or [""]:
        for kind, rx in KINDS:
            if rx.search(line):
                found.append(kind)
        for m in GROUPED_DIGITS.finditer(line):
            digits = re.sub(r"\D", "", m.group())
            if 13 <= len(digits) <= 19 and luhn(digits):
                found.append("a card or account number")
    joined = " " + " ".join(search.words_of(text)) + " "
    if any(f" {t} " in joined for t in terms):
        found.append("one of the person's own words")
    return list(dict.fromkeys(found))
