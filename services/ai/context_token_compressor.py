"""
Trim AI support context to fit local-model windows (e.g. llama3).

Prioritizes permission/route signals over verbose prose blocks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class ContextTokenCompressor:
    """Lossy-but-safe compressor for engine-room / code-oracle payloads."""

    max_chars: int = 12_000
    priority_keys: tuple[str, ...] = (
        "tenant_id",
        "school_id",
        "required_permissions",
        "url_path",
        "route_name",
        "allowable_methods",
        "role",
        "scopes",
    )

    def compress_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload:
            return {}
        ordered: dict[str, Any] = {}
        for key in self.priority_keys:
            if key in payload and payload[key] not in (None, "", [], {}):
                ordered[key] = payload[key]
        for key, value in payload.items():
            if key in ordered:
                continue
            ordered[key] = value
        blob = json.dumps(ordered, ensure_ascii=True, default=str)
        if len(blob) <= self.max_chars:
            return ordered
        trimmed = dict(ordered)
        for drop_key in list(trimmed.keys()):
            if drop_key in self.priority_keys:
                continue
            trimmed.pop(drop_key, None)
            if len(json.dumps(trimmed, ensure_ascii=True, default=str)) <= self.max_chars:
                return trimmed
        return {k: trimmed[k] for k in self.priority_keys if k in trimmed}

    def compress_text_blocks(
        self,
        blocks: Iterable[str],
        *,
        head_reserve: int = 2_000,
    ) -> str:
        parts = [b.strip() for b in blocks if (b or "").strip()]
        if not parts:
            return ""
        if sum(len(p) for p in parts) <= self.max_chars:
            return "\n\n".join(parts)
        head = parts[0][:head_reserve]
        tail_budget = max(0, self.max_chars - len(head) - 4)
        tail = parts[-1][:tail_budget] if tail_budget else ""
        return f"{head}\n...\n{tail}".strip()
