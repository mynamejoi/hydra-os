#!/usr/bin/env python3
"""The main plugin's one UserPromptSubmit hook, on each message, in this order:

1. The secret guard. A message holding what looks like a password or a key is blocked: it never reaches Claude, the
   person is told why and where it goes instead, and nothing else happens, no focus and no log.
2. The focus hook (hydralib/context.py): one block of page context, given as data, and one `asked` log line; then,
   after the data, what to do with each tap still open there (context.taps).

It runs before anything is imported from the plugin's library, so the guard stands even when the rest can't load.
The message's words are never written anywhere. Python 3.9 standard library only, run as python3 -I.
"""
import json
import os
import re
import sys

BLOCKED = ("That message looks like it holds a password or a key, so it wasn't sent to Claude. Sign in on the "
           "service's own page instead. If it was a real password, consider changing it.")
VALUE = r'(?=\S*(?:\d|_|[^\w\s](?=\S)))\S{6,}'  # one word holding a digit, or a symbol inside it, so "stored" or "saved," never counts
PATTERNS = [
    r'\b(?:password|passcode|passwd|pwd|pin)\b\s*(?:is|was|=|:)\s*' + VALUE,
    r'\b(?:client[ _-]?secret|api[ _-]?key|access[ _-]?token|secret[ _-]?key|token)\b\s*(?:is|=|:)\s*' + VALUE,
    r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}',
    r'\bgithub_pat_[A-Za-z0-9_]{20,}',
    r'\bsk-[A-Za-z0-9_\-]{20,}',
    r'\bxox[abpr]-[A-Za-z0-9\-]{10,}',
    r'\bAKIA[0-9A-Z]{16}\b',
]


def secret(text):
    return any(re.search(p, text, re.I) for p in PATTERNS)


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(event, dict):
        return 0
    text = event.get("prompt")
    if isinstance(text, str) and secret(text):
        print(json.dumps({"decision": "block", "reason": BLOCKED}))
        return 0
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from hydralib import context
        root = context.root_for(event.get("cwd") if isinstance(event.get("cwd"), str) else None)
        review = bool(root) and context.review_session(text)
        block = "" if review or not root else context.focus(root)
    except Exception:  # a broken panel file never stops a message
        return 0
    if review:  # the morning review's own session, with nobody there: one line, and nothing of theirs changed
        block = context.REVIEW_ONLY
    else:
        try:  # the first session's current step, as guidance before the data
            step = context.step_now(root, session=str(event.get("session_id") or "")) if root else ""
        except Exception:
            step = ""
        try:  # what ran or changed since their last message
            news = context.since(root) if root else ""
        except Exception:
            news = ""
        try:  # what to do with each open tap, as guidance after the data
            taps = context.taps(root) if root and block else ""
        except Exception:
            taps = ""
        block = "\n".join(t for t in (step, news, block, taps) if t)
    if block:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": block}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
