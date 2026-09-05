"""One warm opencode session per crew member.

Sessions persist for the whole round, so context stays warm across turns — the
"full agent, not subagent" behaviour the native turn-based mode can't provide.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
        try:
            res = await self.oc.prompt(
                self.session_id,
                text,
                agent=self.name,
                provider=self.role.provider,
                model=self.role.model,
            )
            reply_text = extract_text(res.get("parts"))
            structured = extract_json(reply_text) if json_out else None
            return AgentReply(text=reply_text, structured=structured)
        except Exception as e:  # network / server errors only
            return AgentReply(text="", error=str(e))
