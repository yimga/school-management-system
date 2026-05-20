"""
Server-Sent Events helpers for the support assistant stream endpoint.
"""

from __future__ import annotations

import json
from typing import Any


def format_sse_frame(*, event: str, payload: dict[str, Any], event_id: str | None = None) -> bytes:
    parts: list[str] = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    if event:
        parts.append(f"event: {event}")
    parts.append("data: " + json.dumps(payload, default=str))
    parts.append("")
    return ("\n".join(parts) + "\n").encode("utf-8")


def heartbeat_frame() -> bytes:
    return b": ping\n\n"
