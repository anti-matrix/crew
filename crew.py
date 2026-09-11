#!/usr/bin/env python3
"""crew — open the crew with one command.

Usage:
    python crew.py                          # TUI opens on the crew session, Alpha greets you
    python crew.py --cwd <project>          # ...inside a specific project
    python crew.py --goal "your request"    # that becomes the opening prompt
    echo "your request" | python crew.py    # same as --goal, via pipe
    python crew.py --headless --goal "..."  # no TUI; run one orchestrator round
    python crew.py --url http://localhost:4096 --goal "..."   # make the session on an existing server

How it works: a short-lived headless server creates the crew session and has
Alpha answer the opening prompt, then the opencode TUI opens *directly on that
session* (opencode -s) — greeting answered, Alpha front and center.
"""
from __future__ import annotations

import asyncio
import sys

from crew import log
from crew.cli import main

if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(sys.argv[1:])))
    except KeyboardInterrupt:
        log.warn("interrupted")
        raise SystemExit(130)
