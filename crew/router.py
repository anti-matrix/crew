"""The routing table — the code form of the prose that used to live in
``bureaucrat.md``.

Declares the valid lanes between agents. The supervisor validates every message
against it so no agent can reach outside its lane.

Note: because the supervisor mediates all traffic, ``academic``/``amodei``/
``peer-reviewer``/``escribe``/``benjamin`` reply to ``"orchestrator"``; the
supervisor then forwards to the intended recipient. The lanes below express the
*logical* permission, not the wire hop.
"""
from __future__ import annotations

from .types import AgentName

ROUTES: dict[AgentName, tuple[str, ...]] = {
    "alpha": ("omega", "user"),
    "omega": ("alpha",),
    "bureaucrat": ("alpha", "omega"),
    "academic": ("alpha", "omega", "bureaucrat", "orchestrator"),
    "amodei": ("alpha", "omega", "bureaucrat", "orchestrator"),
    "peer-reviewer": ("alpha", "omega", "bureaucrat", "orchestrator"),
    "escribe": ("alpha", "omega", "benjamin"),
    "benjamin": ("alpha", "user", "orchestrator"),
}


def can_send(from_: str, to: str) -> bool:
    if from_ in ("user", "orchestrator"):
        return True
    return to in ROUTES.get(from_, ())  # type: ignore[arg-type]
