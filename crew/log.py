"""Minimal logging that tags each line so an orchestration trace is readable."""
from __future__ import annotations

import sys
import time

_EPOCH = time.time()


def _ts() -> str:
    return f"{time.time() - _EPOCH:7.2f}"


def info(msg: str) -> None:
    print(f"[{_ts()}] [crew] {msg}", flush=True)


def agent(name: str, msg: str) -> None:
    print(f"[{_ts()}] [{name}] {msg}", flush=True)


def section(title: str) -> None:
    print(f"\n[{_ts()}] === {title} ===\n", flush=True)


def warn(msg: str) -> None:
    print(f"[{_ts()}] [warn] {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    print(f"[{_ts()}] [error] {msg}", file=sys.stderr, flush=True)


def debug(msg: str) -> None:
    print(f"[{_ts()}] [debug] {msg}", flush=True)
