"""JSON extraction helpers.

We ask routing agents to reply with JSON and parse it ourselves (the installed
opencode binary predates the SDK's structured-output endpoint, so there is no
server-side guarantee). Balanced-brace extraction tolerates stray prose and
markdown fences.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text

    for start in range(len(candidate)):
        ch = candidate[start]
        if ch not in "{[":
            continue
        end = _balanced_end(candidate, start)
        if end < 0:
            continue
        try:
            return json.loads(candidate[start:end])
        except json.JSONDecodeError:
            continue
    return None


def _balanced_end(s: str, start: int) -> int:
    opening = s[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_str = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if c == '"' and s[i - 1] != "\\":
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opening:
            depth += 1
        elif c == closing:
            depth -= 1
            if depth == 0:
                return i + 1
    return -1
