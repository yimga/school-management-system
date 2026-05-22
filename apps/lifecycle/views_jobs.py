"""Operator-facing provisioning jobs dashboard.

URL: /super/provisioning/jobs/

Reads the last N SchoolProvisioningEvent rows + recent lifecycle
stages and surfaces:
- In-flight count (REQUESTED / STARTED / QUEUED, not yet COMPLETED)
- Recently completed (last 24h)
- Recently failed (last 24h)
- 50-row activity feed (newest first)

No Celery queue introspection — the database itself is the canonical
record of work. The dashboard is staff-only and refreshes via meta-tag.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.models import School, SchoolProvisioningEvent

from .models import SchoolLifecycleStage


_IN_FLIGHT_EVENTS = {
    "REQUEST_RECEIVED",
    "QUEUED",
    "STARTED",
    "PROFILE_APPLIED",
    "ACADEMIC_YEAR_READY",
    "SUBJECTS_READY",
    "BLUEPRINT_TEMPLATE_RECORDED",
    "SAMPLE_DATA_READY",
    "DOMAIN_PENDING",
}


@method_decorator(staff_member_required, name="dispatch")
class ProvisioningJobsDashboardView(View):
    template_name = "lifecycle/jobs_dashboard.html"

    def get(self, request):
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        recent_events = list(
            SchoolProvisioningEvent.objects.select_related("school")
            .order_by("-created_at")[:50]
        )
        completed_24h = SchoolProvisioningEvent.objects.filter(
            event_type="COMPLETED", created_at__gte=last_24h
        ).count()
        failed_24h = SchoolProvisioningEvent.objects.filter(
            event_type="FAILED", created_at__gte=last_24h
        ).count()
        # "In flight" = schools whose latest provisioning event is in a
        # mid-pipeline state. We pull the latest event per school via a
        # subquery-free approximation: walk the most recent 200 events
        # and pick the per-school newest.
        in_flight = 0
        seen: set = set()
        for event in (
            SchoolProvisioningEvent.objects.order_by("-created_at")
            .only("school_id", "event_type")[:500]
        ):
            if event.school_id in seen:
                continue
            seen.add(event.school_id)
            if event.event_type in _IN_FLIGHT_EVENTS:
                in_flight += 1

        recent_lifecycle = list(
            SchoolLifecycleStage.objects.select_related("school")
            .order_by("-created_at")[:50]
        )
        new_schools_7d = School.objects.filter(created_at__gte=last_7d).count()

        ctx = {
            "now": now,
            "in_flight": in_flight,
            "completed_24h": completed_24h,
            "failed_24h": failed_24h,
            "new_schools_7d": new_schools_7d,
            "recent_events": recent_events,
            "recent_lifecycle": recent_lifecycle,
        }
        return render(request, self.template_name, ctx)
