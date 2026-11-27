#!/usr/bin/env python3
"""The main plugin's PreToolUse hook: the morning review's fence (hydralib/review_fence.py). Its command in hooks.json
starts it only when this Hydra-OS folder has a fence in
force, or the call holds the word think. Claude Code sends the tool call as JSON on stdin. A refusal exits 2 with its reason on
stderr, which blocks the call and shows Claude why; anything else exits 0 with no opinion, leaving the call to Claude
Code's own permissions. When it can't decide, it refuses only while a fence is in force here. Python 3.9 standard
library only, run as python3 -I."""
import json
import os
import sys

REFUSED = "During the morning review, Claude uses only hydra think and the reads it lists."


def _in_force():
    """Whether a fence is in force in the folder this session works in, read without the plugin's library."""
    for start in (os.environ.get("HYDRA_ROOT"), os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()):
        here = os.path.abspath(os.path.expanduser(start)) if start else None
        while here:
            if os.path.isfile(os.path.join(here, "hydra", "config.json")):
                return os.path.exists(os.path.join(here, "hydra", "think", "fence.json"))
            up = os.path.dirname(here)
            here = None if up == here else up
    return False


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            raise ValueError("not a tool call")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from hydralib import review_fence as fence
        root = fence.root_for(event.get("cwd") if isinstance(event.get("cwd"), str) else None)
        ok, why = fence.decide(root, event) if root else (True, "")
    except Exception:  # it couldn't decide: a review under way stays fenced, and nothing else is touched
        ok, why = not _in_force(), REFUSED
    if ok:
        return 0
    print(why, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
