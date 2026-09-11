"""CLI.

Default flow — ``python crew.py``:
    1. Boots a short-lived headless opencode server in the project (`--cwd`,
       default: current dir) and has **Alpha** answer the opening prompt
       (``--goal`` if passed, piped stdin if piped, otherwise a default
       greeting) — so the crew session exists before any window shows.
    2. Opens the opencode TUI directly on that session
       (``opencode -s <session>``), greeting already answered, Alpha front
       and center.
    3. Stays attached until you quit the TUI.

Why this shape: the TUI control endpoints (append/submit/execute-command)
silently do nothing in opencode 1.18.29, so we never drive the TUI — we create
the session server-side and resume into it, exactly like ``opencode -s``.

Additional modes:
    ``python crew.py --url http://localhost:4096 --goal "..."``
        Create the crew session on a server/TUI you already have open.
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
from .roles import ROLES
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


async def _make_crew_session(oc: OpenCode, text: str) -> str:
    """Create the crew session server-side and have Alpha answer the opening
    prompt. Returns the session id."""
    role = ROLES["alpha"]
    data = await oc.create_session(title=f"crew — {text[:48]}")
    sid = data["id"]
    tried: list[tuple[str, str]] = []
    for idx, (provider, model) in enumerate(role.candidates):
        tried.append((provider, model))
        try:
            await oc.prompt(sid, text, agent="alpha", provider=provider, model=model)
            return sid
        except OpenCodeError as e:
            if idx < len(role.candidates) - 1:
                nxt_provider, nxt_model = role.candidates[idx + 1]
                log.warn(
                    f"alpha greeting: {provider}/{model} failed ({e}); "
                    f"falling back to {nxt_provider}/{nxt_model}"
                )
            else:
                tried_str = ", ".join(f"{p}/{m}" for p, m in tried)
                log.warn(
                    f"alpha greeting turn failed ({e}); tried {tried_str}; "
                    f"the session still has your prompt"
                )
    return sid


async def _spawn_headless(cwd: str, port: int) -> tuple[asyncio.subprocess.Process, int]:
    """Start a headless server, trying a few ports in case the first is
    occupied. Returns the process and the port that actually worked."""
    last_err: Exception | None = None
    for p in (port, port + 1, port + 2, port + 3):
        proc = await _spawn(f"opencode serve --port {p}", cwd)
        try:
            await _wait_ready(OpenCode(f"http://127.0.0.1:{p}"), proc, 20.0)
            return proc, p
        except Exception as e:  # port busy or boot failure — try the next one
            last_err = e
            _kill_tree(proc)
    raise OpenCodeError(f"could not start a headless opencode server: {last_err}")


async def _tui_flow(cwd: str, opening: str | None, port: int) -> int:
    log.section("OPENING THE CREW")
    log.info(f"project: {cwd}")
    prompt_text = opening or DEFAULT_OPENING

    # Phase 1: create the crew session headlessly and let Alpha answer.
    headless, headless_port = await _spawn_headless(cwd, port)
    log.info("crewing up — Alpha is answering the opening prompt…")
    try:
        sid = await _make_crew_session(
            OpenCode(f"http://127.0.0.1:{headless_port}"), prompt_text
        )
    finally:
        _kill_tree(headless)

    # Phase 2: resume the TUI straight into that session.
    log.info(f"opening the TUI on crew session {sid}")
    proc = await _spawn(f"opencode -s {sid}", cwd)
    try:
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
        log.info(f"creating crew session on {args.url}")
        sid = await _make_crew_session(oc, opening or DEFAULT_OPENING)
        log.info(f"crew session created: {sid} — open it in your TUI session list")
        return 0
    return await _tui_flow(cwd, opening, args.port)
