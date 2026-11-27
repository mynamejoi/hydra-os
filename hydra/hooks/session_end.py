#!/usr/bin/env python3
"""The main plugin's SessionEnd hook, for chats in the Hydra-OS folder: a session under the morning review's fence that
ends leaves it, and with no session left the fence lifts, rather than after 30 minutes; and with the helpers off, Home's
server stops once no Hydra-OS chat is left (hydralib/session.py). It says and decides nothing. Python 3.9 standard
library only, run as python3 -I."""
import json
import os
import sys


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            return 0
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from hydralib import review_fence as fence
        root = fence.root_for(event.get("cwd") if isinstance(event.get("cwd"), str) else None)
        if root:
            fence.release(root, str(event.get("session_id") or ""))
    except Exception:
        root = None
    try:
        if root:
            import datetime
            from hydralib import session
            session.end(root, os.environ, datetime.datetime.now().astimezone(), str(event.get("session_id") or ""))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
