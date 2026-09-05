"""crew — real-time multi-agent orchestrator for opencode."""

from .agent import Agent, AgentReply
from .opencode import OpenCode, OpenCodeError, extract_text
from .roles import BUDGETS, ROLES, Budgets, Role, role
from .scribe import Scribe
from .supervisor import Supervisor
from .types import AGENTS, AgentName
from .user_channel import Asked, Question, UserChannel

__all__ = [
    "Agent",
    "AgentReply",
    "OpenCode",
    "OpenCodeError",
    "extract_text",
    "AGENTS",
    "AgentName",
    "BUDGETS",
    "ROLES",
    "Budgets",
    "Role",
    "role",
    "Scribe",
    "Supervisor",
    "Asked",
    "Question",
    "UserChannel",
]
