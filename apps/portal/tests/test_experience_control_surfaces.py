"""Experience_control closure — portal-owned surfaces (subset of roster)."""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import reverse

from apps.platform_runtime.tests.experience_control_registry import (
    EXPERIENCE_CONTROL_SCREENS,
    reverse_screen,
)

_PORTAL_IDS = frozenset(
    {
        "teacher_dashboard",
        "parent_dashboard",
        "student_360",
        "offline_sync_queue",
        "billing_surfaces",
    }
)


class PortalExperienceControlRegistrySubsetTests(SimpleTestCase):
    def test_portal_roster_entries_resolve(self):
        for row in EXPERIENCE_CONTROL_SCREENS:
            if row["id"] in _PORTAL_IDS:
                reverse_screen(row)

    def test_teacher_attendance_export_reverse(self):
        reverse(
            "portal:teacher_attendance_export",
            urlconf="config.tenant_urls",
        )
