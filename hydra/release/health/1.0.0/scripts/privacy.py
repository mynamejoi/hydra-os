"""Health's privacy checks.

1. States and counts only: what may never appear in STATUS.md, doctor.json or a
   signal. Each app carries its own copy of the patterns, since apps share no code.
2. The person's private terms (<record>/private.txt, one per line, kept by them): a business, a client,
   a project's name. They never go into a search, a prompt or the library.
3. What a search, a question or a public draft may never carry: an email, money, a phone number, a long digit run,
   a key, or one of the private terms.

    python3 scripts/privacy.py check-status [--record DIR]      # exit 1 and one line per finding
    python3 scripts/privacy.py check-query "words to search"     # exit 1 when it may not be searched
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import common

CURRENCY_SIGNS = "$€£¥₹₩₿"
CODES = r"USD|EUR|GBP|CAD|AUD|JPY|CHF|BTC|ETH|dollars?|cents?|bucks?"
PATTERNS = [
    ("money", re.compile(rf"[{re.escape(CURRENCY_SIGNS)}]\s?\d|\d[\d,.]*\s?(?:{CODES})\b", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("phone", re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]\d{3}[\s.-]\d{4}\b|\+\d{10,15}\b")),
    ("key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}|\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}|\bgh[pousr]_[A-Za-z0-9]{36}\b"
                       r"|\bgithub_pat_[A-Za-z0-9_]{50,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{35}\b"
                       r"|\bxox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                       r"|\bBearer\s+[A-Za-z0-9._~+/-]{8,}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
                       r"|\b(?:key|token|secret|password)\s*[:=]\s*\S{8,}", re.I)),
    ("home folder", re.compile(r"/Users/[^/\s]+/")),
]
DIGITS = re.compile(r"\d(?:[ -]?\d){12,18}")
LONG_RUN = re.compile(r"\d{9,}")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def kinds(line: str) -> list[str]:
    """Every kind from the status contract's table that this line carries."""
    found = [k for k, rx in PATTERNS if rx.search(line)]
    if LONG_RUN.search(line):
        found.append("card or account")
    else:
        for m in DIGITS.finditer(line):
            d = re.sub(r"\D", "", m.group())
            if 13 <= len(d) <= 19 and _luhn(d):
                found.append("card or account")
                break
    return list(dict.fromkeys(found))


def private_terms(record: pathlib.Path, settings: dict | None = None) -> list[str]:
    s = settings or common.settings(record)
    p = common.expand(s.get("private_terms", "private.txt"), record)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def _has_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text, re.I) is not None


def check_text(text: str, terms: list[str] = ()) -> list[str]:
    """Findings as '<line number>: <kind>', never echoing the matched text."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        ks = kinds(line)
        if any(_has_term(line, t) for t in terms):
            ks.append("a private term")
        out += [f"{n}: {k}" for k in dict.fromkeys(ks)]
    return out


def check_query(text: str, terms: list[str] = ()) -> list[str]:
    """Why a search or a mission question may not go out, or [] when it may."""
    why = [k for k in kinds(text)]
    if any(_has_term(text, t) for t in terms):
        why.append("a private term")
    return list(dict.fromkeys(why))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Health's privacy checks.")
    ap.add_argument("what", choices=["check-status", "check-query"])
    ap.add_argument("text", nargs="?")
    ap.add_argument("--record")
    a = ap.parse_args(argv)
    record = common.record_dir(a.record)
    terms = private_terms(record)
    if a.what == "check-status":
        try:
            text = (record / "STATUS.md").read_text(encoding="utf-8")
        except OSError:
            print("STATUS.md is missing", file=sys.stderr)
            return 1
        found = check_text(text, terms)
    else:
        found = check_query(a.text or "", terms)
    for f in found:
        print(f)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
