"""
Lightweight support intent routing (rules-first; no extra model call).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class SupportIntent(str, Enum):
    UI_NAVIGATION_HELP = "UI_NAVIGATION_HELP"
    TROUBLESHOOTING_ERROR = "TROUBLESHOOTING_ERROR"
    API_DEVELOPER_SUPPORT = "API_DEVELOPER_SUPPORT"


_ERROR_MARKERS = (
    "error",
    "exception",
    "traceback",
    "500",
    "403",
    "404",
    "failed",
    "cannot",
    "can't",
    "timeout",
    "broken",
    "not working",
)

_API_MARKERS = (
    "api",
    "webhook",
    "openapi",
    "rest",
    "graphql",
    "schema",
    "endpoint",
    "bearer",
    "token scope",
    "drf",
)


def classify_support_intent(
    query: str,
    *,
    active_url: str = "",
    route_row: dict[str, Any] | None = None,
) -> SupportIntent:
    low = (query or "").lower()
    path = (active_url or "").lower()
    if any(marker in low for marker in _API_MARKERS) or "/api/" in path or "/apicenter/" in path:
        return SupportIntent.API_DEVELOPER_SUPPORT
    if any(marker in low for marker in _ERROR_MARKERS):
        return SupportIntent.TROUBLESHOOTING_ERROR
    if route_row and route_row.get("url_path"):
        return SupportIntent.UI_NAVIGATION_HELP
    if re.search(r"\b(how do i|where is|navigate|open|find|click)\b", low):
        return SupportIntent.UI_NAVIGATION_HELP
    return SupportIntent.UI_NAVIGATION_HELP


def intent_prompt_hint(intent: SupportIntent, *, language: str = "en") -> str:
    lang = (language or "en").split("-")[0]
    base = {
        SupportIntent.UI_NAVIGATION_HELP: "Prioritize UI navigation steps from route registry and KB.",
        SupportIntent.TROUBLESHOOTING_ERROR: "Prioritize error resolution, logs, and permission checks.",
        SupportIntent.API_DEVELOPER_SUPPORT: "Prioritize API schema, scopes, and developer docs; no tenant PII.",
    }.get(intent, "")
    if lang and lang != "en":
        return f"{base} Respond in language code '{lang}'."
    return base
