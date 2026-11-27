#!/usr/bin/env python3
"""The main plugin's SessionStart hook, the primer: one block of at most 4,000 characters of facts about this Mac's
Hydra-OS, between marker lines, given to Claude as data (hydralib/context.py). A session outside a
Hydra-OS root (no HYDRA_ROOT, and no hydra/config.json above its folder) gets nothing. Python 3.9 standard library
only, run as python3 -I."""
import json
import os
import sys


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        event = {}
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from hydralib import context
        cwd = event.get("cwd") if isinstance(event, dict) and isinstance(event.get("cwd"), str) else None
        root = context.root_for(cwd)
        text = context.primer(root) if root else ""
    except Exception:
        return 0
    if root:
        try:  # Claude's Bash commands get Hydra-OS's own tools and this chat's Claude Code; with the helpers off,
            # Home's server and the day's reads start with the chat (hydralib/session.py)
            import datetime
            from hydralib import session
            session.start(root, os.environ, datetime.datetime.now().astimezone(),
                          str(event.get("session_id") or "") if isinstance(event, dict) else "")
        except Exception:
            pass
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
