"""CLI.

Default flow — ``python crew.py``:
    1. Opens the opencode TUI in the project (`--cwd`, default: current dir).
    2. Once it's up, gives it an initial prompt: ``--goal`` if passed, piped
       stdin if piped, otherwise a default greeting so the crew opens by
       asking what you want to build.
    3. Stays attached until you quit the TUI.

Additional modes:
    ``python crew.py --url http://localhost:4096 --goal "..."``
        Push the prompt into a TUI/server you already have open (no spawn).
    ``python crew.py --headless ...``
        Skip the TUI entirely and run a full supervisor round (spawns its own
        server if no ``--url``).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

from . import log
from .opencode import OpenCode, OpenCodeError
from .supervisor import Supervisor

DEFAULT_PORT = 4096
READY_TIMEOUT_S = 45.0

DEFAULT_OPENING = (
    "Alpha, the crew is assembled. Greet me and ask what we're working on."
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="crew", description="Open the opencode crew.")
    p.add_argument("--cwd", help="project directory to work in (default: current dir)")
    p.add_argument("--goal", help="initial prompt to hand the crew (optional)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"port for the TUI/server (default {DEFAULT_PORT})")
    p.add_argument("--url", help="push the prompt into an already-running TUI/server instead of spawning one")
    p.add_argument("--opencode", action="store_true",
                   help=argparse.SUPPRESS)  # legacy flag, auto-spawn is the default
    p.add_argument("--headless", action="store_true",
                   help="skip the TUI; run one full orchestrator round and exit")
    return p.parse_args(argv)


def _read_piped() -> str | None:
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read().strip()
    return data or None


async def _wait_ready(
    oc: OpenCode,
    proc: asyncio.subprocess.Process,
    max_seconds: float,
) -> None:
    for _ in range(int(max_seconds)):
        if proc.returncode is not None:
            raise OpenCodeError(
                f"opencode exited early (code {proc.returncode}). "
                "Is `opencode` on your PATH?"
            )
        try:
            await oc.ping()
            log.info("opencode ready")
            return
        except Exception:
            await asyncio.sleep(1.0)
    raise OpenCodeError("opencode did not become ready in time")


async def _spawn(cmdline_args: str, cwd: str) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "cmd", "/c", cmdline_args,
        cwd=cwd,
    )


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    try:
        proc.terminate()
    except ProcessLookupError:
        pass


async def _give_prompt(oc: OpenCode, text: str | None) -> None:
    prompt = text or DEFAULT_OPENING
    try:
        await oc.append_prompt(prompt)
        await oc.submit_prompt()
        log.info("initial prompt submitted")
    except OpenCodeError as e:
        log.warn(f"could not submit initial prompt: {e}")


async def _tui_flow(oc: OpenCode, cwd: str, opening: str | None, port: int) -> int:
    log.section("OPENING OPENCODE TUI")
    log.info(f"project: {cwd}  port: {port}")
    proc = await _spawn(f"opencode --port {port}", cwd)
    try:
        await _wait_ready(oc, proc, READY_TIMEOUT_S)
        await _give_prompt(oc, opening)
        log.info("TUI open — interact normally, quit when done")
        code = await proc.wait()
        log.info(f"opencode exited ({code or 0})")
        return code or 0
    finally:
        _kill_tree(proc)


async def _headless_flow(oc: OpenCode, cwd: str, goal: str, spawn: bool, port: int) -> int:
    server_proc: asyncio.subprocess.Process | None = None
    try:
        if spawn:
            log.section("SPAWNING OPENCODE SERVER")
            log.info(f"project: {cwd}  port: {port}")
            server_proc = await _spawn(f"opencode serve --port {port}", cwd)
            await _wait_ready(oc, server_proc, READY_TIMEOUT_S)
        sup = Supervisor(cwd, interactive=True)
        await sup.spawn_all(oc)
        result = await sup.run(goal)
        log.info(f"round finished: {result.get('status')}")
        return 0
    finally:
        if server_proc is not None:
            _kill_tree(server_proc)


async def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cwd = args.cwd or os.getcwd()
    oc = OpenCode(args.url or f"http://127.0.0.1:{args.port}")

    if args.headless:
        goal = args.goal or _read_piped()
        if not goal:
            log.error("headless mode needs a goal: --goal '...' or piped stdin")
            return 1
        return await _headless_flow(oc, cwd, goal, spawn=args.url is None, port=args.port)

    opening = args.goal or _read_piped()
    if args.url:
        log.info(f"pushing prompt into {args.url}")
        await _give_prompt(oc, opening)
        return 0
    return await _tui_flow(oc, cwd, opening, args.port)
