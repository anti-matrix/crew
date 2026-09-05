"""Typed message shapes shared across the orchestrator.

Agents never talk to each other directly. Each agent is a warm opencode
session; it replies with one of these typed messages and the supervisor routes,
enforces lanes, schedules parallelism, and applies termination rules.
"""
from __future__ import annotations

from typing import Any, Literal

AgentName = Literal[
    "alpha",
    "omega",
    "bureaucrat",
    "academic",
    "amodei",
    "peer-reviewer",
    "escribe",
    "benjamin",
]

Sender = str  # AgentName | "user" | "orchestrator"

MsgType = Literal[
    "system",
    "task",
    "result",
    "ask_user",
    "user_answer",
    "audit_flag",
    "done",
]


class Message:  # pragma: no cover - plain data holder, kept minimal
    def __init__(
        self,
        *,
        id: str,
        type: MsgType,
        from_: Sender,
        to: Sender,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.type = type
        self.from_ = from_
        self.to = to
        self.payload = payload or {}
        self.ts = __import__("time").time()


AGENTS: tuple[AgentName, ...] = (
    "alpha",
    "omega",
    "bureaucrat",
    "academic",
    "amodei",
    "peer-reviewer",
    "escribe",
    "benjamin",
)

LANES: dict[AgentName, tuple[str, ...]] = {
    "alpha": ("plan",),
    "omega": ("plan",),
    "bureaucrat": ("dispatch",),
    "academic": ("work",),
    "amodei": ("work",),
    "peer-reviewer": ("work",),
    "escribe": ("audit",),
    "benjamin": ("audit", "report"),
}
