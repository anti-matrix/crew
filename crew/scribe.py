"""Escribe, the deterministic half.

The faithful record is a mechanical append — it must NOT go through an LLM
(that's what blew the token budget and was, ironically, less faithful). The
free-model ``escribe`` agent only writes the rolling summary; everything here
is pure Python file I/O.
"""
from __future__ import annotations

import os
from pathlib import Path


class Scribe:
    def __init__(self, cwd: str | Path) -> None:
        self.cwd = Path(cwd)
        self.transcript_path = self.cwd / "escribe_transcript.md"
        self.context_path = self.cwd / "escribe_context.md"

    def append(self, line: str) -> None:
        with self.transcript_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def record(self, msg) -> None:
        stamp = __import__("time").strftime("%Y-%m-%dT%H:%M:%S", __import__("time").localtime(msg.ts))
        payload = msg.payload or {}
        try:
            body = __import__("json").dumps(payload, ensure_ascii=False)
        except Exception:
            body = str(payload)
        self.append(f"[{stamp}] {msg.from_} -> {msg.to} ({msg.type}): {body}")

    def read_transcript(self) -> str:
        if not self.transcript_path.exists():
            return ""
        return self.transcript_path.read_text(encoding="utf-8")

    def tail(self, lines: int) -> str:
        return "\n".join(self.read_transcript().splitlines()[-lines:])

    def read_context(self) -> str:
        if not self.context_path.exists():
            return ""
        return self.context_path.read_text(encoding="utf-8")

    def write_context(self, text: str) -> None:
        self.context_path.write_text(text, encoding="utf-8")

    def ensure_dir(self) -> None:
        os.makedirs(self.cwd, exist_ok=True)
