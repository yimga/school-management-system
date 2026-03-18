"""
Plan II: LMS / Zoom attendance scaffold.
Abstract provider for syncing attendance from Zoom, Teams, or other LMS.
Production needs external APIs (Zoom, Microsoft Graph) and credentials.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class LmsAttendanceRecord:
    """Single attendance record from an LMS (e.g. Zoom meeting)."""

    external_id: str
    user_identifier: str  # email or LMS user id
    joined_at: str  # ISO datetime
    left_at: str | None
    duration_minutes: int | None
    raw_data: dict | None = None


class LmsAttendanceProvider(ABC):
    """Abstract base for syncing attendance from Zoom, Teams, or other LMS."""

    @abstractmethod
    def fetch_attendance(
        self, meeting_id: str, session_date: date
    ) -> List[LmsAttendanceRecord]:
        """Fetch attendance for a meeting/session. Requires external API credentials."""
        pass

    def health_check(self) -> bool:
        """Optional: verify API connectivity."""
        return True


def get_lms_attendance_provider(school, provider_code: str = "zoom"):
    """
    Return configured LmsAttendanceProvider for the tenant, or None.
    Configure via ServiceIntegration (e.g. Zoom API key, Microsoft Graph).
    """
    from apps.siteconfig.integration_registry import resolve_active_integration

    rec = resolve_active_integration(school, provider_code) if school else None
    if not rec or not getattr(rec, "config", None):
        return None
    # Stub: no concrete Zoom/Teams implementation; production would instantiate ZoomProvider etc.
    return None
