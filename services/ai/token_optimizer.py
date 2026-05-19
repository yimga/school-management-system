"""Context window budgeting for local Ollama (char-based token estimate)."""

from __future__ import annotations

import re
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


@dataclass
class CompressedContext:
    permission_block: str
    screen_block: str
    knowledge_block: str
    history_block: str
    truncated: bool

    def as_prompt_sections(self) -> str:
        parts = [
            self.permission_block,
            self.screen_block,
            self.knowledge_block,
            self.history_block,
        ]
        return "\n".join(p for p in parts if p.strip())


class ContextTokenCompressor:
    """
    Hierarchical truncation:
    permissions → active screen → help excerpts → history.
    """

    def __init__(self, *, max_input_tokens: int = 6000) -> None:
        self.max_input_tokens = max(512, int(max_input_tokens))

    @staticmethod
    def _densify(text: str) -> str:
        out = re.sub(r"\n{3,}", "\n\n", text or "")
        out = re.sub(r"[ \t]{2,}", " ", out)
        return out.strip()

    def compress(
        self,
        *,
        permission_block: str,
        screen_block: str,
        knowledge_block: str,
        history_block: str = "",
    ) -> CompressedContext:
        permission_block = self._densify(permission_block)
        screen_block = self._densify(screen_block)
        knowledge_block = self._densify(knowledge_block)
        history_block = self._densify(history_block)

        blocks = [
            ("permission", permission_block),
            ("screen", screen_block),
            ("knowledge", knowledge_block),
            ("history", history_block),
        ]
        truncated = False
        budget = self.max_input_tokens

        def total_tokens() -> int:
            return sum(estimate_tokens(b[1]) for b in blocks if b[1])

        while total_tokens() > budget:
            trimmed = False
            for idx in range(len(blocks) - 1, -1, -1):
                key, value = blocks[idx]
                if not value:
                    continue
                if key == "permission":
                    continue
                if len(value) <= 80:
                    blocks[idx] = (key, "")
                else:
                    blocks[idx] = (key, value[: max(80, len(value) // 2)].rstrip() + "…")
                trimmed = True
                truncated = True
                break
            if not trimmed:
                break
            if total_tokens() <= budget:
                break

        by_key = {k: v for k, v in blocks}
        return CompressedContext(
            permission_block=by_key.get("permission", ""),
            screen_block=by_key.get("screen", ""),
            knowledge_block=by_key.get("knowledge", ""),
            history_block=by_key.get("history", ""),
            truncated=truncated,
        )
