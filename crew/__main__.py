"""``python -m crew`` entrypoint — delegates to the CLI."""
from __future__ import annotations

import asyncio
import sys

from . import log
from .cli import main


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(sys.argv[1:])))
    except KeyboardInterrupt:
        log.warn("interrupted")
        raise SystemExit(130)
