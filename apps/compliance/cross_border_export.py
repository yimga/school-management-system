"""
Cross-border compliance export gate — blocks downloads when school data_region
does not match the operator's active residency context (when enforcement is on).
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings


def cross_border_export_blocked(
    school: Any,
    *,
    destination_region: str | None = None,
) -> tuple[bool, str]:
    """
    Return (blocked, message). Soft by default; strict when DATA_RESIDENCY_ENFORCE=1.
    """
    if school is None:
        return False, ""

    school_region = (
        str(getattr(school, "data_region", None) or "").strip().lower()
    )
    if not school_region:
        return False, ""

    dest = (destination_region or "").strip().lower()
    if not dest:
        return False, ""

    if school_region == dest:
        return False, ""

    enforce = os.environ.get("DATA_RESIDENCY_ENFORCE", "").strip() in (
        "1",
        "true",
        "yes",
    ) or getattr(settings, "DATA_RESIDENCY_ENFORCE", False)

    if not enforce:
        return False, ""

    return (
        True,
        f"Export blocked: school data_region={school_region!r} does not match "
        f"active region={dest!r}. Adjust residency or use in-region operator session.",
    )
