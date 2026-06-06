"""Shared helpers for Wedge 22 multi-campus rollup views."""

from __future__ import annotations

import uuid


def parse_parent_school_id(raw: str | None) -> uuid.UUID | None:
    """Parse ``?parent=`` query value; School PK is UUID, not integer."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except (ValueError, AttributeError, TypeError):
        return None
