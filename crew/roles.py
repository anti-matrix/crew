"""Agent roles: model assignment, lane, and whether the agent may write files.

Model ids here are placeholders that mirror the existing crew definitions under
``~/.config/opencode/agent/*.md``. Point ``escribe`` at your free model — its
only model task is a short rolling summary, so a small context window is fine
(the faithful record append is done by :class:`crew.scribe.Scribe` in pure
Python, no tokens).
"""
from __future__ import annotations

from typing import Literal

from .types import AgentName

Lane = Literal["plan", "dispatch", "work", "audit", "report"]


class Role:
    __slots__ = ("lane", "provider", "model", "can_write", "fallback")

    def __init__(
        self,
        lane: Lane,
        provider: str,
        model: str,
        can_write: bool,
        fallback: tuple[str, str] | None = None,
    ) -> None:
        self.lane = lane
        self.provider = provider
        self.model = model
        self.can_write = can_write
        self.fallback = fallback

    @property
    def candidates(self) -> list[tuple[str, str]]:
        """Provider/model pairs to try, primary first, fallback second."""
        pairs: list[tuple[str, str]] = [(self.provider, self.model)]
        if self.fallback is not None:
            pairs.append(self.fallback)
        return pairs


ROLES: dict[AgentName, Role] = {
    "alpha": Role(
        "plan", "opencode-go", "deepseek-v4-pro",
        can_write=False,
        fallback=("opencode", "deepseek-v4-flash"),
    ),
    "omega": Role("plan", "opencode-go", "kimi-k2.7-code", can_write=False),
    "academic": Role(
        "work", "opencode-go", "deepseek-v4-pro",
        can_write=False,
        fallback=("opencode", "deepseek-v4-flash"),
    ),
    "amodei": Role("work", "opencode-go", "kimi-k2.7-code", can_write=True),
    "peer-reviewer": Role(
        "work", "opencode-go", "deepseek-v4-pro",
        can_write=False,
        fallback=("opencode", "deepseek-v4-flash"),
    ),
    "escribe": Role(
        "audit", "opencode-go", "deepseek-v4-pro",
        can_write=True,
        fallback=("opencode", "deepseek-v4-flash"),
    ),
    "benjamin": Role(
        "audit", "opencode-go", "deepseek-v4-pro",
        can_write=False,
        fallback=("opencode", "deepseek-v4-flash"),
    ),
}


def role(id: AgentName) -> Role:
    return ROLES[id]


class Budgets:
    __slots__ = ("plan_cycles", "refine_cycles", "audit_cycles")

    def __init__(self, plan_cycles: int, refine_cycles: int, audit_cycles: int) -> None:
        self.plan_cycles = plan_cycles
        self.refine_cycles = refine_cycles
        self.audit_cycles = audit_cycles


BUDGETS = Budgets(plan_cycles=5, refine_cycles=2, audit_cycles=3)
