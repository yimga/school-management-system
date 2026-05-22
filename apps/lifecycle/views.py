"""Operator-facing 360 lifecycle timeline.

URL: /super/lifecycle/<uuid:school_id>/

Permissions: staff_member_required. This is a /super/ surface that
must NEVER bleed into tenant subdomains. The same guard pattern the
rest of /super/ uses (require_super_access_with_host) is the canonical
isolation primitive; we layer it on at the URL include site.
"""

from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.models import School

from .models import LIVE_STAGES, TERMINAL_STAGES, SchoolLifecycleStage
from .services import current_stage, stage_counts, timeline_for


@method_decorator(staff_member_required, name="dispatch")
class LifecycleTimelineView(View):
    """Per-school 360 timeline rendered as a vertical sequence."""

    template_name = "lifecycle/timeline.html"

    def get(self, request, school_id):
        school = get_object_or_404(School, id=school_id)
        timeline = list(timeline_for(school, limit=200))
        counts = stage_counts(timeline)
        latest = current_stage(school)
        ctx = {
            "school": school,
            "timeline": timeline,
            "counts": counts,
            "latest_stage": latest,
            "is_live": latest in LIVE_STAGES,
            "is_terminal": latest in TERMINAL_STAGES,
            "stage_labels": dict(SchoolLifecycleStage.Stage.choices),
        }
        return render(request, self.template_name, ctx)
