"""Thin async client over the opencode server's HTTP API.

Python speaks the same JSON endpoints the TS SDK wraps. We only need two of
them: ``POST /session`` (spawn a warm agent session) and ``POST /session/{id}/
message`` (one prompt turn). Everything else the orchestrator does is plain
Python.
"""
from __future__ import annotations

import json
from typing import Any

import httpx


class OpenCodeError(RuntimeError):
    pass


class OpenCode:
    """Async handle to a running ``opencode serve``."""

    def __init__(self, base_url: str, timeout: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.get(f"{self.base_url}/global/event")
        return {"status": r.status_code}

    async def ping(self, *, timeout: float = 5.0) -> bool:
        """Readiness probe. GET /agent returns quickly once the server is up."""
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"{self.base_url}/agent")
        if r.status_code >= 400:
            raise OpenCodeError(f"server not ready ({r.status_code})")
        return True

    async def append_prompt(self, text: str) -> dict[str, Any]:
        """Append text to the TUI's input prompt."""
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{self.base_url}/tui/append-prompt", json={"text": text})
        return self._ok(r, "append-prompt")

    async def submit_prompt(self) -> dict[str, Any]:
        """Submit the TUI's current prompt."""
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{self.base_url}/tui/submit-prompt")
        return self._ok(r, "submit-prompt")

    async def create_session(self, title: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{self.base_url}/session", json={"title": title})
        return self._ok(r, "create session")

    async def prompt(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Send one user turn and await the assistant reply.

        Returns the parsed JSON body of the ``200`` response
        (``{"info": ..., "parts": [...]}``).
        """
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }
        if agent:
            body["agent"] = agent
        if provider and model:
            body["model"] = {"providerID": provider, "modelID": model}

        async with httpx.AsyncClient(timeout=self.timeout) as c:
            try:
                r = await c.post(f"{self.base_url}/session/{session_id}/message", json=body)
            except httpx.TimeoutException as e:
                raise OpenCodeError(f"timeout prompting {session_id}") from e
        return self._ok(r, "prompt")

    @staticmethod
    def _ok(r: httpx.Response, what: str) -> dict[str, Any]:
        if r.status_code >= 400:
            raise OpenCodeError(f"{what} failed ({r.status_code}): {r.text[:500]}")
        body = r.text.strip()
        if not body:
            return {}
        try:
            return r.json()
        except json.JSONDecodeError as e:
            raise OpenCodeError(f"{what} returned non-JSON: {body[:200]}") from e


def extract_text(parts: Any) -> str:
    """Pull the assistant's text out of a prompt response's ``parts`` list."""
    chunks: list[str] = []
    for p in parts or ():
        if isinstance(p, dict) and p.get("type") == "text":
            t = p.get("text")
            if isinstance(t, str):
                chunks.append(t)
    return "\n".join(chunks).strip()
