"""
Feedback loop live-usage operator surface.
"""

from __future__ import annotations

from django.views.decorators.http import require_GET

from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_help_signals import operator_help_signal_bundle
from apps.schools.operator_report_render import render_manager_report_page


@require_GET
@require_control_plane_access
def manager_feedback_loop(request):
    bundle = operator_help_signal_bundle()
    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_feedback_loop_body.html",
        context={
            "friction": bundle["friction"],
            "feedback": bundle["feedback"],
            "ai": bundle["ai"],
            "total_signal_7d": bundle["total_signal_7d"],
            "is_empty": bundle["is_empty"],
            "now": bundle["now"],
        },
        page_title="Feedback loop · live usage",
    )
