"""One warm opencode session per crew member.

Sessions persist for the whole round, so context stays warm across turns — the
"full agent, not subagent" behaviour the native turn-based mode can't provide.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import log
from .jsonx import extract_json
from .opencode import OpenCode, extract_text
from .roles import Role


@dataclass
class AgentReply:
    text: str
    structured: Any = None
    error: str | None = None


class Agent:
    def __init__(
        self,
        oc: OpenCode,
        name: str,
        role: Role,
        session_id: str,
    ) -> None:
        self.oc = oc
        self.name = name
        self.role = role
        self.session_id = session_id

    @classmethod
    async def spawn(cls, oc: OpenCode, name: str, role: Role) -> "Agent":
        data = await oc.create_session(title=f"crew:{name}")
        sid = data.get("id")
        if not sid:
            raise RuntimeError(f"no session id returned for {name}")
        return cls(oc, name, role, sid)

    async def send(self, prompt: str, *, json_out: bool = False) -> AgentReply:
        text = prompt
        if json_out:
            text += (
                "\n\nIMPORTANT: respond with a single JSON object only — no markdown "
                "code fences, no commentary."
            )

        last_error: str | None = None

        for idx, (provider, model) in enumerate(self.role.candidates):
            try:
                res = await self.oc.prompt(
                    self.session_id,
                    text,
                    agent=self.name,
                    provider=provider,
                    model=model,
                )
                reply_text = extract_text(res.get("parts"))
            except Exception as e:
                last_error = str(e)
                if idx < len(self.role.candidates) - 1:
                    nxt_provider, nxt_model = self.role.candidates[idx + 1]
                    log.warn(
                        f"{self.name}: {provider}/{model} failed ({e}); "
                        f"falling back to {nxt_provider}/{nxt_model}"
                    )
                continue

            if text.strip() and not reply_text.strip():
                last_error = f"empty response from {provider}/{model}"
                if idx < len(self.role.candidates) - 1:
                    nxt_provider, nxt_model = self.role.candidates[idx + 1]
                    log.warn(
                        f"{self.name}: {provider}/{model} returned empty; "
                        f"falling back to {nxt_provider}/{nxt_model}"
                    )
                continue

            try:
                structured = extract_json(reply_text) if json_out else None
            except Exception as e:
                return AgentReply(text="", error=str(e))

            return AgentReply(text=reply_text, structured=structured)

        log.warn(f"{self.name}: all candidates failed; last error: {last_error}")
        return AgentReply(text="", error=last_error)
