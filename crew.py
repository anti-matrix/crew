#!/usr/bin/env python3
"""crew — open the crew with one command.

Usage:
    python crew.py                          # open the TUI, crew greets you
    python crew.py --cwd <project>          # ...inside a specific project
    python crew.py --goal "your request"    # TUI opens with this already submitted
    echo "your request" | python crew.py    # same as --goal, via pipe
    python crew.py --headless --goal "..."  # no TUI; run one orchestrator round
    python crew.py --url http://localhost:4096 --goal "..."   # push into an open TUI

Opens the opencode TUI in the project (default: current dir), waits for it,
then submits the initial prompt (--goal, piped stdin, or a default greeting).
Stays attached until you quit the TUI.
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
