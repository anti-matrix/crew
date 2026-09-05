"""The user channel.

Agents don't talk to the human directly; they post ``ask_user`` intents and the
supervisor batches them here. Batched so review agents don't nag one question
per message.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class Asked:
    question: str
    answer: str
    requester: str


@dataclass
class Question:
    question: str
    requester: str


class UserChannel:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._pending: list[Question] = []

    def add(self, question: str, requester: str) -> None:
        self._pending.append(Question(question, requester))

    def has_pending(self) -> bool:
        return bool(self._pending)

    async def ask_all(self) -> list[Asked]:
        out: list[Asked] = []
        if not self.enabled:
            self._pending = []
            return out

        loop = asyncio.get_running_loop()
        for q in self._pending:
            answer = await loop.run_in_executor(
                None, lambda qq=q: input(f"\n? [{qq.requester}] {qq.question}\n  > ")
            )
            out.append(Asked(q.question, answer.strip(), q.requester))
        self._pending = []
        return out
