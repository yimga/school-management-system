"""
First-touch funnel instrumentation for authenticated tenant traffic (dashboard + action).
"""

from __future__ import annotations


class GrowthFunnelMiddleware:
    """Record first_dashboard_view once per school (session-backed dedupe)."""

    DASHBOARD_PATH_FRAGMENTS = (
        "/backend/",
        "/portal/",
        "/siteconfig/",
        "dashboard",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._maybe_record(request)
        return self.get_response(request)

    def _maybe_record(self, request) -> None:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return
        school = getattr(request, "school", None)
        if school is None:
            return

        # Interactive product demo (tenant flagged RUNMYCAMPUS_DEMO_*): count once per session per school.
        try:
            from django.conf import settings as dj_settings

            if getattr(dj_settings, "RUNMYCAMPUS_DEMO_ENABLED", False):
                dk = f"rmc_growth_demo_touch:{getattr(school, 'pk', '')}"
                if not request.session.get(dk):
                    from apps.schools.funnel_events import record_marketing_funnel_event

                    record_marketing_funnel_event(
                        "demo_started",
                        request,
                        school=school,
                        user=user,
                        metadata={"source": "interactive_tenant"},
                    )
                    request.session[dk] = True
                    request.session.modified = True
        except Exception:
            pass

        path = (getattr(request, "path", "") or "").lower()
        if not any(x in path for x in self.DASHBOARD_PATH_FRAGMENTS):
            return

        sk = f"rmc_growth_dash:{getattr(school, 'pk', '')}"
        if not request.session.get(sk):
            try:
                from apps.schools.funnel_events import record_school_funnel_once

                if record_school_funnel_once(
                    "first_dashboard_view", school, request, user=user
                ):
                    request.session[sk] = True
                    request.session.modified = True
            except Exception:
                pass
        # first_action + activation clear: only via explicit signals (see conversion_lock_state).
