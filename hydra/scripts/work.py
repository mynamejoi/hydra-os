#!/usr/bin/env python3
"""A step a button on Home started, carried out in a process of its own (hydralib/work.py): Update, the helpers' on and
off, Repair or Remove. Home's server starts it; it writes how it went to <root>/hydra/panel/work.json, which the page
reads through GET /api/panel. Python 3.9 standard library only.

    work.py --root DIR --step update|helpers-on|helpers-off|repair|remove [--app ID] [--started WHEN]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hydralib import config as cfg  # noqa: E402
from hydralib import work  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="A step a button on Home started")
    ap.add_argument("--root", required=True)
    ap.add_argument("--step", required=True, choices=sorted(work.STEPS))
    ap.add_argument("--app", default="")
    ap.add_argument("--started", default="", help="when the press started it, the run's at for the page")
    args = ap.parse_args(argv)
    try:
        config = cfg.load(args.root)
    except cfg.NotInstalled:
        return 1
    work.run(config, args.step, args.app, args.started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
