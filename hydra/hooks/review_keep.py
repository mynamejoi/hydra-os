#!/usr/bin/env python3
"""The main plugin's PostToolUse hook for WebSearch: each listed search's answer kept as it comes back, for its page
(Research's raw search results kept by the main plugin's hook, as reads are). Only a session under the review's fence,
and only a search hydra think listed, character for
character, is kept: in <root>/hydra/think/kept/<page>/<search id>.json, {"query", "answer"}, "answer" being WebSearch's
own result as Claude Code hands it to the hook, whole. At hydra think done <page>, Hydra-OS gives each to the page's own
save as that search's part, so web text never passes through Claude's typing or a shell. It says nothing and decides
nothing: anything it can't do, it leaves. Python 3.9 standard library only, run as python3 -I."""
import json
import os
import sys


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict) or event.get("tool_name") != "WebSearch":
            return 0
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from hydralib import review_fence as fence
        from hydralib import think
        root = fence.root_for(event.get("cwd") if isinstance(event.get("cwd"), str) else None)
        if root:
            think.keep_search(root, str(event.get("session_id") or ""), event.get("tool_input"),
                              event.get("tool_response"))
    except Exception:  # never in the way of the review
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

