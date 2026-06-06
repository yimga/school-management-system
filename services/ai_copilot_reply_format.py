"""Format structured guided-assistant payloads for chat surfaces (copilot rail, modals)."""
from __future__ import annotations

from typing import Any


def format_guided_assistant_reply(payload: dict[str, Any] | None) -> str:
    """Turn a guided_assistant dict into plain text for thread bubbles."""
    if not isinstance(payload, dict):
        return ""
    summary = str(payload.get("summary") or "").strip()
    parts: list[str] = []
    if summary:
        parts.append(summary)

    actions = payload.get("actions")
    if isinstance(actions, list) and actions:
        lines: list[str] = []
        for idx, row in enumerate(actions[:6], start=1):
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            detail = str(row.get("detail") or "").strip()
            if not title:
                continue
            lines.append(f"{idx}. {title}" + (f" — {detail}" if detail else ""))
        if lines:
            parts.append("**Next steps**\n" + "\n".join(lines))

    cautions = payload.get("cautions")
    if isinstance(cautions, list):
        caution_lines = [str(c).strip() for c in cautions[:4] if str(c).strip()]
        if caution_lines:
            parts.append("**Note:** " + " ".join(caution_lines))

    return "\n\n".join(parts).strip()


def extract_copilot_rail_reply(ai_result: Any) -> str:
    """Normalize gateway return values into operator-facing chat text."""
    if ai_result is None:
        return ""
    if isinstance(ai_result, str):
        return ai_result.strip()
    if hasattr(ai_result, "text") and isinstance(ai_result.text, str):
        return ai_result.text.strip()
    if isinstance(ai_result, dict):
        if str(ai_result.get("summary") or "").strip():
            return format_guided_assistant_reply(ai_result)
        for key in ("text", "reply"):
            value = ai_result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""
