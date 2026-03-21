"""
Wave 6: Mobile-friendly entry to bulk capture flows (student roll call, teacher roll call).
Existing take_student_attendance already saves a full class in one POST; this hub improves discoverability.
Wave 18: Additional links (class overview, seating chart) for deeper mobile capture paths.
"""

from __future__ import annotations

from django.shortcuts import render
from django.urls import reverse

from apps.accounts.decorators import role_required, teacher_portal_required
from apps.accounts.models import User


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_bulk_capture_hub(request):
    """Landing page: large actions for field / mobile bulk workflows."""
    cards = [
        {
            "title": "Student roll call",
            "description": "Mark present, absent, late, or excused for an entire class in one save.",
            "url": reverse("portal:take_student_attendance"),
            "icon": "bi-clipboard-check",
            "primary": True,
        },
        {
            "title": "Teacher attendance",
            "description": "Staff check-in grid for the day (requires attendance.manage).",
            "url": reverse("portal:record_teacher_attendance"),
            "icon": "bi-person-badge",
            "primary": False,
        },
        {
            "title": "My classes & attendance",
            "description": "Open your class list and drill into daily attendance summaries.",
            "url": reverse("portal:teacher_attendance"),
            "icon": "bi-collection",
            "primary": False,
        },
        {
            "title": "Seating chart",
            "description": "Visual layout for quick presence checks in the room.",
            "url": reverse("portal:seating_chart"),
            "icon": "bi-grid-3x3",
            "primary": False,
        },
    ]
    return render(
        request,
        "portal/teacher_bulk_capture_hub.html",
        {
            "cards": cards,
            "offline_sync_note": True,
        },
    )
